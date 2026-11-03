#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
# Self-test for guard_diff.py: both halves on throwaway git repos.
#   MUST-FLAG: real weakenings and ungranted edits -> exit 1 (and the expected item in the JSON).
#   MUST-PASS: legitimate work (new tests, more asserts, renames, moves, granted value change, reformat,
#              tests appended to an existing file without a grant = "extended", first runner config = "bootstrap") -> 0.
# Prints one ok/FAIL line per case; exit 1 if any case fails. Usage: bash test_guard_diff.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
GD="$HERE/guard_diff.py"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/guard_diff_test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid \
       GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
PASSES=0; FAILS=0

g() { git -C "$R" -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@" >/dev/null 2>&1; }

seed() {  # seed <name>: fresh repo with one base commit; sets R
  R="$TMP/$1"; mkdir -p "$R/tests" "$R/src" "$R/.github/workflows" "$R/web/__tests__/__snapshots__"
  git init -q -b master "$R"
  cat > "$R/tests/test_calc.py" <<'PY'
import pytest
from src.calc import double


def test_double():
    # doubling
    assert double(2) == 4
    assert double(0) == 0


def test_neg():
    assert double(-1) == -2


class TestGroup:
    def test_in_class(self):
        assert double(3) == 6
        with pytest.raises(TypeError):
            double(None)
PY
  printf 'def double(x):\n    return x * 2\n' > "$R/src/calc.py"
  printf 'on: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n' > "$R/.github/workflows/ci.yml"
  cat > "$R/web/__tests__/sum.test.js" <<'JS'
describe('sum', () => {
  it('adds', () => {
    expect(1 + 1).toBe(2);
  });
  it('zero', () => { expect(0 + 0).toBe(0); });
});
JS
  printf 'exports[`sum 1`] = `2`;\n' > "$R/web/__tests__/__snapshots__/sum.test.js.snap"
  g add -A; g commit -qm base
}

seed_bare() {  # seed_bare <name> [file content]...: repo whose base has NO tests and NO runner config; sets R
  R="$TMP/$1"; shift; mkdir -p "$R/src"; git init -q -b master "$R"
  printf 'def double(x):\n    return x * 2\n' > "$R/src/calc.py"; printf 'export const f = 1;\n' > "$R/src/f.js"
  while [ $# -gt 0 ]; do mkdir -p "$R/$(dirname "$1")"; printf '%s\n' "$2" > "$R/$1"; shift 2; done
  g add -A; g commit -qm base
}

allow() { printf '%s\n' "$@" > "$TMP/allow.txt"; }   # allow <line>...

check() {  # check <name> <want-exit> <grep-in-json or ''> <extra args...>
  local name="$1" want="$2" pat="$3"; shift 3
  local out rc
  out="$(python3 "$GD" --repo "$R" "$@" 2>/dev/null)"; rc=$?
  if [ "$rc" = "$want" ] && { [ -z "$pat" ] || printf '%s' "$out" | grep -q -- "$pat"; }; then
    echo "ok    $name (exit $rc)"; PASSES=$((PASSES+1))
  else
    echo "FAIL  $name: exit $rc, want $want${pat:+, pattern '$pat'}"; printf '%s\n' "$out" | sed 's/^/      /'
    FAILS=$((FAILS+1))
  fi
}

py() { python3 - "$R/$1" "$2" "$3" <<'PY'
import sys; p, a, b = sys.argv[1:]; s = open(p).read(); assert a in s, (a, p); open(p, "w").write(s.replace(a, b, 1))
PY
}

echo "== MUST-FLAG"
seed f1; py tests/test_calc.py 'def test_neg' '@pytest.mark.skip(reason="flaky")
def test_neg'; allow tests/test_calc.py
check "skip added in granted file" 1 '"what": "skip"' --allow "$TMP/allow.txt"

seed f2; py tests/test_calc.py '    assert double(0) == 0
' ''; allow tests/test_calc.py
check "assert removed in granted file" 1 '"scope": "test_double"' --allow "$TMP/allow.txt"

seed f3; py tests/test_calc.py 'def test_neg():
    assert double(-1) == -2
' ''; allow tests/test_calc.py
check "test function deleted" 1 '"detail": "deleted"' --allow "$TMP/allow.txt"

seed f4; sed -i.bak 's/== 4/== 5/' "$R/tests/test_calc.py"; rm "$R/tests/test_calc.py.bak"; allow 'src/*'
check "ungranted edit of existing test via shell" 1 '"modified test file without a grant"' --allow "$TMP/allow.txt"

seed f5; printf '      - run: true\n' >> "$R/.github/workflows/ci.yml"
check "CI workflow edited" 1 '"kind": "ci"'

seed f6; py tests/test_calc.py '    assert double(0) == 0
' ''; py tests/test_calc.py 'assert double(-1) == -2' 'assert double(-1) == -2
    assert double(-2) == -4
    assert double(-3) == -6'; allow tests/test_calc.py
check "assert-count masked by asserts added in another function" 1 '"scope": "test_double"' --allow "$TMP/allow.txt"

seed f7; py web/__tests__/sum.test.js "it('zero'" "it.skip('zero'"; allow 'web/*'
check "JS: it.skip added in granted file" 1 '"what": "skip"' --allow "$TMP/allow.txt"

seed f8; py web/__tests__/sum.test.js "    expect(1 + 1).toBe(2);
" ""; allow 'web/*'
check "JS: expect removed in granted file" 1 '"scope": "sum > adds"' --allow "$TMP/allow.txt"

seed f9; printf 'import os\ncollect_ignore = ["tests"]\n' > "$R/conftest.py"
check "new conftest.py (test config)" 1 '"new config file"'

seed f10; printf 'exports[`sum 1`] = `3`;\n' > "$R/web/__tests__/__snapshots__/sum.test.js.snap"
check "snapshot changed without grant" 1 '"kind": "snapshot"'

seed f11; printf '{"allow_file": ".dd-allow"}\n' > "$R/.dev-discipline.json"; g add -A; g commit -qm cfg
git -C "$R" worktree add -q "$TMP/f11wt" -b w >/dev/null 2>&1
printf 'tests/*\n' > "$TMP/f11wt/.dd-allow"; sed -i.bak 's/== 4/== 5/' "$TMP/f11wt/tests/test_calc.py"
rm "$TMP/f11wt/tests/test_calc.py.bak"; R0="$R"; R="$TMP/f11wt"
check "worktree writer cannot grant itself" 1 '"modified test file without a grant"'
R="$R0"

seed f12; py tests/test_calc.py '        with pytest.raises(TypeError):
            double(None)
' ''; allow tests/test_calc.py
check "pytest.raises removed (counts as assert)" 1 'TestGroup.test_in_class' --allow "$TMP/allow.txt"

seed f13; printf '\n\n@pytest.mark.skip(reason="later")\ndef test_extra():\n    assert double(5) == 10\n' >> "$R/tests/test_calc.py"
allow tests/test_calc.py
check "new skipped test in an existing file" 1 '"detail": "added scope"' --allow "$TMP/allow.txt"

seed f14; py web/__tests__/sum.test.js "it('adds'" "it.only('adds'"; allow 'web/*'
check "JS: .only narrows the suite" 1 '"what": "skip"' --allow "$TMP/allow.txt"

seed f15; py tests/test_calc.py 'def test_double():
    # doubling
    assert double(2) == 4
    assert double(0) == 0' 'def test_doubling_values():
    # doubling
    assert double(2) == 4
    print(double(0))'; allow tests/test_calc.py
check "renamed + an assert turned into print in one change" 1 '"detail": "changed, renamed' --allow "$TMP/allow.txt"

seed f16; py tests/test_calc.py 'def test_neg():
    assert double(-1) == -2
' 'def test_unrelated_new():
    values = {k: double(k) for k in range(5)}
    assert values[1] == 2
    assert len(values) == 5
'; allow tests/test_calc.py
check "deleted test hidden behind a dissimilar new test" 1 '"scope": "test_neg"' --allow "$TMP/allow.txt"

echo "== MUST-FLAG: extended is only for pure additions (no grant in these cases)"
seed x1; printf '\n\ndef test_more():\n    assert double(7) == 14\n' >> "$R/tests/test_calc.py"
py tests/test_calc.py 'assert double(2) == 4' 'assert double(2) == 5'
check "new test appended AND an old assert value edited" 1 '"modified test file without a grant"'

seed x2; py tests/test_calc.py '    # doubling
' '    assert True
    return
'
check "assert + return inserted into an old test (asserts grow, test neutered)" 1 'beyond added asserts'

seed x3; py tests/test_calc.py 'from src.calc import double
' 'from src.calc import double


def double(x):
    return 0
'
check "new def shadows the imported function under test" 1 'new def/class double rebinds'

seed x4; py tests/test_calc.py 'from src.calc import double
' 'from src.calc import double
from os.path import join as double
'
check "new import rebinds an old name" 1 'new import rebinds'

seed x13; py tests/test_calc.py 'from src.calc import double' 'from src.calc import triple as double'
printf '\n\ndef test_triple():\n    assert double(2) == 6\n' >> "$R/tests/test_calc.py"
check "py: existing from-import retargeted (old name rebound)" 1 'new import rebinds'

seed x5; printf '\n\ndef test_neg():\n    assert True\n' >> "$R/tests/test_calc.py"
check "same-name test redefined below (shadows the old one)" 1 'shadows'

seed x6; py tests/test_calc.py '    assert double(-1) == -2' '    x = double(-1)
    assert x == -2
    assert double(-1) == -2'
check "assignment inserted into an old test" 1 'beyond added asserts'

seed x7; py tests/test_calc.py 'import pytest' 'import pytest
TOL = 1e-3'
check "module-level constant added (not an import)" 1 'module level changed'

seed x8; py web/__tests__/sum.test.js "  it('zero'" "  it.skip('later', () => { expect(2).toBe(2); });
  it('zero'"
check "JS: skipped test added to an existing file (extended, still a weakening)" 1 '"detail": "added scope"'

seed x9; py web/__tests__/sum.test.js "    expect(1 + 1).toBe(2);" "    expect(1 + 1).toBe(2);
    expect(0).toBe(0); globalThis.x = 1;"
check "JS: assert + assignment inserted into an old case" 1 'beyond added asserts'

seed x10; printf '[pytest]\naddopts = -q\n' > "$R/pytest.ini"
check "bootstrap refused: base already has tests" 1 '"new config file"'

seed_bare x11 conftest.py 'collect_ignore = []'; printf '[pytest]\naddopts = -q\n' > "$R/pytest.ini"
check "bootstrap refused: base already has runner config" 1 '"new config file"'

seed_bare x12; mkdir -p "$R/.github/workflows"; printf 'on: push\n' > "$R/.github/workflows/ci.yml"
printf '[pytest]\n' > "$R/pytest.ini"
check "bootstrap covers runner config only, not CI" 1 '"kind": "ci"'

echo "== MUST-PASS"
seed p14; py tests/test_calc.py 'def test_neg' '@pytest.mark.skip(reason="x")
def test_neg'; printf 'import pytest\n' > "$R/tests/test_other.py"; g add -A; g commit -qm "skip"
py tests/test_calc.py '@pytest.mark.skip(reason="x")
def test_neg():
    assert double(-1) == -2
' ''; printf 'from src.calc import double\n\n\n@pytest.mark.skip(reason="x")\ndef test_neg():\n    assert double(-1) == -2\n' >> "$R/tests/test_other.py"
allow 'tests/*'
check "skipped test moved to another existing file" 0 '' --allow "$TMP/allow.txt"

seed p1; printf 'from src.calc import double\n\n\ndef test_big():\n    assert double(10) == 20\n' > "$R/tests/test_new.py"
check "new test file" 0 '"tests/test_new.py"'

seed p2; py tests/test_calc.py 'assert double(-1) == -2' 'assert double(-1) == -2
    assert double(-5) == -10'; allow tests/test_calc.py
check "asserts added" 0 '' --allow "$TMP/allow.txt"

seed p3; py tests/test_calc.py 'def test_neg' 'def test_negative_input'; allow tests/test_calc.py
check "pure rename of a test function" 0 '' --allow "$TMP/allow.txt"

seed p4; py tests/test_calc.py 'assert double(2) == 4' 'assert double(2) == 4.0'; allow tests/test_calc.py
check "granted pin value change" 0 '' --allow "$TMP/allow.txt"

seed p5; py tests/test_calc.py '    # doubling' '    # TODO pytest.mark.skip(reason) / assert nothing here
    "assert inside a string does not count"'; allow tests/test_calc.py
check "comment/string-only change" 0 '' --allow "$TMP/allow.txt"

seed p6; python3 - "$R/tests/test_calc.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("    ", "  ").replace("assert double(2) == 4", "assert (\n    double(2)\n    == 4\n  )")
open(p, "w").write(s)
PY
allow tests/test_calc.py
check "reformat/indent change" 0 '' --allow "$TMP/allow.txt"

seed p7; py tests/test_calc.py 'def test_neg():
    assert double(-1) == -2
' ''; allow '# slice 7' 'tests/test_calc.py' '# WEAKEN-OK: tests/test_calc.py negative input dropped by spec v2'
check "WEAKEN-OK marked removal" 0 '"exempted": \[' --allow "$TMP/allow.txt"

seed p8; py tests/test_calc.py 'def test_neg():
    assert double(-1) == -2
' ''; printf 'from src.calc import double\n\n\ndef test_neg():\n    assert double(-1) == -2\n' > "$R/tests/test_neg.py"
allow tests/test_calc.py
check "moving a test to a new file" 0 '' --allow "$TMP/allow.txt"

seed p9; g mv tests/test_calc.py tests/test_calc_moved.py
check "whole test file moved (git mv), ungranted" 0 ''

seed p10; printf 'def double(x):\n    return 2 * x\n' > "$R/src/calc.py"; printf 'scratch\n' > "$R/notes.txt"
check "source-only change and untracked non-test file" 0 '"granted": \[\]'

seed p11; printf '{"allow_file": ".dd-allow"}\n' > "$R/.dev-discipline.json"; g add -A; g commit -qm cfg
printf 'tests/test_calc.py\n' > "$R/.dd-allow"; py tests/test_calc.py 'assert double(2) == 4' 'assert double(2) == 4.0'
check "grant from config allow_file in main checkout" 0 '"path": "tests/test_calc.py"'

seed p12; py web/__tests__/sum.test.js "it('zero'" "it('adds zeros'"; allow 'web/*'
check "JS: test title renamed" 0 '' --allow "$TMP/allow.txt"

seed p13; py tests/test_calc.py 'def test_neg' '@pytest.mark.skip(reason="x")
def test_neg'; g add -A; g commit -qm "skip it"
py tests/test_calc.py '@pytest.mark.skip(reason="x")
' ''; allow tests/test_calc.py
check "skip removed (strengthening)" 0 '' --allow "$TMP/allow.txt"

seed p15; g checkout -q -b feat; g checkout -q -; printf 'def test_m():\n    assert 1\n' > "$R/tests/test_main_only.py"
g add -A; g commit -qm "main moves on"; g checkout -q feat
check "base not an ancestor -> merge-base (main's new test is not 'deleted')" 0 '"note": "base = merge-base' --base master

seed p16; py tests/test_calc.py 'class TestGroup:' 'class TestMovedGroup:'; py tests/test_calc.py 'assert double(3) == 6' 'assert double(3) == 6.0'
allow tests/test_calc.py
check "class renamed and a value changed (same test name)" 0 '' --allow "$TMP/allow.txt"

seed p17; py tests/test_calc.py 'def test_double():
    # doubling
    assert double(2) == 4
    assert double(0) == 0' 'def test_double_keeps_zero_and_sign():
    assert double(2) == 4
    assert double(0) == 0
    assert double(-0) == 0'; allow tests/test_calc.py
check "renamed and rewritten test, asserts kept" 0 '' --allow "$TMP/allow.txt"

echo "== MUST-PASS: extended and bootstrap (no grant)"
seed e1; printf '\n\ndef test_big():\n    assert double(10) == 20\n' >> "$R/tests/test_calc.py"
check "py: new test appended to an existing file, ungranted -> extended" 0 'extended (existing test files[^"]*tests/test_calc.py'

seed e2; py tests/test_calc.py 'import pytest' 'import pytest
import math'; py tests/test_calc.py '    assert double(-1) == -2' '    assert double(-1) == -2
    assert double(-7) == -14; assert math.isfinite(double(1.5))'
py tests/test_calc.py '            double(None)' '            double(None)

    def test_in_class_more(self):
        assert double(4) == 8'
check "py: asserts added to an old test, new import, new method in a class" 0 'tests/test_calc.py'

seed e6; py tests/test_calc.py 'from src.calc import double' 'from src.calc import double, triple'
printf '\n\ndef test_triple():\n    assert triple(2) == 6\n' >> "$R/tests/test_calc.py"
check "py: a name added to an existing from-import for a new test" 0 'extended (existing test files[^"]*tests/test_calc.py'

seed e3; py web/__tests__/sum.test.js "    expect(1 + 1).toBe(2);" "    expect(1 + 1).toBe(2);
    expect(2 + 2).toBe(4);"
py web/__tests__/sum.test.js "  it('zero'" "  it('negatives', () => { expect(-1 + -1).toBe(-2); });
  it('zero'"
check "JS: expect added to an old case and a new case in the suite" 0 'web/__tests__/sum.test.js'

seed_bare e4; printf '[pytest]\naddopts = -q\n' > "$R/pytest.ini"; printf 'import pytest\n' > "$R/conftest.py"
mkdir -p "$R/tests"; printf 'from src.calc import double\n\n\ndef test_d():\n    assert double(2) == 4\n' > "$R/tests/test_calc.py"
check "bootstrap: first pytest.ini + conftest.py + tests in a repo without tests" 0 'bootstrap: base had no tests'

seed_bare e5; printf 'export default {};\n' > "$R/vitest.config.ts"
printf "import { f } from './f';\ntest('f', () => { expect(f).toBe(1); });\n" > "$R/src/f.test.js"
check "bootstrap: first vitest.config.ts" 0 '"vitest.config.ts"'

echo "== NOT_PROVEN and calibration"
seed n1; check "unknown base -> NOT_PROVEN" 2 '"NOT_PROVEN"' --base no-such-ref

seed c1; printf 'from src.calc import double\n\n\ndef test_t():\n    assert double(1) == 2\n' > "$R/tests/test_t.py"
g add -A; g commit -qm "add test"
py tests/test_calc.py '    assert double(0) == 0
' ''; g add -A; g commit -qm "drop assert"
py tests/test_calc.py 'def test_neg' 'def test_negative'; g add -A; g commit -qm "rename test"
printf '\n\ndef test_ten():\n    assert double(5) == 10\n' >> "$R/tests/test_calc.py"; g add -A; g commit -qm "append test"
out="$(python3 "$GD" --repo "$R" --calibrate 5)"; rc=$?
if [ $rc = 0 ] && printf '%s' "$out" | grep -q 'weakening_commits=1 ' \
   && printf '%s' "$out" | grep 'drop assert' | grep -q 'FLAGS: tests/test_calc.py::test_double assert 2->1' \
   && printf '%s' "$out" | grep 'rename test' | grep -q 'weak=0' \
   && printf '%s' "$out" | grep 'append test' | grep -q 'touch=0 ext=1 ' \
   && printf '%s' "$out" | grep -q 'extended_only_commits=1 '; then
  echo "ok    calibrate: 1 flag on 4 commits, rename not flagged, appended test = extended"; PASSES=$((PASSES+1))
else
  echo "FAIL  calibrate (exit $rc)"; printf '%s\n' "$out" | sed 's/^/      /'; FAILS=$((FAILS+1))
fi

echo "test_guard_diff: $PASSES ok, $FAILS FAIL"
[ "$FAILS" = 0 ]
