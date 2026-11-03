# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""pin: a test that SEARCHES must assert how much it found.

A sweep over a glob, registry or extracted list stays green when its source
degenerates to nothing: the pattern narrowed, the directory moved, the record
format changed, and the loop runs zero times. Pin the count.

Use it only where a test loops over a glob / registry / catalog / extracted list.
Plain example-based tests do not need it.

    from pinned import pin
    files = pin(sorted(ROOT.glob("migrations/*.sql")), 42, "SQL migrations")
    pin(len(registry()), 10, "handlers in registry", mode="at_least")
    pin(len(future_source()), 0, "entries of a not-yet-filled registry")

Raise an exact pin in the SAME commit that adds the items, with a reason for
each new item. Lower it only after showing the code was removed, not the search broken.
Copy this file into your tests (e.g. tests/pinned.py). Stdlib only.
"""
from __future__ import annotations

from typing import Sized, Union


_GREW = ("MORE than expected -> the code grew: update the expected number in the same "
         "commit as the growth, with a reason for each new item.")
_SHRANK = ("FEWER than expected -> check the SEARCH first (pattern, path, record format) "
           "before touching the number: a drop usually means the search broke, not that "
           "code was removed. A test fixed by narrowing its search guards nothing.")


def pin(found: Union[int, Sized], expected: int, what: str, mode: str = "exact"):
    """Assert the count of what a search found. Returns `found` unchanged.

    found    -- an int count, or any sized collection (len() is taken)
    expected -- the pinned number (0 is legal for a deliberately empty source)
    what     -- what was searched for, in words
    mode     -- "exact": count must equal expected;
                "at_least": count must be >= expected (sources that grow freely)
    """
    if mode not in ("exact", "at_least"):
        raise ValueError(f"pin mode must be 'exact' or 'at_least', got {mode!r}")
    if isinstance(found, bool):
        raise TypeError("pin(found=...) got a bool; pass a count or a collection")
    n = found if isinstance(found, int) else len(found)
    if mode == "at_least":
        if n < expected:
            raise AssertionError(f"{what}: found {n}, expected at least {expected}.\n  {_SHRANK}")
        return found
    if n > expected:
        raise AssertionError(f"{what}: found {n}, expected exactly {expected}.\n  {_GREW}")
    if n < expected:
        raise AssertionError(f"{what}: found {n}, expected exactly {expected}.\n  {_SHRANK}")
    return found


if __name__ == "__main__":  # two-sided selftest: python3 pinned.py
    assert pin(3, 3, "x") == 3
    assert pin([1, 2], 2, "x") == [1, 2]
    assert pin(5, 3, "x", mode="at_least") == 5
    assert pin(0, 0, "empty future source") == 0
    for args, kw, needle in [((4, 3, "x"), {}, "code grew"), ((2, 3, "x"), {}, "SEARCH"),
                             ((1, 3, "x"), {"mode": "at_least"}, "SEARCH"), (([], 1, "x"), {}, "SEARCH")]:
        try:
            pin(*args, **kw)
        except AssertionError as e:
            assert needle in str(e), (needle, str(e))
        else:
            raise SystemExit(f"FAIL: pin{args} {kw} did not raise")
    print("pinned selftest: PASS")
