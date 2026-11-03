#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Prove that a test actually proves a fix: red on base -> green on fix -> red again after reverting the fix.

usage: prove_fix.py --base REF [--fix REF|WORKTREE|DIR] --cmd "pytest -q tests/test_x.py::test_y"
                    [--test-files a b ...] [--expect REGEX] [--reached MARKER]
                    [--full-cmd "pytest -q"] [--repeat N] [--timeout 600] [--receipts DIR] [--repo DIR]

--fix DIR (an existing directory, e.g. a writer's worktree) means --repo DIR --fix WORKTREE: the
uncommitted tree of that checkout. --cmd and --full-cmd run through `bash -c`, so `GATE=1 pytest ...`,
`cd web && npx vitest run x` and pipes work; the environment is pinned (LC_ALL=C, TZ=UTC, PYTHONHASHSEED=0).

Arm A: base source + the fix's test files       -> must FAIL by an assertion (+ MARKER, --expect if given).
Arm B: fix                                       -> --cmd must PASS (and --full-cmd, if given).
Arm C: fix with every non-test change reverted   -> tree must equal arm A, must FAIL again the same way.
A red counts only when it is an ASSERTION failure (pytest `E assert` / AssertionError / DID NOT RAISE,
jest/vitest expect(...), node/chai AssertionError, go `x_test.go:N:`). ImportError, ModuleNotFoundError,
SyntaxError, AttributeError, a collection error, skip/xfail, "no tests ran" are NOT_PROVEN: they show the
code is missing, not that the test judges behaviour. Assert the behaviour through the public entry point.
For a new feature use an entry point that exists on the parent (route -> 404, CLI subcommand, DOM query,
registry lookup) so the parent fails on the assert; if there is none, report PARENT_RED as
`n/a — new feature, no entry point on parent` and rely on the gate plus a negative test.
--reached MARKER (off by default): require the red output to contain MARKER, which the test prints right
before the decisive assertion. Use it when the test has several possible failure points.
Runs never retry. --repeat N (default 1) runs each arm N times and requires the same result every time:
use 3+ for a nondeterministic repro (a red that turns green on a rerun is a flaky repro, not a proof).
BASE that is not an ancestor of the fix is resolved to their merge-base.
Test files default to test paths changed between base and fix.
Exit: 0 PASS, 1 FAIL (an arm behaved wrong), 2 NOT_PROVEN (not an assertion red, timeout, missing binary,
skip, marker asked for but not printed).
"""
import argparse
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddlib  # noqa: E402


HOW_TO = ("assert the behaviour (a value, a status, an error caught by the test), not the import; for a new "
          "feature go through an entry point that exists on the parent, or report PARENT_RED as "
          "`n/a — new feature, no entry point on parent`")


def classify_red(code, out, marker, expect):
    if code is None:
        return "NOT_PROVEN", ddlib.none_reason(out)
    empty = ddlib.nothing_ran(out)
    if empty:
        return "NOT_PROVEN", "not red: %s" % empty
    if code == 0:
        return "FAIL", "test passed but must fail here"
    if ddlib.env_failure(code, out):
        return "NOT_PROVEN", "collection/environment error: the test never reached its assertion; " + HOW_TO
    reached = bool(marker) and marker in out
    if marker and not reached:
        return "NOT_PROVEN", ("red, but marker %r not printed: the test failed before its decisive assert; "
                              "print the marker right before it, or drop --reached" % marker)
    kind = ddlib.red_kind(out)
    if kind != "assertion":
        why = kind.split(":", 1)[1] if kind.startswith("foreign:") else "no assertion failure in the output"
        return "NOT_PROVEN", "red is not an assertion failure (%s): %s" % (why, HOW_TO)
    if expect and not re.search(expect, out):
        return "NOT_PROVEN", "red, but output does not match --expect"
    return "PASS", "red by assertion"


def _is_ref(repo, name):
    try:
        root = ddlib.repo_root(repo)
    except RuntimeError:
        return False
    return ddlib.git(["rev-parse", "--verify", "--quiet", name + "^{commit}"], cwd=root, check=False).strip() != ""


def red_arm(a, path, rdir, name, marker):
    """Run --repeat times; every run must be red for the expected reason."""
    exits = []
    for i in range(max(1, a.repeat)):
        code, out = ddlib.run_cmd(a.cmd, path, a.timeout, os.path.join(rdir, "%s_%d.txt" % (name, i)))
        exits.append(code)
        verdict, why = classify_red(code, out, marker, a.expect)
        if verdict != "PASS":
            if i and verdict == "FAIL":
                why = "red is not deterministic: passed on run %d of %d" % (i + 1, a.repeat)
            return {"verdict": verdict, "why": why, "exit": exits}
    return {"verdict": "PASS", "why": "red by assertion in %d/%d runs" % (len(exits), len(exits)), "exit": exits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--fix", default="HEAD")
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--full-cmd")
    ap.add_argument("--test-files", nargs="*")
    ap.add_argument("--expect")
    ap.add_argument("--reached", help="marker the red output must contain (opt-in)")
    ap.add_argument("--no-reached", action="store_true", help="kept for old commands; the marker is off by default")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--receipts")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    marker = None if a.no_reached else a.reached
    fix_note = None
    if a.fix not in ("HEAD", "WORKTREE") and os.path.isdir(a.fix) and (
            os.sep in a.fix or a.fix in (".", "..") or not _is_ref(a.repo, a.fix)):
        fix_note = "--fix %s is a directory: --repo %s --fix WORKTREE" % (a.fix, a.fix)
        a.repo, a.fix = a.fix, "WORKTREE"
    root = ddlib.repo_root(a.repo)
    base_ref, base_note = ddlib.resolve_base(root, a.base)
    base = ddlib.resolve_commit(root, base_ref)
    fix = ddlib.resolve_commit(root, a.fix)
    cfg = ddlib.load_config(root, base)
    changed = ddlib.name_status(root, base, fix)
    if base == fix:
        ddlib.emit({"status": "NOT_PROVEN", "error": "base and fix are the same commit"}, 2)
    tests = a.test_files or [p for st, p in changed if st != "D" and ddlib.is_test_path(p, cfg)]
    src = [(st, p) for st, p in changed if p not in tests]
    if not tests:
        ddlib.emit({"status": "NOT_PROVEN", "error": "no test files changed between base and fix; pass --test-files"}, 2)
    if not src:
        ddlib.emit({"status": "NOT_PROVEN", "error": "fix changes no non-test files: nothing to prove"}, 2)
    rdir = a.receipts or tempfile.mkdtemp(prefix="dd-receipts-")
    os.makedirs(rdir, exist_ok=True)
    res = {"base": base, "base_note": base_note, "fix": fix, "fix_note": fix_note, "repo": root, "repeat": max(1, a.repeat), "test_files": tests,
           "src_files": [p for _, p in src], "marker": marker, "receipts_dir": rdir}

    with ddlib.Worktree(root, base) as wa:
        ddlib.checkout_paths(wa.path, fix, tests)
        tree_a = wa.tree()
        res["armA"] = red_arm(a, wa.path, rdir, "armA", marker)

    with ddlib.Worktree(root, fix) as wb:
        b = {"verdict": "PASS", "why": "green on fix in every run", "exit": []}
        for i in range(max(1, a.repeat)):
            code, out = ddlib.run_cmd(a.cmd, wb.path, a.timeout, os.path.join(rdir, "armB_%d.txt" % i))
            b["exit"].append(code)
            if code is None:
                b.update(verdict="NOT_PROVEN", why="%s on the fix tree" % ddlib.none_reason(out))
                break
            if code != 0 and ddlib.env_failure(code, out):
                b.update(verdict="NOT_PROVEN", why="collection/environment error on the fix tree")
                break
            if ddlib.nothing_ran(out):
                b.update(verdict="NOT_PROVEN", why="not green on fix: %s" % ddlib.nothing_ran(out))
                break
            if code != 0:
                b.update(verdict="FAIL", why="test does not pass on the fix (run %d)" % (i + 1))
                break
        if a.full_cmd and b["verdict"] == "PASS":
            fc, fout = ddlib.run_cmd(a.full_cmd, wb.path, a.timeout, os.path.join(rdir, "armB_full.txt"))
            b["full_exit"] = fc
            if fc != 0:
                env_bad = ddlib.env_failure(fc, fout)
                b.update(verdict="NOT_PROVEN" if env_bad else "FAIL",
                         why=("full suite could not run on fix: %s" % (ddlib.none_reason(fout) if fc is None else
                              "collection/environment error")) if env_bad else "full suite not green on fix")
        b["linked_deps"] = wb.linked
        res["armB"] = b

    base_files = set(ddlib.git(["ls-tree", "-r", "--name-only", "-z", base], cwd=root).split("\0"))
    with ddlib.Worktree(root, fix) as wc:
        ddlib.checkout_paths(wc.path, base, [p for _, p in src if p in base_files])
        for _, p in src:
            if p not in base_files and os.path.lexists(os.path.join(wc.path, p)):
                os.unlink(os.path.join(wc.path, p))
        tree_c = wc.tree()
        res["armC"] = red_arm(a, wc.path, rdir, "armC", marker)
    res["tree_equal"] = tree_a == tree_c
    if not res["tree_equal"]:
        res["armC"].update(verdict="FAIL", why="revert does not reproduce base + tests (tree differs)")

    verdicts = [res["armA"]["verdict"], res["armB"]["verdict"], res["armC"]["verdict"]]
    status = "FAIL" if "FAIL" in verdicts else ("NOT_PROVEN" if "NOT_PROVEN" in verdicts else "PASS")
    res["status"] = status
    ddlib.emit(res, {"PASS": 0, "FAIL": 1, "NOT_PROVEN": 2}[status])


if __name__ == "__main__":
    ddlib.guarded_main(main)
