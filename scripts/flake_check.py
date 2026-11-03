#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Run a test N times without retries to measure flakiness, or to accept a flaky fix only at 0/N.

usage: flake_check.py --cmd "pytest -q tests/test_x.py::test_y" [--runs N | --rate 0.02 --confidence 0.95]
                      [--stop-on-fail] [--timeout 300] [--repo DIR]
N defaults to the number of runs needed to see at least one failure of a test failing with probability
--rate at the given --confidence: N = ceil(ln(1-confidence) / ln(1-rate)); 2% at 95% -> 149 runs.
Ten runs detect a 2% flake only ~18% of the time.
A timeout counts as a failure. Any run that never reached the tests (collection error, all skipped,
0 tests) makes a 0-failure result NOT_PROVEN.
Runner retries must be off in --cmd (--retries=0, no jest.retryTimes); CI is stripped from the env.
--cmd runs through `bash -c`. The environment is NOT pinned (unlike prove_fix): each run gets its own
PYTHONHASHSEED and a rotated TZ, and LC_ALL stays as the caller has it, so set-order, timezone and locale
flakes show up. The JSON lists each run's env ("env_runs"); rerun a failure with that env to reproduce it.
Slow tests: --rate 0.05 (59 runs) or --stop-on-fail, and state the power line in the report.
Exit: 0 = 0/N failures, 1 = at least one failure or timeout (flaky or broken), 2 = could not run.
"""
import argparse
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddlib  # noqa: E402


def runs_needed(rate, confidence):
    return int(math.ceil(math.log(1 - confidence) / math.log(1 - rate)))


TZ_ROTATION = ["UTC", "America/Los_Angeles", "Asia/Kolkata", "Pacific/Chatham", "Europe/Moscow",
               "America/St_Johns", "Australia/Adelaide", "Pacific/Kiritimati"]


def run_env(i, rng):
    """Per-run variation of the nondeterminism sources prove_fix pins."""
    return {"PYTHONHASHSEED": str(rng.randint(1, 2 ** 32 - 1)), "TZ": TZ_ROTATION[i % len(TZ_ROTATION)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--runs", type=int)
    ap.add_argument("--rate", type=float, default=0.02)
    ap.add_argument("--confidence", type=float, default=0.95)
    ap.add_argument("--stop-on-fail", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    n = a.runs or runs_needed(a.rate, a.confidence)
    rdir = tempfile.mkdtemp(prefix="dd-flake-")
    fails, timeouts, env_errors, first_fail = 0, 0, 0, None
    rng, env_runs = random.SystemRandom(), []
    lc_all = os.environ.get("LC_ALL")
    for i in range(n):
        receipt = os.path.join(rdir, "run%03d.txt" % i)
        extra = run_env(i, rng)
        code, out = ddlib.run_cmd(a.cmd, os.path.abspath(a.repo), a.timeout, receipt, env_extra=extra, pin=False)
        env_runs.append(dict(extra, run=i, exit=code))
        if code is None and "[dev-discipline] TIMEOUT" in out:
            fails += 1  # a hang is the commonest flaky class (async wait), not an environment error
            timeouts += 1
            first_fail = first_fail or receipt
        elif code is None or (code != 0 and ddlib.env_failure(code, out)) or (code == 0 and ddlib.nothing_ran(out)):
            env_errors += 1
            if env_errors >= 3 and fails == 0:
                ddlib.emit({"status": "NOT_PROVEN", "error": "command does not run: %s" % (
                    ddlib.none_reason(out) if code is None else "collection/environment error or nothing ran"),
                    "receipt": receipt, "env_runs": env_runs}, 2)
            continue
        elif code != 0:
            fails += 1
            first_fail = first_fail or receipt
        if fails and a.stop_on_fail:
            n = i + 1
            break
    n_eff = n - env_errors
    detect = 1 - (1 - a.rate) ** n_eff
    # 0/N counts only when every run reached the tests: a skipped run is not a green run.
    status = "FAIL" if fails else ("NOT_PROVEN" if env_errors else "PASS")
    ddlib.emit({"status": status, "runs": n, "runs_effective": n_eff, "failures": fails, "timeouts": timeouts,
                "env_errors": env_errors, "observed_rate": round(fails / float(max(n_eff, 1)), 4),
                "power": "P(detect a %.1f%% flake in %d runs) = %.2f" % (a.rate * 100, n_eff, detect),
                "first_failure_receipt": first_fail, "receipts_dir": rdir,
                "env": {"pinned": False, "LC_ALL": lc_all, "varied": ["PYTHONHASHSEED", "TZ"]},
                "env_runs": env_runs},
               {"PASS": 0, "FAIL": 1, "NOT_PROVEN": 2}[status])


if __name__ == "__main__":
    ddlib.guarded_main(main)
