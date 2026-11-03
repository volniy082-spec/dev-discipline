#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Re-execute the commands behind the key numbers of an agent's report and compare.

usage: reexec_claims.py claims.json [--timeout 900] [--repo DIR]
claims.json is a JSON list, one object per number the report states:
  [{"name": "tests passed",                  optional, shown in the output
    "cmd": "python3 -m pytest -q | tail -1",  required, the command from the report, verbatim
    "extract": "(\\d+) passed",              optional, regex with one group over stdout+stderr;
                                              the last match is compared
    "reported": "42"},                       required, the value the report claims (string or number)
   {"name": "gate exit", "cmd": "GATE=1 python3 -m pytest -q", "reported": 0}]
  Without "extract" the exit code is compared with "reported".
Each cmd runs through `bash -c` (pipes, `&&`, `cd`, `VAR=x cmd` work) in --repo, which must be the
checkout the report describes: for a writer subagent its worktree (`--repo <worktree>`), not the main one.
A number in a report is a model output until an instrument reproduces it.
WARNING: every cmd from claims.json runs via `bash -c` with your environment (tokens, keys in env included):
only run claims from reports you trust, and read each cmd first.
Exit: 0 all match, 1 any mismatch, 2 a command did not run (timeout, binary not found) / extract found
nothing / claims.json has the wrong shape.
"""
import argparse
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddlib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("claims")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    with open(a.claims) as f:
        claims = json.load(f)
    bad = [i for i, c in enumerate(claims if isinstance(claims, list) else [None])
           if not isinstance(c, dict) or not isinstance(c.get("cmd"), str) or "reported" not in c]
    if not isinstance(claims, list) or bad:
        ddlib.emit({"status": "NOT_PROVEN", "error": "claims.json must be a list of {cmd, reported[, extract, "
                    "name]}; bad entries: %s" % bad}, 2)
    rdir = tempfile.mkdtemp(prefix="dd-claims-")
    rows, worst = [], 0
    for i, c in enumerate(claims):
        code, out = ddlib.run_cmd(c["cmd"], os.path.abspath(a.repo), a.timeout, os.path.join(rdir, "claim%d.txt" % i))
        why = None
        if code is None:
            actual, verdict, why = None, "NOT_PROVEN", ddlib.none_reason(out)
        elif c.get("extract"):
            m = re.findall(c["extract"], out)
            actual = m[-1] if m else None
            verdict = "NOT_PROVEN" if actual is None else ("MATCH" if str(actual) == str(c["reported"]) else "MISMATCH")
        else:
            actual = str(code)
            verdict = "MATCH" if actual == str(c["reported"]) else "MISMATCH"
        worst = max(worst, {"MATCH": 0, "MISMATCH": 1, "NOT_PROVEN": 2}[verdict])
        rows.append({"name": c.get("name", c["cmd"]), "reported": c["reported"], "actual": actual,
                     "verdict": verdict, "why": why, "receipt": os.path.join(rdir, "claim%d.txt" % i)})
    status = {0: "PASS", 1: "FAIL", 2: "NOT_PROVEN"}[worst]
    if worst == 2 and any(r["verdict"] == "MISMATCH" for r in rows):
        status, worst = "FAIL", 1
    ddlib.emit({"status": status, "claims": rows}, worst)


if __name__ == "__main__":
    ddlib.guarded_main(main)
