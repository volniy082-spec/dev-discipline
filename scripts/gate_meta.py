#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Meta-test: every test file is in the gate list or an exception list, every gate entry exists, the
exception lists only shrink.

usage: gate_meta.py [--gate gate.txt] [--tests DIR ...] [--flaky flaky.txt] [--lists exceptions.txt ...]
                    [--base REF] [--repo DIR]
  gate file: one path (file or directory) per line, '#' comments; a directory entry covers files under it.
  exception lists (the flaky list and every --lists / config "shrink_lists" file): a file or directory entry
  covers the test file, which is then reported under "excepted", not as an orphan. A node id
  (`f.py::test_x`) excepts one test only, so the file itself must still be in the gate list.
  --base REF: compare the flaky list and every exception list with their version at REF (ratchet: they
  may only shrink). A list absent at REF counts as empty. An unresolvable REF is NOT_PROVEN, not FAIL.
Defaults come from .dev-discipline.json ("gate", "tests" = dir or [dirs], "flaky", "shrink_lists").
No gate list in the repo: the orphan/missing check is not_checked, the ratchet still runs with --base
(a grown list = FAIL, none grew = PASS + "not_checked"). Nothing to check at all -> NOT_PROVEN.
Exit: 0 PASS, 1 FAIL (orphans / missing / an exception list grew), 2 NOT_PROVEN (nothing checkable, git error).
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddlib  # noqa: E402


def read_list(path):
    with open(path) as f:
        return ddlib._entries(f.read().splitlines())


def list_at(root, ref, path):
    """Entries of PATH at REF (already verified); [] when the file does not exist there."""
    exists = subprocess.run(["git", "cat-file", "-e", "%s:%s" % (ref, path)], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        return []
    return ddlib._entries(ddlib.git(["show", "%s:%s" % (ref, path)], cwd=root).splitlines())


def ratchet(root, base, lists, flaky):
    """(entries now, flaky info, grown non-flaky lists, number of lists compared)."""
    entries, grew_lists, compared = [], {}, 0
    flaky_info = {"now": None, "before": None, "grew": False}
    for lp in lists:
        path = os.path.join(root, lp)
        now = read_list(path) if os.path.exists(path) else None
        entries += now or []
        before = len(list_at(root, base, lp)) if base else None
        if before is not None and (now is not None or before):
            compared += 1
        grew = before is not None and len(now or []) > before
        if lp == flaky:
            flaky_info = {"now": None if now is None else len(now), "before": before, "grew": grew}
        elif grew:
            grew_lists[lp] = {"now": len(now), "before": before}
    return entries, flaky_info, grew_lists, compared


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate")
    ap.add_argument("--tests", nargs="*")
    ap.add_argument("--flaky")
    ap.add_argument("--lists", nargs="*")
    ap.add_argument("--base")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    root = ddlib.repo_root(a.repo)
    cfg = ddlib.load_config(root)
    gate = a.gate or cfg.get("gate", "gate.txt")
    tests = a.tests or cfg.get("tests", "tests")
    flaky = a.flaky or cfg.get("flaky", "flaky.txt")
    base = None
    if a.base:
        try:
            base = ddlib.git(["rev-parse", "--verify", a.base + "^{commit}"], cwd=root).strip()
        except RuntimeError as e:
            ddlib.emit({"status": "NOT_PROVEN", "error": "--base %s does not resolve: %s" % (a.base, e),
                        "report_as": "not_checked: base ref unresolved"}, 2)
    shrink = a.lists if a.lists is not None else cfg.get("shrink_lists", [])
    shrink = [shrink] if isinstance(shrink, str) else list(shrink)
    exc_entries, flaky_info, grew_lists, compared = ratchet(
        root, base, [flaky] + [lp for lp in shrink if lp != flaky], flaky)
    grew = bool(flaky_info["grew"] or grew_lists)

    gpath = os.path.join(root, gate)
    if not os.path.exists(gpath):
        absent = "orphans and missing entries: gate list %s absent" % gate
        if not compared:
            ddlib.emit({"status": "NOT_PROVEN", "error": "gate list %s not found and no exception list "
                        "compared with --base" % gate, "report_as": "not_checked: gate list absent"}, 2)
        ddlib.emit({"status": "FAIL" if grew else "PASS", "gate": None, "lists_compared": compared,
                    "not_checked": [absent], "flaky": flaky_info, "lists_grew": grew_lists}, 1 if grew else 0)

    entries = [ddlib._norm(e).rstrip("/") for e in read_list(gpath)]
    missing = [e for e in entries if not os.path.exists(os.path.join(root, e))]
    exc_paths = [ddlib._norm(e).rstrip("/") for e in exc_entries if "::" not in e]

    tracked = ddlib.git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root).split("\0")
    skip_parts = {"fixtures", "__snapshots__", "testdata", "node_modules"}
    # A test is a file the runner collects (test_*.py, *_test.py, tests.py, *.test.ts ...): helpers such as
    # tests/factories.py are not orphans, and a service named data/ is not excluded.
    test_files = [p for p in tracked if p and os.path.isfile(os.path.join(root, p))
                  and ddlib.is_test_path(p, {"tests": tests}) and ddlib.is_collected_test(p)
                  and not skip_parts & set(p.split("/")[:-1])]
    under = lambda p, es: any(p == e or p.startswith(e + "/") for e in es)
    orphans = [p for p in test_files if not under(p, entries) and not under(p, exc_paths)]
    excepted = [p for p in test_files if not under(p, entries) and under(p, exc_paths)]
    fail = bool(orphans or missing or grew)
    out = {"status": "FAIL" if fail else "PASS", "gate": gate, "test_files": len(test_files),
           "orphans": orphans, "excepted": excepted, "missing": missing, "flaky": flaky_info,
           "lists_grew": grew_lists}
    if not base:
        out["not_checked"] = ["exception-list ratchet: no --base"]
    ddlib.emit(out, 1 if fail else 0)


if __name__ == "__main__":
    ddlib.guarded_main(main)
