#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""guard_diff.py — gate-time oracle protection for any git repo (stdlib only, Python 3.9+).

Judges the RESULT, not the editing tool: the tree under the gate (tracked + untracked files, whatever channel
wrote them: Edit, shell, scripts) is compared against BASE.

Per changed protected path:
  GRANTED    path matches an allowlist glob (`*` crosses `/`);
  EXTENDED   existing test file (kind test, code) changed WITHOUT a grant, but only by adding: every old function /
             case / class keeps its name and its own normalized tokens (nested scopes excluded), or only gains whole
             assert statements (py: `assert …` / `self.assertX(…)` lines; js: `expect(…)` / `assert…` without
             assignment or control flow; go: assert./require./t.Error…); module level gains only imports of names
             the old file did not bind (py also: no new def shadowing an old name). Reported, not a violation.
  BOOTSTRAP  new runner config (conftest.py, pytest.ini, jest/vitest config|setup, vitest.workspace) when BASE has no
             test file, snapshot or runner config: setup of the first runner, reported with a note, not a violation.
  VIOLATION  existing test / test config / CI / snapshot changed or deleted without a grant (editing an old test
             body beyond the EXTENDED rule included), or a NEW test config / CI file outside BOOTSTRAP.
             New test files are fine (adding tests is required work).
Weakening (also inside GRANTED files), per function / test case, on code tokens only (comments, strings ignored):
  asserts must not fall, skips must not grow; a deleted test = its asserts to 0.
  Python  asserts: assert, assert*(…) calls (unittest, mock, numpy), pytest.raises/approx/warns/fail;
          skips: mark.skip/skipif/xfail/flaky, pytest.skip(/xfail(/importorskip(, unittest skip*, skipTest(.
  JS/TS   asserts: expect(, assert( / assert.; skips: .skip/.only/.todo/.skipIf/.runIf/.fails, xit/xtest/xdescribe,
          fit/fdescribe, jest.retryTimes, retries(/retry:.
  Go      asserts: t.Error*/Fatal*/Fail*, assert./require.; skips: t.Skip*.
  Functions are matched old->new by name, then by normalized body hash (a pure rename or a move to another
  file is NOT a weakening), then, within one file, by the same short name under another class/suite and by a
  near-identical body (token similarity >= 0.8, best pair first): a rename + edit is judged as an edit. Exemption: allowlist line `WEAKEN-OK: <glob> <reason>` (comment or not; it also grants).
Config (.dev-discipline.json, read from BASE so the change cannot redefine its own oracle):
  "protect": [globs] extra protected paths (oracle config: pins, pyproject.toml, package.json — only if you list them);
  "tests": "dir" | [dirs] extra test dirs;  "protect_defaults": false drops the defaults;
  "allow_file": "path" allowlist, read from the MAIN checkout (dirname of git-common-dir): a writer in a worktree
  cannot grant itself.
Usage:
  guard_diff.py [--repo DIR] [--base REF] [--config PATH] [--allow FILE]     -> JSON, exit 0 PASS / 1 FAIL / 2 NOT_PROVEN
  guard_diff.py --calibrate N [--base REF]   replay the last N first-parent commits, each against its parent (git blobs,
                                              no checkout), ending at REF; one line per commit + summary;
                                              WEAKEN-OK: <glob> <reason> in a commit message exempts; exit 0 / 2.
  Known limits: files ignored by .gitignore are not seen; a test moved to another file AND edited, or renamed and
  rewritten below 0.8 similarity, reads as deleted; asserts count, not strength (a same-count narrowing passes);
  a removed skip is never flagged (it strengthens); new test files are not checked for skips; an added assert
  whose expression has a side effect (`assert xs.pop()`) still reads as EXTENDED.
"""
import argparse
import ast
import bisect
import difflib
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tokenize

_CODE_EXT = ("js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts")
DEFAULTS = (  # (kind, globs); first match wins, so snapshot/config/ci go before test
    ("snapshot", ["**/__snapshots__/**", "*.snap"]),
    ("config", ["conftest.py", "pytest.ini", ".dev-discipline.json"]
     + ["%s.%s.*" % (a, b) for a in ("jest", "vitest") for b in ("config", "setup")] + ["vitest.workspace.*"]),
    ("ci", [".github/workflows/**", ".gitlab-ci.yml", ".circleci/**"]),
    ("test", ["tests/**", "test/**", "**/__tests__/**", "test_*.py", "*_test.py", "*_test.go"]
     + ["*.%s.%s" % (k, e) for k in ("test", "spec") for e in _CODE_EXT]),
)
NEW_OK_KINDS = ("test", "snapshot")   # new files of these kinds are additions, not violations
RUNNER_CONFIG = [g for g in DEFAULTS[1][1] if g != ".dev-discipline.json"]  # BOOTSTRAP: first runner config
WEAKEN_RX = re.compile(r"WEAKEN-OK:\s*(\S+)[ \t]*([^\n]*)")
MODULE = "<module>"
_ENV = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}


class GitError(Exception):
    pass


# ------------------------------------------------------------------ git
def git(root, *args, check=True):
    p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, env=_ENV)
    if check and p.returncode != 0:
        raise GitError("git %s: %s" % (" ".join(args), p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout.decode("utf-8", "surrogateescape")


class Blobs:
    """`git cat-file --batch`: one process for all blob reads (fast on large repos)."""

    def __init__(self, root):
        self.p = subprocess.Popen(["git", "-C", root, "cat-file", "--batch"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, env=_ENV)

    def get(self, rev, path):
        if rev is None or "\n" in path:
            return None
        self.p.stdin.write(("%s:%s\n" % (rev, path)).encode("utf-8", "surrogateescape"))
        self.p.stdin.flush()
        head = self.p.stdout.readline().split()
        if len(head) != 3 or head[1] != b"blob":
            return None
        data = self.p.stdout.read(int(head[2]) + 1)
        return data[:-1]

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def changed_tree(root, base):
    out = {}
    raw = git(root, "diff", "--name-status", "-z", "--no-renames", base).split("\0")
    for i in range(0, len(raw) - 1, 2):
        if raw[i]:
            out[raw[i + 1]] = raw[i][0]
    for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if p:
            out[p] = "A"
    return out


def changed_commit(root, parent, commit):
    raw = git(root, "diff", "--name-status", "-z", "--no-renames", parent, commit).split("\0")
    return {raw[i + 1]: raw[i][0] for i in range(0, len(raw) - 1, 2) if raw[i]}


def resolve_base(root, ref):
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").strip()
    sha = git(root, "rev-parse", "--verify", ref + "^{commit}").strip()
    if sha == head or subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, head], env=_ENV,
                                     capture_output=True).returncode == 0:
        return sha, None
    mb = git(root, "merge-base", sha, head, check=False).strip()
    if not mb:
        raise GitError("%s has no merge-base with HEAD" % ref)
    return mb, "base = merge-base(%s, HEAD) = %s: %s is not an ancestor of HEAD" % (ref, mb[:10], ref)


def main_checkout(root):
    common = git(root, "rev-parse", "--git-common-dir").strip()
    common = common if os.path.isabs(common) else os.path.join(root, common)
    return os.path.realpath(os.path.dirname(os.path.realpath(common)))


# ------------------------------------------------------------------ globs, config, allowlist
def gmatch(path, pat, basename=False):
    pat = pat.strip()
    if pat.startswith("./"):
        pat = pat[2:]
    pat = pat.replace("**", "*")
    if fnmatch.fnmatchcase(path, pat) or (pat.startswith("*/") and fnmatch.fnmatchcase(path, pat[2:])):
        return True
    return basename and "/" not in pat and fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pat)


def load_config(blobs, root, base, cfg_arg):
    if os.path.isabs(cfg_arg) and os.path.isfile(cfg_arg):
        with open(cfg_arg, "rb") as f:
            raw, src = f.read(), cfg_arg
    else:
        raw, src = blobs.get(base, cfg_arg), "%s@%s" % (cfg_arg, base[:10])
    if raw is None:
        return {}, "config: none (%s absent), defaults" % src
    try:
        cfg = json.loads(raw.decode("utf-8"))
        assert isinstance(cfg, dict)
    except (ValueError, AssertionError):
        raise GitError("config %s is not a JSON object" % src)
    return cfg, "config: " + src


def rules(cfg):
    out = [(k, list(g)) for k, g in DEFAULTS] if cfg.get("protect_defaults", True) else []
    tests = cfg.get("tests") or []
    tests = [tests] if isinstance(tests, str) else tests
    out.append(("test", [t.rstrip("/") + "/**" for t in tests]))
    out.insert(0, ("config", list(cfg.get("protect", []))))
    return out


def classify(path, rules_):
    for kind, globs in rules_:
        if any(gmatch(path, g, basename=True) for g in globs):
            return kind
    return None


def parse_allow(text):
    grants, weaken, notes = [], [], []
    for line in text.splitlines():
        for m in WEAKEN_RX.finditer(line):
            if m.group(2).strip().lstrip("#").strip():
                weaken.append(m.group(1))
            else:
                notes.append("WEAKEN-OK without a reason ignored: %s" % m.group(1))
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("WEAKEN-OK:"):
            grants.append(s.split()[0])
    return grants + weaken, weaken, notes


# ------------------------------------------------------------------ scopes and counts
class Scope:
    __slots__ = ("path", "name", "hash", "asserts", "skips", "toks", "shell")

    def __init__(self, path, name, h, toks=None, shell=None):
        self.path, self.name, self.hash, self.asserts, self.skips = path, name, h, 0, 0
        self.toks = toks  # normalized body tokens (name dropped): for rename + edit pairing
        self.shell = shell  # own tokens only (nested scopes and name dropped; py keeps "\n"): for EXTENDED


SIMILAR = 0.8  # body-token similarity at which an unmatched old scope pairs with an unmatched new one (same file)


def _short(name):
    """Last component of a scope name: Class.test_x -> test_x, 'suite > case' -> case."""
    return name.rsplit(" > ", 1)[-1].rsplit(".", 1)[-1]


def _digest(parts):
    return hashlib.sha1("\x1f".join(parts).encode("utf-8", "surrogateescape")).hexdigest()


def _dedupe(names):
    seen, out = {}, []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else "%s#%d" % (n, seen[n]))
    return out


_PY_SKIP_MARK = {"skip", "skipif", "xfail", "flaky"}
_PY_SKIP_CALL = {"skip", "xfail", "importorskip"}
_PY_UT_SKIP = {"skip", "skipIf", "skipUnless", "expectedFailure"}
_PY_ASSERT_ATTR = {"raises", "approx", "warns", "fail"}
_ASSERT_NAME = re.compile(r"^assert[A-Z_]\w*$")


def _py_kind(t, i):
    s = t[i]
    nx = t[i + 1:i + 4]
    pv = t[i - 1] if i else ""
    if s == "assert":
        return "assert"
    if _ASSERT_NAME.match(s) and nx[:1] == ["("] and pv not in ("def", "class"):
        return "assert"
    if s == "pytest" and len(nx) >= 2 and nx[0] == "." and nx[1] in _PY_ASSERT_ATTR:
        return "assert"
    if s == "mark" and len(nx) >= 2 and nx[0] == "." and nx[1] in _PY_SKIP_MARK:
        return "skip"
    if s == "pytest" and len(nx) == 3 and nx[0] == "." and nx[1] in _PY_SKIP_CALL and nx[2] == "(":
        return "skip"
    if s == "unittest" and len(nx) >= 2 and nx[0] == "." and nx[1] in _PY_UT_SKIP:
        return "skip"
    if s in _PY_UT_SKIP and pv == "@":
        return "skip"
    if s == "skipTest" and pv == "." and nx[:1] == ["("]:
        return "skip"
    return None


def _drop_name(body):
    k = next((k for k, x in enumerate(body) if x in ("def", "class")), None)
    if k is not None and k + 1 < len(body):
        del body[k + 1]


def py_scopes(path, src):
    tree = ast.parse(src)
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                              tokenize.DEDENT, tokenize.ENDMARKER)]
    spans = []

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([d.lineno for d in ch.decorator_list] + [ch.lineno])
                spans.append((start, ch.end_lineno or ch.lineno, prefix + ch.name))
                walk(ch, prefix + ch.name + ".")
            else:
                walk(ch, prefix)
    walk(tree, "")
    names = _dedupe([s[2] for s in spans])
    tl = [t.start[0] for t in toks]
    owner = {}
    for k in sorted(range(len(spans)), key=lambda k: spans[k][0]):  # inner scopes start later and overwrite
        for ln in range(spans[k][0], spans[k][1] + 1):
            owner[ln] = k
    stmt = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER)]
    scopes = []
    for k, ((a, b, _), name) in enumerate(zip(spans, names)):
        body = [t.string for t in toks[bisect.bisect_left(tl, a):bisect.bisect_right(tl, b)]]
        _drop_name(body)
        own = ["\n" if t.type == tokenize.NEWLINE else t.string for t in stmt if owner.get(t.start[0]) == k]
        _drop_name(own)
        scopes.append(Scope(path, name, _digest(body), tuple(body), tuple(own)))
    module = Scope(path, MODULE, None)
    strs = [t.string for t in toks if t.type in (tokenize.NAME, tokenize.OP)]
    lines = [t.start[0] for t in toks if t.type in (tokenize.NAME, tokenize.OP)]
    for i in range(len(strs)):
        kind = _py_kind(strs, i)
        if kind:
            k = owner.get(lines[i])
            sc = module if k is None else scopes[k]
            setattr(sc, kind + "s", getattr(sc, kind + "s") + 1)
    return scopes + [module]


def lex_c(src, go):
    """C-family tokens (kind, value): comments dropped; strings kept as one token."""
    toks, i, n = [], 0, len(src)
    regex_prev = set("(,=:[!&|?{};+-*%<>~^")
    regex_kw = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await"}
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "\"'" or (c == "`" and go):
            j = i + 1
            while j < n and src[j] != c and (c == "`" or src[j] != "\n"):
                j += 2 if (src[j] == "\\" and c != "`") else 1
            toks.append(("str", src[i + 1:j]))
            i = j + 1
        elif c == "`":
            j, depth = i + 1, 0
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if depth == 0 and src[j] == "`":
                    break
                if src.startswith("${", j):
                    depth += 1
                    j += 1
                elif src[j] == "}" and depth:
                    depth -= 1
                j += 1
            toks.append(("str", src[i + 1:j]))
            i = j + 1
        elif c == "/" and not go and (not toks or (toks[-1][0] == "op" and toks[-1][1] in regex_prev)
                                      or (toks[-1][0] == "id" and toks[-1][1] in regex_kw)):
            j, cls = i + 1, False
            while j < n and src[j] != "\n" and (cls or src[j] != "/"):
                if src[j] == "\\":
                    j += 1
                elif src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                j += 1
            j += 1
            while j < n and (src[j].isalnum()):
                j += 1
            toks.append(("str", src[i:j]))
            i = j
        elif c.isalpha() or c in "_$":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            toks.append(("id", src[i:j]))
            i = j
        elif c.isdigit():
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in "._"):
                j += 1
            toks.append(("num", src[i:j]))
            i = j
        else:
            toks.append(("op", c))
            i += 1
    return toks


_JS_TEST = {"it", "test", "describe", "suite", "context", "specify", "bench", "xit", "xtest", "xdescribe",
            "xcontext", "xspecify", "fit", "fdescribe"}
_JS_SKIP_ATTR = {"skip", "only", "todo", "skipIf", "runIf", "fails"}
_JS_SKIP_ID = {"xit", "xtest", "xdescribe", "xcontext", "xspecify", "fit", "fdescribe"}
_GO_FAIL = {"Error", "Errorf", "Fatal", "Fatalf", "Fail", "FailNow"}


def _c_kind(t, i, go):
    k, s = t[i]
    if k != "id":
        return None
    nx = [v for _, v in t[i + 1:i + 3]]
    pv = t[i - 1][1] if i else ""
    if go:
        if pv == "." and nx[:1] == ["("] and s in _GO_FAIL:
            return "assert"
        if s in ("assert", "require") and nx[:1] == ["."] and pv != ".":
            return "assert"
        if pv == "." and s in ("Skip", "Skipf", "SkipNow") and nx[:1] == ["("]:
            return "skip"
        return None
    if s == "expect" and nx[:1] == ["("] and pv != ".":
        return "assert"
    if s == "assert" and nx[:1] in (["("], ["."]) and pv not in (".", "function"):
        return "assert"
    if pv == "." and s in _JS_SKIP_ATTR:
        return "skip"
    if s in _JS_SKIP_ID and nx[:1] == ["("] and pv != ".":
        return "skip"
    if s == "retryTimes" and pv == ".":
        return "skip"
    if s in ("retries", "retry") and nx[:1] in (["("], [":"]):
        return "skip"
    return None


def c_scopes(path, src, go):
    t = lex_c(src, go)
    match, stack = {}, []
    for i, (k, v) in enumerate(t):
        if k == "op" and v in "([{":
            stack.append(i)
        elif k == "op" and v in ")]}" and stack:
            match[stack.pop()] = i
    spans = []  # (start, end, title, title_index)
    for i, (k, v) in enumerate(t):
        if k != "id":
            continue
        pv = t[i - 1][1] if i else ""
        if not go and v in _JS_TEST and pv != ".":
            j = i + 1
            while j + 1 < len(t) and t[j][1] == "." and t[j + 1][0] == "id":
                j += 2
            while j < len(t):
                if t[j][0] == "str":
                    j += 1
                elif t[j][1] == "(" and j + 1 < len(t) and t[j + 1][0] == "str" and j in match:
                    spans.append((i, match[j], t[j + 1][1], j + 1))
                    break
                elif t[j][1] == "(" and j in match:
                    j = match[j] + 1
                else:
                    break
        elif go and v == "Run" and pv == "." and i + 2 < len(t) and t[i + 1][1] == "(" and t[i + 2][0] == "str" \
                and (i + 1) in match:
            spans.append((i, match[i + 1], t[i + 2][1], i + 2))
        elif (v == "function" and not go) or (v == "func" and go):
            j = i + 1
            if go and j < len(t) and t[j][1] == "(" and j in match:
                j = match[j] + 1
            if j < len(t) and t[j][0] == "id":
                name_i = j
                j += 1
                while j < len(t) and t[j][1] != "{":
                    j = match[j] + 1 if t[j][1] == "(" and j in match else j + 1
                if j < len(t) and j in match:
                    spans.append((i, match[j], t[name_i][1], name_i))
    spans.sort()
    full, open_ = [], []  # spans sorted by start nest like brackets: a stack gives the parents
    for a, b, title, _ in spans:
        while open_ and open_[-1][1] < a:
            open_.pop()
        full.append(" > ".join([p[2] for p in open_] + [title]))
        open_.append((a, b, title))
    owner = [None] * len(t)
    for k, (a, b, _, _) in enumerate(spans):
        owner[a:b + 1] = [k] * (b - a + 1)
    names = _dedupe(full)
    bodies = [[v for j, (_, v) in enumerate(t[a:b + 1], a) if j != ti] for (a, b, _, ti) in spans]
    sv = [("\0" + v) if kd == "str" else v for kd, v in t]  # string contents never read as code
    shells = [tuple(sv[j] for j in range(a, b + 1) if owner[j] == k and j != ti)
              for k, (a, b, _, ti) in enumerate(spans)]
    scopes = [Scope(path, nm, _digest(bd), tuple(bd), sh) for bd, nm, sh in zip(bodies, names, shells)]
    module = Scope(path, MODULE, None, None, tuple(sv[j] for j in range(len(t)) if owner[j] is None))
    for i in range(len(t)):
        kind = _c_kind(t, i, go)
        if kind:
            sc = module if owner[i] is None else scopes[owner[i]]
            setattr(sc, kind + "s", getattr(sc, kind + "s") + 1)
    return scopes + [module]


def lang(path):
    ext = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    return "py" if ext == "py" else "go" if ext == "go" else "js" if ext in _CODE_EXT else None


_CACHE = {}


def file_scopes(path, src):
    """Scopes of one file version; cached by (path, content): in --calibrate a commit's new blob is the next one's old."""
    key = (path, hashlib.sha1(src.encode("utf-8", "surrogateescape")).hexdigest())
    if key not in _CACHE:
        _CACHE[key] = _file_scopes(path, src)
    return _CACHE[key]


def _file_scopes(path, src):
    lg = lang(path)
    if lg == "py":
        return py_scopes(path, src)
    return c_scopes(path, src, lg == "go")


def file_level(path, src):
    """Fallback when a side does not parse: whole-file counts by regex (strings/comments not stripped)."""
    sc = Scope(path, "<file>", None)
    if lang(path) == "py":
        sc.asserts = len(re.findall(r"^\s*assert\b|\bassert[A-Z_]\w*\s*\(|\bpytest\.(?:raises|approx|warns|fail)\b",
                                    src, re.M))
        sc.skips = len(re.findall(r"\bmark\.(?:skip|skipif|xfail|flaky)\b|\bpytest\.(?:skip|xfail|importorskip)\(",
                                  src))
    else:
        sc.asserts = len(re.findall(r"\b(?:expect|assert)\s*[(.]", src))
        sc.skips = len(re.findall(r"\.(?:skip|only|todo)\b|\bx(?:it|test|describe)\s*\(", src))
    return [sc]


# ------------------------------------------------------------------ EXTENDED: an existing test file that only gained tests
_STMT_KW = {"return", "raise", "throw", "yield", "break", "continue", "pass", "del", "delete", "def", "function",
            "func", "class", "lambda", "if", "else", "elif", "for", "while", "do", "try", "except", "catch", "finally",
            "with", "switch", "case", "var", "let", "const", "import", "from", "global", "nonlocal", "defer", "go",
            "goto", "skip", "only", "todo", "skipIf", "runIf", "fails", "retryTimes", "retries", "retry"}


def _is_assign(run, i):
    """JS/Go op tokens are single chars: '=' is assignment unless part of ==, !=, <=, >=, =>."""
    pv = run[i - 1] if i else ""
    nx = run[i + 1] if i + 1 < len(run) else ""
    return not (pv in ("=", "!", "<", ">") or nx in ("=", ">"))


def _py_assert_run(run, before):
    """Whole statements only, each an assert: `assert …` or `self.assertX(…)`; no walrus."""
    if before != "\n" or not run or run[-1] != "\n" or ":=" in run:
        return False
    stmts, cur = [], []
    for x in run:
        if x in ("\n", ";"):
            if cur:
                stmts.append(cur)
            cur = []
        else:
            cur.append(x)
    return bool(stmts) and all(st[0] == "assert" or (len(st) >= 4 and st[0] in ("self", "cls") and st[1] == "."
                                                     and _ASSERT_NAME.match(st[2]) and st[3] == "(")
                               for st in stmts)


def _c_assert_run(run, go):
    stmts, cur = [], []
    for x in run:
        if x == ";":
            if cur:
                stmts.append(cur)
            cur = []
        else:
            cur.append(x)
    if cur:
        stmts.append(cur)
    if not stmts or any(x in _STMT_KW for x in run):
        return False
    if any(x == "=" and _is_assign(run, i) for i, x in enumerate(run)):
        return False
    if any(run[i] in "+-" and run[i + 1] == run[i] for i in range(len(run) - 1)):
        return False
    for st in stmts:
        st = st[1:] if st[0] == "await" else st
        if go:
            ok = st[0] in ("assert", "require") or (len(st) >= 3 and st[1] == "." and st[2] in _GO_FAIL)
        else:
            ok = st[0] in ("expect", "assert")
        if not ok:
            return False
    return True


def _inserted_runs(old, new):
    """None if old -> new is not insert-only; else [(j1, j2)] runs in new."""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    runs = []
    for op, _, _, j1, j2 in sm.get_opcodes():
        if op == "insert":
            runs.append((j1, j2))
        elif op != "equal":
            return None
    return runs


def _runs_ok(old, new, ok):
    """Every inserted run passes ok(run, token_before) at some placement it can slide to (equal tokens at its ends)."""
    runs = _inserted_runs(old, new)
    if runs is None:
        return False
    for j1, j2 in runs:
        cands = [(j1, j2)]
        a, b = j1, j2
        while a > 0 and new[a - 1] == new[b - 1]:
            a, b = a - 1, b - 1
            cands.append((a, b))
        a, b = j1, j2
        while b < len(new) and new[a] == new[b]:
            a, b = a + 1, b + 1
            cands.append((a, b))
        if not any(ok(list(new[x:y]), new[x - 1] if x else "") for x, y in cands):
            return False
    return True


def _py_bound(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
    return out


def _py_module_extended(so, sn):
    """'' or the reason: module statements (defs/classes aside) kept in order; inserted ones are imports of fresh
    names; no new top-level def/class rebinds an old name."""
    to, tn = ast.parse(so), ast.parse(sn)
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    bound = _py_bound(to)
    olds = [x for x in to.body if not isinstance(x, defs)]
    old = [ast.dump(x) for x in olds]
    old_top = {x.name for x in to.body if isinstance(x, defs)}
    i = 0
    for x in tn.body:
        if isinstance(x, defs):
            if x.name not in old_top and x.name in bound:
                return "new def/class %s rebinds a name the old file uses" % x.name
            continue
        d = ast.dump(x)
        if i < len(old) and d == old[i]:
            i += 1
            continue
        if not isinstance(x, (ast.Import, ast.ImportFrom)):
            return "module level changed beyond new imports"
        names = {(al.name, al.asname) for al in x.names}
        prev = olds[i] if i < len(olds) else None
        if (prev is not None and type(prev) is type(x) and getattr(prev, "module", None) == getattr(x, "module", None)
                and getattr(prev, "level", 0) == getattr(x, "level", 0)
                and {(al.name, al.asname) for al in prev.names} <= names):
            names -= {(al.name, al.asname) for al in prev.names}  # same import, names added to it
            i += 1
        if any(n == "*" or (an or n.split(".")[0]) in bound for n, an in names):
            return "a new import rebinds a name the old file uses (or is *)"
    return "" if i == len(old) else "module level changed beyond new imports"


def _c_module_extended(old, new, go):
    old_ids = {x for x in old if x[:1] != "\0"}

    def ok(run, _before):
        if all(x == ";" for x in run):
            return True
        if go:
            return all(x == ";" or x[:1] == "\0" for x in run)
        if run[0] != "import" or any(x == "=" and _is_assign(run, i) for i, x in enumerate(run)):
            return False
        names = [x for i, x in enumerate(run) if x[:1] != "\0" and re.match(r"^[A-Za-z_$][\w$]*$", x)
                 and x not in ("import", "from", "as", "type") and (i + 1 >= len(run) or run[i + 1] != "as")]
        return not any(x in old_ids for x in names)
    return _runs_ok(old, new, ok)


def extended(path, so, sn, o_sc, n_sc):
    """'' if the change of an existing test file only adds tests / asserts (EXTENDED), else the reason it does not."""
    lg = lang(path)
    if lg is None:
        return "not a code file"
    old = {s.name: s for s in o_sc if s.name != MODULE}
    new = {s.name: s for s in n_sc if s.name != MODULE}
    if any(s.shell is None for s in list(old.values()) + list(new.values())):
        return "whole-file parse"
    for name, s in old.items():
        m = new.get(name)
        if m is None:
            return "old scope %s removed or renamed" % name
        if m.shell == s.shell or (lg != "py" and _runs_ok(s.shell, m.shell, lambda run, _b: set(run) == {";"})):
            continue  # unchanged, or (js/go) only the ';' after a new nested case
        if m.skips > s.skips or m.asserts <= s.asserts:
            return "old scope %s edited" % name
        if lg == "py":
            good = _runs_ok(s.shell, m.shell, _py_assert_run)
        else:
            good = _runs_ok(s.shell, m.shell, lambda run, _b: _c_assert_run(run, lg == "go"))
        if not good:
            return "old scope %s edited beyond added asserts" % name
    if lg == "py":
        if any("#" in n for n in new if n not in old):
            return "a new def repeats an old name (shadows it)"
        return _py_module_extended(so, sn)
    om = next(s for s in o_sc if s.name == MODULE)
    nm = next(s for s in n_sc if s.name == MODULE)
    old_ids = {x for x in om.shell if x[:1] != "\0"}
    if any(" > " not in n and n in old_ids for n in new if n not in old):
        return "a new function repeats an old name"
    return "" if _c_module_extended(om.shell, nm.shell, lg == "go") else "module level changed beyond new imports"


def base_has_tests(root, rev, rules_):
    for p in git(root, "ls-tree", "-r", "--name-only", "-z", rev).split("\0"):
        if p and (classify(p, rules_) in ("test", "snapshot") or any(gmatch(p, g, basename=True) for g in RUNNER_CONFIG)):
            return True
    return False


# ------------------------------------------------------------------ evaluation
def _text(b):
    return None if b is None else b.decode("utf-8", "replace")


def evaluate(changes, rules_, grants, weaken_ok, has_tests=lambda: True):
    """changes: [(path, old_bytes|None, new_bytes|None)] -> result dict (no status).
    has_tests(): does BASE hold any test / snapshot / runner config (called only when a runner config is added)."""
    res = {"violations": [], "weakenings": [], "exempted": [], "granted": [], "new_tests": [], "moved": [],
           "extended": [], "bootstrap": [], "protected": 0, "parsed": 0, "fallback": []}
    prot = [(p, classify(p, rules_), o, n) for p, o, n in changes]
    prot = [x for x in prot if x[1] and x[2] != x[3]]
    res["protected"] = len(prot)
    added = {n for p, k, o, n in prot if o is None and n is not None}
    olds, news = [], []
    boot = []
    for path, kind, old, new in prot:
        state = "added" if old is None else "deleted" if new is None else "modified"
        o_sc = n_sc = None
        fell = False
        if lang(path):
            so, sn = _text(old), _text(new)
            try:
                o_sc = file_scopes(path, so) if so is not None else []
                n_sc = file_scopes(path, sn) if sn is not None else []
            except (SyntaxError, ValueError, tokenize.TokenError, IndentationError, RecursionError):
                o_sc = file_level(path, so) if so is not None else []
                n_sc = file_level(path, sn) if sn is not None else []
                res["fallback"].append(path)
                fell = True
            res["parsed"] += 1
            olds += o_sc
            news += [(s, old is not None) for s in n_sc]
        why = None
        if any(gmatch(path, g) for g in grants):
            res["granted"].append({"path": path, "kind": kind, "state": state})
        elif state == "added" and kind in NEW_OK_KINDS:
            res["new_tests"].append(path)
        elif state == "deleted" and old in added:
            res["moved"].append(path)
        elif state == "added" and kind == "config" and any(gmatch(path, g, basename=True) for g in RUNNER_CONFIG):
            boot.append(path)
        elif state == "modified" and kind == "test" and o_sc is not None and not fell:
            try:
                why = extended(path, so, sn, o_sc, n_sc)
            except (SyntaxError, ValueError, RecursionError):
                why = "does not parse"
            if why == "":
                res["extended"].append(path)
            else:
                res["violations"].append({"path": path, "kind": kind, "state": state,
                                          "reason": "modified test file without a grant", "detail": why})
        else:
            why = ("new %s file" % kind) if state == "added" else "%s %s file without a grant" % (state, kind)
            res["violations"].append({"path": path, "kind": kind, "state": state, "reason": why})
    if boot:
        if has_tests():
            res["violations"] += [{"path": p, "kind": "config", "state": "added", "reason": "new config file"}
                                  for p in boot]
        else:
            res["bootstrap"] = boot
    # 1) same file, same name; 2) normalized body hash anywhere (rename, move); 3) leftovers.
    by_name = {(s.path, s.name): s for s, _ in news}
    pairs, left_old, used = [], [], set()
    for s in olds:
        m = by_name.get((s.path, s.name))
        if m is not None:
            pairs.append((s, m))
            used.add(id(m))
        else:
            left_old.append(s)
    pool = {}
    for s, _ in news:
        if id(s) not in used and s.hash:
            pool.setdefault(s.hash, []).append(s)
    rest = []
    for s in left_old:
        cand = pool.get(s.hash) if s.hash else None
        if cand:
            m = cand.pop(0)
            pairs.append((s, m))
            used.add(id(m))
        else:
            rest.append(s)
    # 3) rename + edit in one change (same file): the same short name under another class/suite, unique on both
    # sides; then a near-identical body (token similarity >= SIMILAR), best pair first. The pair is then judged
    # like any edit (asserts must not fall), so this only turns a false "deleted" into an honest count.
    free = [s for s, _ in news if id(s) not in used and s.toks]
    how = {}
    for s in list(rest):
        if not s.toks:
            continue
        sib = [m for m in free if m.path == s.path and _short(m.name) == _short(s.name) and id(m) not in used]
        twins = [o for o in rest if o.path == s.path and _short(o.name) == _short(s.name)]
        if len(sib) == 1 and len(twins) == 1:
            pairs.append((s, sib[0]))
            used.add(id(sib[0]))
            rest.remove(s)
            how[id(s)] = "moved (same name)"
    cands = []
    for s in rest:
        if not s.toks:
            continue
        for m in free:
            if id(m) in used or m.path != s.path:
                continue
            sm = difflib.SequenceMatcher(None, s.toks, m.toks, autojunk=False)
            if sm.real_quick_ratio() >= SIMILAR and sm.quick_ratio() >= SIMILAR:
                r = sm.ratio()
                if r >= SIMILAR:
                    cands.append((-r, len(cands), s, m))
    taken = set()
    for negr, _, s, m in sorted(cands, key=lambda c: (c[0], c[1])):
        if id(s) in taken or id(m) in used:
            continue
        pairs.append((s, m))
        used.add(id(m))
        taken.add(id(s))
        how[id(s)] = "renamed (body ~%.2f)" % -negr
    for s in rest:
        if id(s) not in taken and s.asserts:
            pairs.append((s, None))
    for s, existed in news:
        if id(s) not in used and existed and s.skips:
            pairs.append((None, s))
    for o, n in pairs:
        oa, os_ = (o.asserts, o.skips) if o else (0, 0)
        na, ns = (n.asserts, n.skips) if n else (0, 0)
        ref = o or n
        where = ref.path if (o is None or n is None or o.path == n.path) else "%s -> %s" % (o.path, n.path)
        for what, a, b, worse in (("assert", oa, na, na < oa), ("skip", os_, ns, ns > os_)):
            if worse:
                item = {"path": where, "scope": ref.name if not (o and n) or o.name == n.name else
                        "%s -> %s" % (o.name, n.name), "what": what, "old": a, "new": b,
                        "detail": "deleted" if n is None else "added scope" if o is None else
                        "changed, " + how[id(o)] if id(o) in how else "changed"}
                ex = any(gmatch(p, g) for g in weaken_ok for p in {(o or n).path, (n or o).path})
                res["exempted" if ex else "weakenings"].append(item)
    return res


# ------------------------------------------------------------------ modes
def run_check(a):
    root = git(os.path.abspath(a.repo), "rev-parse", "--show-toplevel").strip()
    base, note = resolve_base(root, a.base)
    notes = [note] if note else []
    blobs = Blobs(root)
    try:
        cfg, cnote = load_config(blobs, root, base, a.config)
        notes.append(cnote)
        main = main_checkout(root)
        allow_path = a.allow or (os.path.join(main, cfg["allow_file"]) if cfg.get("allow_file") else None)
        grants, weaken = [], []
        if allow_path:
            if not os.path.isfile(allow_path):
                if a.allow:
                    raise GitError("--allow: no file %s" % allow_path)
                notes.append("allowlist %s absent: no grants" % allow_path)
            else:
                with open(allow_path, encoding="utf-8", errors="replace") as f:
                    grants, weaken, n2 = parse_allow(f.read())
                notes += n2 + ["allowlist %s: %d globs, %d WEAKEN-OK" % (allow_path, len(grants), len(weaken))]
        else:
            notes.append("no allowlist (config allow_file unset, no --allow): every edit of an existing test beyond EXTENDED is ungranted")
        if allow_path and os.path.realpath(root) == main:
            notes.append("writer tree is the main checkout: grants there are self-servable; run writers in a worktree")
        rules_ = rules(cfg)
        changes = []
        for path, st in sorted(changed_tree(root, base).items()):
            if not classify(path, rules_):
                continue
            full = os.path.join(root, path)
            if os.path.isdir(full) and not os.path.islink(full):
                continue  # submodule
            if os.path.islink(full):
                new = os.readlink(full).encode("utf-8", "surrogateescape")
            elif os.path.isfile(full):
                with open(full, "rb") as f:
                    new = f.read()
            else:
                new = None
            changes.append((path, blobs.get(base, path), new))
    finally:
        blobs.close()
    r = evaluate(changes, rules_, grants, weaken, lambda: base_has_tests(root, base, rules_))
    if r["extended"]:
        notes.append("extended (existing test files that only gained tests/asserts, no grant needed; name them in "
                     "the report): " + ", ".join(r["extended"]))
    if r["bootstrap"]:
        notes.append("bootstrap: base had no tests or runner config; new runner config accepted as setup (say so in "
                     "the report, commit it separately): " + ", ".join(r["bootstrap"]))
    if r["fallback"]:
        notes.append("parsed as whole file (syntax not recognised): " + ", ".join(r["fallback"]))
    notes.append("inspected: %d protected changed paths, %d parsed for weakening; new tests %d, moved %d, exempted %d"
                 % (r["protected"], r["parsed"], len(r["new_tests"]), len(r["moved"]), len(r["exempted"])))
    fail = bool(r["violations"] or r["weakenings"])
    out = {"status": "FAIL" if fail else "PASS", "base": base, "violations": r["violations"],
           "weakenings": r["weakenings"], "granted": r["granted"], "exempted": r["exempted"],
           "new_tests": r["new_tests"], "extended": r["extended"], "bootstrap": r["bootstrap"], "note": "; ".join(notes)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.stderr.write("guard_diff: %s — %d violations, %d weakenings, %d granted, %d extended, %d bootstrap, "
                     "%d protected changed\n" % (out["status"], len(r["violations"]), len(r["weakenings"]),
                                                 len(r["granted"]), len(r["extended"]), len(r["bootstrap"]),
                                                 r["protected"]))
    return 1 if fail else 0


def run_calibrate(a):
    root = git(os.path.abspath(a.repo), "rev-parse", "--show-toplevel").strip()
    log = git(root, "log", "--first-parent", "-n", str(a.calibrate), "--format=%H%x00%P%x00%s%x00%b%x1e", a.base)
    blobs = Blobs(root)
    stats = {"commits": 0, "touch_commits": 0, "weak_commits": 0, "weak_items": 0, "exempt_items": 0,
             "ext_commits": 0, "ext_only_commits": 0, "boot_commits": 0,
             "files_parsed": 0, "fallback_files": 0, "skipped_root": 0}
    rows = []
    try:
        for rec in log.split("\x1e"):
            parts = rec.strip("\n").split("\0")
            if len(parts) < 4:
                continue
            sha, parents, subj, body = parts[0], parts[1].split(), parts[2], parts[3]
            if not parents:
                stats["skipped_root"] += 1
                continue
            parent = parents[0]
            cfg, _ = load_config(blobs, root, parent, a.config)
            rules_ = rules(cfg)
            weaken = [m.group(1) for m in WEAKEN_RX.finditer(subj + "\n" + body) if m.group(2).strip()]
            ch = [(p, blobs.get(parent, p), blobs.get(sha, p)) for p in sorted(changed_commit(root, parent, sha))
                  if classify(p, rules_)]
            r = evaluate(ch, rules_, [], weaken, lambda: base_has_tests(root, parent, rules_))
            stats["commits"] += 1
            stats["touch_commits"] += bool(r["violations"])
            stats["ext_commits"] += bool(r["extended"])
            stats["ext_only_commits"] += bool(r["extended"]) and not r["violations"]
            stats["boot_commits"] += bool(r["bootstrap"])
            stats["weak_commits"] += bool(r["weakenings"])
            stats["weak_items"] += len(r["weakenings"])
            stats["exempt_items"] += len(r["exempted"])
            stats["files_parsed"] += r["parsed"]
            stats["fallback_files"] += len(r["fallback"])
            flags = ["%s::%s %s %d->%d" % (w["path"], w["scope"], w["what"], w["old"], w["new"])
                     for w in r["weakenings"]]
            rows.append({"commit": sha, "subject": subj, "touch": len(r["violations"]), "new_tests": len(r["new_tests"]),
                         "extended": r["extended"], "bootstrap": r["bootstrap"],
                         "weakenings": r["weakenings"], "exempted": len(r["exempted"])})
            if not a.json:
                print("%s touch=%d ext=%d%s new=%d weak=%d%s  %s%s" % (
                    sha[:9], len(r["violations"]), len(r["extended"]),
                    " boot=%d" % len(r["bootstrap"]) if r["bootstrap"] else "", len(r["new_tests"]), len(r["weakenings"]),
                    " exempt=%d" % len(r["exempted"]) if r["exempted"] else "", subj[:60],
                    ("  FLAGS: " + "; ".join(flags[:3]) + (" …+%d" % (len(flags) - 3) if len(flags) > 3 else ""))
                    if flags else ""))
    finally:
        blobs.close()
    if a.json:
        print(json.dumps({"status": "MEASURED", "summary": stats, "commits": rows}, ensure_ascii=False, indent=1))
    else:
        print("calibrate: commits=%(commits)d protected_touch_commits=%(touch_commits)d weakening_commits=%(weak_commits)d"
              " weakening_items=%(weak_items)d exempt_items=%(exempt_items)d extended_commits=%(ext_commits)d"
              " extended_only_commits=%(ext_only_commits)d bootstrap_commits=%(boot_commits)d files_parsed=%(files_parsed)d"
              " whole_file_fallback=%(fallback_files)d root_skipped=%(skipped_root)d" % stats)
        print("calibrate: touch = protected edits that would need a grant; ext = existing test files that only gained "
              "tests (no grant needed); judge every FLAG by hand (precision), "
              "and seed known weakenings to measure recall")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate-time oracle protection: base..tree diff of tests, test config, CI.")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--config", default=".dev-discipline.json")
    ap.add_argument("--allow", default=None)
    ap.add_argument("--calibrate", type=int, default=0, metavar="N")
    ap.add_argument("--json", action="store_true", help="calibrate: JSON instead of lines (check is always JSON)")
    a = ap.parse_args(argv)
    try:
        return run_calibrate(a) if a.calibrate > 0 else run_check(a)
    except (GitError, OSError) as e:
        print(json.dumps({"status": "NOT_PROVEN", "base": a.base, "violations": [], "weakenings": [], "granted": [],
                          "note": str(e)}, ensure_ascii=False, indent=1))
        return 2


if __name__ == "__main__":
    sys.exit(main())
