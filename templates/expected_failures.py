# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Two-sided registry of known failures for a sweep test (pytest).

Instead of `pytest.skip` on a case that fails, list it in EXPECTED_FAILURES with a
fragment of its error. Then:
  - an unexpected failure                         -> FAIL
  - an expected failure that now passes           -> FAIL (remove its line: it is fixed)
  - an expected failure with a different reason   -> FAIL (a new defect hides behind an old one)
  - a registry key that is not a case any more    -> FAIL (the registry does not rot)
The registry is a shrink-only list: lines leave when cases get fixed, a new line
needs a reason and the task contract (references/oracle-protection.md).

Adapt: replace discover_cases() and run_case() with your sweep; keep the four rules.
Run the demo: python3 -m pytest -q templates/expected_failures.py
(the demo's own registry is consistent, so it is green; edit it to see each rule fire).
"""
from __future__ import annotations

import pytest

try:
    from pinned import pin  # templates/pinned.py copied next to the tests
except ImportError:  # demo fallback
    def pin(found, expected, what, mode="exact"):
        n = found if isinstance(found, int) else len(found)
        assert (n >= expected) if mode == "at_least" else (n == expected), f"{what}: {n} vs {expected}"
        return found

# case_id -> fragment that must appear in the error. Reason and responsible person in the comment.
EXPECTED_FAILURES: dict[str, str] = {
    "case_c": "division by zero",  # issue 412: zero-capacity input not supported yet
}


# --- replace these two with the real sweep ---------------------------------------------
def discover_cases() -> dict[str, dict]:
    """The source of truth for the sweep (a registry, a glob of fixture files, ...)."""
    return {
        "case_a": {"total": 10, "parts": 2},
        "case_b": {"total": 9, "parts": 3},
        "case_c": {"total": 5, "parts": 0},
    }


def run_case(case: dict) -> float:
    return case["total"] / case["parts"]
# ----------------------------------------------------------------------------------------


CASES = discover_cases()


def test_case_count_pinned():
    # The sweep must not degenerate to zero cases (references/gate-integrity.md, section 6).
    pin(CASES, 3, "cases in the sweep")


def test_registry_has_no_stale_keys():
    stale = sorted(set(EXPECTED_FAILURES) - set(CASES))
    assert not stale, f"EXPECTED_FAILURES names cases that no longer exist: {stale}; remove them"


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case(case_id):
    expected = EXPECTED_FAILURES.get(case_id)
    try:
        run_case(CASES[case_id])
    except Exception as e:  # noqa: BLE001 -- the sweep judges every error class
        msg = f"{type(e).__name__}: {e}"
        if expected is None:
            pytest.fail(f"{case_id}: unexpected failure: {msg}")
        if expected not in msg:
            pytest.fail(f"{case_id}: expected failure changed reason.\n"
                        f"  registry: {expected!r}\n  actual:   {msg!r}")
        return  # known failure, same reason: accepted and visible in the registry
    if expected is not None:
        pytest.fail(f"{case_id}: listed in EXPECTED_FAILURES ({expected!r}) but now passes; "
                    f"remove the line in this commit")
