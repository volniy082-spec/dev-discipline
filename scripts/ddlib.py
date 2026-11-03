# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Shared helpers for dev-discipline scripts (stdlib only, Python 3.9+).

Exit-code convention for every script: 0 = PASS, 1 = FAIL, 2 = NOT_PROVEN / environment error.
Project config (optional): .dev-discipline.json in the repo root, e.g.
  {"gate": "gate.txt", "tests": "tests", "flaky": "flaky.txt", "shrink_lists": ["legacy_allow.txt"]}
  "tests" is one directory or a list of directories.
Commands (--cmd) run through `bash -c`: env prefixes (GATE=1 ...), `cd x && ...` and pipes work.
Scripts that judge a change read this config from the BASE ref, so the change cannot redefine its own oracle.
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

TEST_PATH_GLOBS = [
    "tests/*", "test/*", "*/tests/*", "*/test/*", "__tests__/*", "*/__tests__/*",
    "test_*.py", "*_test.py", "tests.py", "test.py", "tests_*.py", "*_tests.py", "*_test.go",
    "*.snap", "__snapshots__/*", "*/__snapshots__/*", "__mocks__/*", "*/__mocks__/*",
]
JS_TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")  # Jest/Vitest default **/*.{test,spec}.?(c|m)[jt]s?(x)
# Basenames a runner collects (gate_meta counts only these; helpers under tests/ are not tests).
COLLECTED_TEST_FILE = re.compile(r"(^test_.*\.py$|_tests?\.py$|^tests?\.py$|^tests_.*\.py$|_test\.go$|"
                                 r"\.(test|spec)\.[cm]?[jt]sx?$)")
DEP_DIRS = {"node_modules", ".venv", "venv", ".tox", "vendor"}


# ---- paths ----------------------------------------------------------------------------------------
def _norm(path):
    p = path.replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _match(path, globs):
    p = _norm(path)
    return any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch(os.path.basename(p), g) for g in globs)


def test_dirs(value):
    """Config "tests": None | "dir" | ["dir", ...] -> list of normalised dirs."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [_norm(str(d)).rstrip("/") for d in value if d and _norm(str(d)).rstrip("/")]


def is_test_path(path, cfg=None):
    p = _norm(path)
    if any(p.startswith(d + "/") for d in test_dirs((cfg or {}).get("tests"))):
        return True
    return bool(JS_TEST_FILE.search(_norm(path))) or _match(path, TEST_PATH_GLOBS)


def is_collected_test(path):
    return bool(COLLECTED_TEST_FILE.search(os.path.basename(_norm(path))))


def _entries(lines):
    """List-file entries: '#' starts a comment, blank lines are skipped."""
    return [l.split("#", 1)[0].strip() for l in lines if l.split("#", 1)[0].strip()]


# ---- git ------------------------------------------------------------------------------------------
def git(args, cwd=None, check=True, input=None):
    r = subprocess.run(["git", "-c", "core.quotePath=false"] + args, cwd=cwd, input=input,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def repo_root(cwd=None):
    return git(["rev-parse", "--show-toplevel"], cwd=cwd).strip()


def load_config(root, ref=None):
    """Config from the working tree, or from REF when judging a change (the change cannot edit its oracle)."""
    if ref:
        txt = git(["show", "%s:.dev-discipline.json" % ref], cwd=root, check=False)
        return json.loads(txt) if txt.strip() else {}
    path = os.path.join(root, ".dev-discipline.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def checkout_paths(cwd, ref, paths):
    """git checkout REF -- PATHS without hitting ARG_MAX."""
    if paths:
        git(["checkout", ref, "--pathspec-from-file=-", "--pathspec-file-nul"], cwd=cwd, input="\0".join(paths))


def name_status(root, *revs):
    """[(status_letter, path)] including renames as delete+add, NUL-safe."""
    out = git(["diff", "--name-status", "--no-renames", "-z"] + list(revs), cwd=root).split("\0")
    res, i = [], 0
    while i + 1 < len(out):
        res.append((out[i][0], out[i + 1]))
        i += 2
    return res


def emit(obj, code):
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    sys.exit(code)


def guarded_main(fn):
    """Any uncaught error (environment or a crash of the script itself) is NOT_PROVEN (exit 2), never a
    traceback with exit 1, which the convention would read as FAIL."""
    try:
        fn()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - every crash is "not proven", not "fail"
        emit({"status": "NOT_PROVEN", "error": "%s: %s" % (type(e).__name__, e)}, 2)


# ---- reading runner output -------------------------------------------------------------------------
# Collection/environment signatures: the run never reached the test body.
NOT_PROVEN_OUTPUT = re.compile(
    r"(ERROR collecting|errors? during collection|ImportError while importing test module|"
    r"no tests ran|NO TESTS RAN|\bRan 0 tests\b|No tests found|No test files found|Cannot find module .{0,200} from|"
    r"command not found|\[dev-discipline\] (TIMEOUT|NOT_FOUND))")
# Evidence that a test failed on an assertion (pytest, unittest, jest/vitest, node:assert, chai, go testing).
ASSERTION_FAILURE = re.compile(
    r"(^E\s+assert\b|^E\s+(AssertionError|Failed: DID NOT (RAISE|WARN))|\bAssertionError\b|"
    r"FAILED \S+ - (assert\b|Failed: DID NOT)|expect\(received\)|^\s*Expected[^:\n]{0,30}:\s|"
    r"^\s+\S+_test\.go:\d+: )", re.M)
# A red caused by one of these (and no assertion) proves only that the code is missing or broken.
FOREIGN_ERROR = re.compile(r"\b(ModuleNotFoundError|ImportError|SyntaxError|IndentationError|NameError|"
                           r"AttributeError|TypeError|ReferenceError|Cannot find module|is not a function|"
                           r"is not defined|fixture '[^']+' not found)")
SUMMARY_COUNTS = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|todo|pending)\b")


def env_failure(code, out):
    return code is None or bool(NOT_PROVEN_OUTPUT.search(out))


def run_counts(out):
    """Counts from the runner's last summary line (pytest '1 failed, 2 passed', jest 'Tests: 1 skipped'),
    or from unittest's 'Ran N tests' block. None when no summary is found."""
    for line in reversed(out.splitlines()):
        found = SUMMARY_COUNTS.findall(line)
        if found:
            c = {}
            for n, k in found:
                k = "errors" if k.startswith("error") else k
                c[k] = c.get(k, 0) + int(n)
            return c
    m = re.search(r"\bRan (\d+) tests?\b[\s\S]*?\n(OK|FAILED)\b(?: \((.*)\))?", out)
    if m:
        extra = dict(re.findall(r"(\w+)=(\d+)", m.group(3) or ""))
        skipped = int(extra.get("skipped", 0)) + int(extra.get("expected_failures", 0))
        bad = int(extra.get("failures", 0)) + int(extra.get("errors", 0))
        return {"passed": int(m.group(1)) - skipped - bad, "failed": bad, "skipped": skipped}
    return None


def nothing_ran(out):
    """Reason when the summary shows no test that actually passed or failed (all skipped / xfail / 0)."""
    c = run_counts(out)
    if c is None or c.get("passed") or c.get("failed") or c.get("errors"):
        return None
    return "no test passed or failed (%s)" % (", ".join("%d %s" % (v, k) for k, v in c.items()) or "0 tests")


def red_kind(out):
    """'assertion' | 'foreign:<Error>' | 'unknown' for a red run."""
    if ASSERTION_FAILURE.search(out):
        return "assertion"
    m = FOREIGN_ERROR.search(out)
    return "foreign:" + m.group(1) if m else "unknown"


# ---- hermetic runs in throwaway worktrees -----------------------------------------------------------
def resolve_base(root, ref):
    """The branch point: REF itself when it is an ancestor of HEAD, else merge-base(REF, HEAD).
    Comparing against the tip of main would count tests added to main after branching as 'removed'."""
    if ref in ("HEAD", "WORKTREE"):
        return ref, None
    sha = git(["rev-parse", "--verify", ref + "^{commit}"], cwd=root).strip()
    if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return sha, None
    mb = git(["merge-base", sha, "HEAD"], cwd=root, check=False).strip()
    if not mb:
        raise RuntimeError("%s has no merge-base with HEAD" % ref)
    return mb, "merge-base of %s and HEAD (%s is not an ancestor of HEAD)" % (ref, ref)


def resolve_commit(root, ref):
    """A commit for REF; 'WORKTREE' snapshots tracked + untracked files without touching the index."""
    if ref != "WORKTREE":
        return git(["rev-parse", "--verify", ref + "^{commit}"], cwd=root).strip()
    fd, idx = tempfile.mkstemp(prefix="dd-index-")
    os.close(fd)
    os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        run = lambda args: subprocess.run(["git"] + args, cwd=root, env=env, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, check=True).stdout.strip()
        run(["read-tree", "HEAD"])
        run(["add", "-A"])
        tree = run(["write-tree"])
        return run(["-c", "commit.gpgSign=false", "commit-tree", tree, "-p", "HEAD", "-m",
                    "dev-discipline worktree snapshot"])
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


class Worktree:
    """Throwaway worktree. Ignored dependency dirs (node_modules, .venv, ...) are symlinked from the
    main checkout so the project's own runner and packages are used, not whatever npx/global finds."""

    def __init__(self, root, commit):
        self.root, self.commit = root, commit
        self.path = tempfile.mkdtemp(prefix="dd-wt-")
        self.linked = []

    def __enter__(self):
        git(["worktree", "add", "--detach", "--force", self.path, self.commit], cwd=self.root)
        ignored = git(["ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z"],
                      cwd=self.root, check=False).split("\0")
        for d in ignored:
            d = d.rstrip("/")
            if d and os.path.basename(d) in DEP_DIRS and d.count("/") <= 3:
                dst = os.path.join(self.path, d)
                if not os.path.exists(dst) and os.path.isdir(os.path.dirname(dst)):
                    os.symlink(os.path.join(self.root, d), dst)
                    self.linked.append(d)
        return self

    def __exit__(self, *exc):
        git(["worktree", "remove", "--force", self.path], cwd=self.root, check=False)
        shutil.rmtree(self.path, ignore_errors=True)

    def tree(self):
        tmp = tempfile.mkdtemp(prefix="dd-tree-")
        try:
            env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
            subprocess.run(["git", "add", "-A"], cwd=self.path, env=env, check=True, stdout=subprocess.DEVNULL)
            return subprocess.run(["git", "write-tree"], cwd=self.path, env=env, check=True,
                                  stdout=subprocess.PIPE, text=True).stdout.strip()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def python_roots(cwd):
    """Import roots inside a worktree: every package dir (pyproject/setup.py/setup.cfg) at depth <= 3, its src/
    first. Beats editable installs (.pth -> live checkout) in monorepos (packages/<name>/src)."""
    roots = []
    for d, dirs, files in os.walk(cwd):
        depth = os.path.relpath(d, cwd).count(os.sep) + (0 if d == cwd else 1)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in DEP_DIRS and depth < 3]
        if d == cwd or {"pyproject.toml", "setup.py", "setup.cfg"} & set(files):
            src = os.path.join(d, "src")
            roots += ([src] if os.path.isdir(src) else []) + [d]
    return roots


PINNED_ENV = {"LC_ALL": "C", "TZ": "UTC", "PYTHONHASHSEED": "0"}


def hermetic_env(cwd=None, pin=True):
    """Env for a judged run. pin=True (prove_fix) fixes locale, timezone and hash seed so the three arms
    differ only by code. pin=False (flake_check) leaves them to the caller: pinning would hide exactly the
    order/time/locale flakes a flakiness measurement must see."""
    env = dict(os.environ)
    stripped = [k for k in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS", "PYTHONSTARTUP",
                            "PYTHONPATH", "PYTEST_ADDOPTS", "CI") if env.pop(k, None) is not None]
    # CI is stripped, not set: configs like `retries: process.env.CI ? 2 : 0` would turn retries on.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if pin:
        env.update(PINNED_ENV)
    if cwd:
        env["PYTHONPATH"] = os.pathsep.join(python_roots(cwd))
    return env, stripped


NOT_FOUND_RE = re.compile(r"^(?:bash: )?(?:line \d+: )?([^:\n]+): (?:command not found|No such file or directory)$", re.M)


def none_reason(out):
    """Why run_cmd returned exit None: the timeout or the missing binary, from its own marker line."""
    m = re.search(r"\[dev-discipline\] (TIMEOUT after \S+|NOT_FOUND: .*)", out or "")
    if not m:
        return "command did not run"
    return m.group(1).replace("NOT_FOUND: ", "binary not found: ").replace("TIMEOUT", "timeout")


def run_cmd(cmd, cwd, timeout, receipt_path, env_extra=None, pin=True):
    """Run CMD through `bash -c` (env prefixes, &&, cd, pipes work) in a hermetic env.
    Returns (exit, combined output); exit is None on a timeout or when the command's binary is missing
    (bash exit 127 'command not found'); none_reason(out) says which."""
    env, _ = hermetic_env(cwd, pin=pin)
    env.update(env_extra or {})
    try:
        r = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=timeout)
        code, out = r.returncode, r.stdout
        m = NOT_FOUND_RE.search(out) if code == 127 else None
        if m:
            code, out = None, out + "\n[dev-discipline] NOT_FOUND: %s" % m.group(1).strip()
    except subprocess.TimeoutExpired as e:
        partial = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        code, out = None, partial + "\n[dev-discipline] TIMEOUT after %ss" % timeout
    except FileNotFoundError as e:  # no bash, or cwd missing
        code, out = None, "[dev-discipline] NOT_FOUND: %s" % (e.filename or e)
    shown = " ".join("%s=%s" % kv for kv in sorted((env_extra or {}).items()))
    with open(receipt_path, "w") as f:
        f.write("$ %s\n# cwd=%s exit=%s pinned_env=%s%s\n%s" % (cmd, cwd, code, pin,
                                                                 (" " + shown) if shown else "", out))
    return code, out
