#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
# Self-test of the dev-discipline scripts on a throwaway git repo. Needs git, python3 + pytest.
# Every script gets a BLOCK case (bad input -> FAIL/NOT_PROVEN) and a PASS case (good input -> 0).
# usage: selftest.sh        Exit 0 = every case behaved as expected.
# No `set -e`: many cases run a command that is meant to fail and then read $?. Setup steps are guarded
# explicitly instead, so a failed mktemp/cd/git init can never run git add/commit/stash/reset in the
# caller's directory.
set -u
S="$(cd "$(dirname "$0")" && pwd)" || { echo "selftest: cannot resolve script dir (NOT_PROVEN)"; exit 2; }
T=$(mktemp -d "${TMPDIR:-/tmp}/dd-selftest.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] \
  || { echo "selftest: mktemp failed (NOT_PROVEN)"; exit 2; }
trap 'rm -rf "$T"' EXIT
# Isolate git from the user's system/global config (signing, hooks, templates) and identity.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid \
       GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
fails=0; total=0
check() { # name expected actual
  total=$((total+1))
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: expected $2, got $3"; fails=$((fails+1)); fi
}
python3 -c 'import pytest' 2>/dev/null || { echo "selftest: pytest is not installed (NOT_PROVEN)"; exit 2; }

cd "$T" && git init -q repo && cd repo || { echo "selftest: setup failed (NOT_PROVEN)"; exit 2; }
# Abort unless we are inside the fresh temp repo: everything below runs git add/commit/stash/reset here.
[ "$(pwd -P)" = "$(cd "$T/repo" && pwd -P)" ] && [ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(pwd -P)" ] \
  || { echo "selftest: not inside the temp repo $T/repo (NOT_PROVEN)"; exit 2; }
mkdir tests
printf 'def discount(price, pct):\n    return price - price * pct / 10\n' > calc.py
printf 'from calc import discount\n\ndef test_zero():\n    assert discount(50, 0) == 50\n' > tests/test_basic.py
printf 'tests/test_basic.py\n' > gate.txt
git add -A && git commit -qm base; BASE=$(git rev-parse HEAD)
fix() { sed -i.bak 's#/ 10#/ 100#' calc.py && rm -f calc.py.bak; }
fix
printf 'from calc import discount\n\ndef test_twenty():\n    r = discount(50, 20)\n    print("REACHED")\n    assert r == 40\n' > tests/test_discount.py
echo tests/test_discount.py >> gate.txt
git add -A && git commit -qm fix; MAIN=$(git rev-parse --abbrev-ref HEAD)
CMD="python3 -m pytest -q tests/test_discount.py"
pf() { python3 "$S/prove_fix.py" "$@" >/dev/null 2>&1; echo $?; }
branch() { git checkout -q -b "$1" "$BASE"; }   # new branch from base

# ---- prove_fix ------------------------------------------------------------------------------------
check "prove_fix: assertion red -> green -> red = PASS" 0 "$(pf --base "$BASE" --cmd "$CMD" --expect "== 40")"
branch vac; fix
printf 'from calc import discount\ndef test_v():\n    r = discount(50, 0)\n    print("REACHED")\n    assert r == 50\n' > tests/test_v.py
git add -A && git commit -qm v
check "prove_fix: vacuous test (green on base) = FAIL" 1 "$(pf --base "$BASE" --cmd "python3 -m pytest -q tests/test_v.py")"
branch nomark; fix
printf 'from calc import discount\ndef test_n():\n    assert discount(50, 20) == 40\n' > tests/test_n.py
git add -A && git commit -qm n
check "prove_fix: --reached REACHED, marker not printed = NOT_PROVEN" 2 "$(pf --base "$BASE" --reached REACHED --cmd "python3 -m pytest -q tests/test_n.py")"
check "prove_fix: marker off by default, assertion red = PASS" 0 "$(pf --base "$BASE" --cmd "python3 -m pytest -q tests/test_n.py")"
check "prove_fix: env prefix in --cmd (bash -c) = PASS" 0 "$(pf --base "$BASE" --cmd "GATE=1 python3 -m pytest -q tests/test_n.py")"
check "prove_fix: --no-reached, assertion red = PASS" 0 "$(pf --base "$BASE" --no-reached --cmd "python3 -m pytest -q tests/test_n.py")"
branch imp; fix; printf '\ndef net(price, pct):\n    return discount(price, pct)\n' >> calc.py
printf 'from calc import net\ndef test_i():\n    print("REACHED")\n    assert net(50, 20) == 40\n' > tests/test_i.py
git add -A && git commit -qm imp
check "prove_fix: ImportError red (collection) = NOT_PROVEN" 2 "$(pf --base "$BASE" --no-reached --cmd "python3 -m pytest -q tests/test_i.py")"
python3 "$S/prove_fix.py" --base "$BASE" --cmd "python3 -m pytest -q tests/test_i.py" 2>/dev/null | grep -q 'entry point that exists on the parent'
check "prove_fix: non-assertion red says how to fix (entry point / n/a)" 0 $?
printf 'import calc\ndef test_a():\n    print("REACHED")\n    assert calc.net(50, 20) == 40\n' > tests/test_i.py
git add -A && git commit -qm attr
check "prove_fix: AttributeError red in test body = NOT_PROVEN" 2 "$(pf --base "$BASE" --cmd "python3 -m pytest -q tests/test_i.py")"
printf 'import pytest, calc\ndef test_s():\n    if not hasattr(calc, "net"):\n        pytest.skip("no net")\n    print("REACHED")\n    assert calc.net(50, 20) == 40\n' > tests/test_i.py
git add -A && git commit -qm skip
check "prove_fix: skip on base = NOT_PROVEN" 2 "$(pf --base "$BASE" --no-reached --cmd "python3 -m pytest -q tests/test_i.py")"
git checkout -q -b wt "$BASE"; fix; git show "$MAIN:tests/test_discount.py" > tests/test_discount.py
check "prove_fix: uncommitted fix (WORKTREE) = PASS" 0 "$(pf --base "$BASE" --fix WORKTREE --cmd "$CMD")"
[ -n "$(git status --porcelain)" ]; check "prove_fix: WORKTREE leaves the tree untouched" 0 $?
check "prove_fix: missing runner = NOT_PROVEN" 2 "$(pf --base "$BASE" --fix WORKTREE --cmd "nonexistent-runner-xyz tests/test_discount.py")"
python3 "$S/prove_fix.py" --base "$BASE" --fix WORKTREE --cmd "nonexistent-runner-xyz x" 2>/dev/null | grep -q 'binary not found: nonexistent-runner-xyz'
check "prove_fix: missing runner reported as binary not found" 0 $?
REPO=$PWD
check "prove_fix: --fix DIR (from another cwd) = --repo DIR --fix WORKTREE, PASS" 0 "$(cd "$T" && pf --base "$BASE" --fix "$REPO" --cmd "$CMD")"
check "prove_fix: --fix that is neither ref nor dir = NOT_PROVEN" 2 "$(pf --base "$BASE" --fix "$T/no-such-dir" --cmd "$CMD")"
git stash -u -q && git stash drop -q
# a fix about SyntaxError is provable when the red is an assertion; a crash red is not a proof
git checkout -q "$MAIN" && git checkout -q -b syn
printf 'def is_valid(src):\n    return True\n' > val.py && git add val.py && git commit -qm val; SB=$(git rev-parse HEAD)
printf 'def is_valid(src):\n    try:\n        compile(src, "x", "eval")\n    except SyntaxError:\n        return False\n    return True\n' > val.py
printf 'from val import is_valid\ndef test_syntaxerror_input_is_invalid():\n    print("REACHED")\n    assert is_valid("1 +") is False\n' > tests/test_val.py
check "prove_fix: SyntaxError-themed fix, assertion red = PASS" 0 "$(pf --base "$SB" --fix WORKTREE --cmd "python3 -m pytest -q tests/test_val.py")"
git stash -u -q && git stash drop -q
printf 'def ratio(a, b):\n    return a / b\n' > ratio.py && git add ratio.py && git commit -qm ratio; RB=$(git rev-parse HEAD)
printf 'def ratio(a, b):\n    return a / b if b else 0.0\n' > ratio.py
printf 'from ratio import ratio\ndef test_zero_div():\n    print("REACHED")\n    assert ratio(1, 0) == 0.0\n' > tests/test_ratio.py
check "prove_fix: exception red (ZeroDivisionError) = NOT_PROVEN" 2 "$(pf --base "$RB" --fix WORKTREE --cmd "python3 -m pytest -q tests/test_ratio.py")"
printf 'import pytest\nfrom ratio import ratio\ndef test_zero_div():\n    try:\n        r = ratio(1, 0)\n    except ZeroDivisionError:\n        r = "raised"\n    print("REACHED")\n    assert r == 0.0\n' > tests/test_ratio.py
check "prove_fix: same fix, behaviour asserted = PASS" 0 "$(pf --base "$RB" --fix WORKTREE --cmd "python3 -m pytest -q tests/test_ratio.py")"
git stash -u -q && git stash drop -q
# a red that turns green on a rerun is not a proof (--repeat for nondeterministic repros)
branch fl; fix
printf 'import os\nfrom calc import discount\ndef test_f():\n    p = os.environ["DD_CNT"]\n    n = int(open(p).read()) if os.path.exists(p) else 0\n    open(p, "w").write(str(n + 1))\n    print("REACHED")\n    assert n %% 2 == 1 or discount(50, 20) == 40\n' > tests/test_fl.py
git add -A && git commit -qm fl
check "prove_fix: flaky red with --repeat 3 = FAIL" 1 "$(DD_CNT="$T/cnt" pf --base "$BASE" --repeat 3 --cmd "python3 -m pytest -q tests/test_fl.py")"
# base that is not an ancestor resolves to the merge-base
git checkout -q "$MAIN"; git checkout -q -b side "$BASE"; printf 'x = 1\n' > other.py && git add -A && git commit -qm side
git checkout -q "$MAIN"
out=$(python3 "$S/prove_fix.py" --base side --cmd "$CMD" 2>/dev/null); c=$?
echo "$out" | grep -q merge-base; check "prove_fix: non-ancestor base -> merge-base, PASS" "0 0" "$c $?"

# ---- runner-output classifier ---------------------------------------------------------------------
rk() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ddlib; print(ddlib.red_kind(sys.argv[2]))' "$S" "$1"; }
nr() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ddlib; print(bool(ddlib.nothing_ran(sys.argv[2])))' "$S" "$1"; }
check "red_kind: jest expect" assertion "$(rk $'  expect(received).toBe(expected)\n\n    Expected: 3\n    Received: 2')"
check "red_kind: node assert" assertion "$(rk 'AssertionError [ERR_ASSERTION]: 2 == 3')"
check "red_kind: pytest E assert" assertion "$(rk $'E       assert 2 == 3\nFAILED t.py::test_x - assert 2 == 3')"
check "red_kind: go t.Errorf" assertion "$(rk $'--- FAIL: TestX (0.00s)\n    x_test.go:12: got 2, want 3')"
check "red_kind: ModuleNotFoundError" "foreign:ModuleNotFoundError" "$(rk "E   ModuleNotFoundError: No module named 'x'")"
check "red_kind: node TypeError" "foreign:TypeError" "$(rk 'TypeError: calc.net is not a function')"
check "nothing_ran: all skipped" True "$(nr '1 skipped in 0.01s')"
check "nothing_ran: jest all skipped" True "$(nr 'Tests:       2 skipped, 2 total')"
check "nothing_ran: unittest OK (skipped=1)" True "$(nr $'Ran 1 test in 0.000s\n\nOK (skipped=1)')"
check "nothing_ran: real run" False "$(nr '1 failed, 2 passed in 0.03s')"
gm() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ddlib
def f(): raise AttributeError("boom")
ddlib.guarded_main(f)' "$S" >/dev/null 2>&1; echo $?; }
check "guarded_main: any crash = NOT_PROVEN (2), not 1" 2 "$(gm)"
tp() { python3 -c 'import sys, json; sys.path.insert(0, sys.argv[1]); import ddlib
print(ddlib.is_test_path(sys.argv[2], {"tests": json.loads(sys.argv[3])}))' "$S" "$1" "$2"; }
check "is_test_path: tests as list, second dir" True "$(tp itests/helpers.py '["tests", "itests"]')"
check "is_test_path: tests as list, outside" False "$(tp src/helpers.py '["tests", "itests"]')"
check "is_test_path: tests as string" True "$(tp itests/helpers.py '"itests"')"

# ---- gate_meta ------------------------------------------------------------------------------------
git checkout -q "$MAIN"
python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: clean" 0 $?
printf 'def test_o():\n    pass\n' > tests/test_orphan.py
python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: orphan test = FAIL" 1 $?
rm tests/test_orphan.py
echo "tests/test_basic.py::test_zero  # inc-1" > flaky.txt
python3 "$S/gate_meta.py" --base HEAD >/dev/null; check "gate_meta: flaky list grew = FAIL" 1 $?
rm flaky.txt
printf 'def make():\n    return 1\n' > tests/factories.py
python3 "$S/gate_meta.py" | grep -q factories; check "gate_meta: helper module is not an orphan" 1 $?
rm tests/factories.py
mkdir -p services/data/tests && printf 'def test_l():\n    assert 1\n' > services/data/tests/test_loader.py
python3 "$S/gate_meta.py" | grep -q services/data/tests/test_loader.py; check "gate_meta: test under data/ is an orphan" 0 $?
rm -rf services
echo tests/gone.py >> gate.txt
python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: gate entry for a missing file = FAIL" 1 $?
git checkout -q gate.txt
mv gate.txt ../gate.bak; python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: no gate list = NOT_PROVEN" 2 $?
echo "tests/test_basic.py  # inc-2" > flaky.txt
python3 "$S/gate_meta.py" --base HEAD >/dev/null; check "gate_meta: no gate list, flaky grew = FAIL" 1 $?
git add flaky.txt && git commit -qm flaky
python3 "$S/gate_meta.py" --base HEAD >/dev/null; check "gate_meta: no gate list, flaky same = PASS" 0 $?
git reset -q --hard HEAD~1
mv ../gate.bak gate.txt
python3 "$S/gate_meta.py" --base no-such-ref >/dev/null; check "gate_meta: unresolvable --base = NOT_PROVEN" 2 $?
printf 'def test_o():\n    pass\n' > tests/test_vat.py
echo "tests/test_vat.py  # flaky; return when fixed" > flaky.txt
out=$(python3 "$S/gate_meta.py"); c=$?
echo "$out" | grep -q '"excepted": \[' ; check "gate_meta: test in flaky list = excepted, PASS" "0 0" "$c $?"
echo "tests/test_vat.py::test_o  # one test only" > flaky.txt
python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: node id in flaky list does not cover the file = FAIL" 1 $?
rm -f flaky.txt tests/test_vat.py
mkdir itests && printf 'def test_i():\n    pass\n' > itests/test_int.py
echo '{"tests": ["tests", "itests"]}' > .dev-discipline.json
python3 "$S/gate_meta.py" | grep -q itests/test_int.py; check "gate_meta: config tests as list, orphan in 2nd dir found" 0 $?
echo itests >> gate.txt
python3 "$S/gate_meta.py" >/dev/null; check "gate_meta: config tests as list, covered = PASS" 0 $?
git checkout -q gate.txt; rm -rf itests .dev-discipline.json

# ---- reexec_claims --------------------------------------------------------------------------------
printf '[{"name":"passed","cmd":"python3 -m pytest -q","extract":"(\\\\d+) passed","reported":"2"}]' > ../c1.json
python3 "$S/reexec_claims.py" ../c1.json >/dev/null; check "reexec_claims: match" 0 $?
printf '[{"name":"passed","cmd":"python3 -m pytest -q","extract":"(\\\\d+) passed","reported":"42"}]' > ../c2.json
python3 "$S/reexec_claims.py" ../c2.json >/dev/null; check "reexec_claims: mismatch = FAIL" 1 $?
printf '[{"name":"x","cmd":"no-such-binary-xyz","reported":"0"}]' > ../c3.json
python3 "$S/reexec_claims.py" ../c3.json >/dev/null; check "reexec_claims: command does not run = NOT_PROVEN" 2 $?
printf '[{"name":"pipe","cmd":"GATE=1 python3 -m pytest -q | tail -1","extract":"(\\\\d+) passed","reported":2}]' > ../c4.json
python3 "$S/reexec_claims.py" ../c4.json >/dev/null; check "reexec_claims: pipe + env prefix (bash -c) = match" 0 $?
printf '[{"name":"pipe","cmd":"python3 -m pytest -q | tail -1","extract":"(\\\\d+) passed","reported":3}]' > ../c5.json
python3 "$S/reexec_claims.py" ../c5.json >/dev/null; check "reexec_claims: pipe, wrong number = FAIL" 1 $?
printf '{"cmd":"true"}' > ../c6.json
python3 "$S/reexec_claims.py" ../c6.json >/dev/null; check "reexec_claims: wrong claims.json shape = NOT_PROVEN" 2 $?

# ---- flake_check ----------------------------------------------------------------------------------
printf 'import random, sys\nsys.exit(1 if random.random() < 0.3 else 0)\n' > ../flaky.py
python3 "$S/flake_check.py" --cmd "python3 ../flaky.py" --runs 40 >/dev/null; check "flake_check: 30 percent flake = FAIL" 1 $?
python3 "$S/flake_check.py" --cmd "true" --runs 20 >/dev/null; check "flake_check: 0/N = PASS" 0 $?
python3 "$S/flake_check.py" --cmd "no-such-binary-xyz" --runs 5 >/dev/null; check "flake_check: missing cmd = NOT_PROVEN" 2 $?
python3 "$S/flake_check.py" --cmd "sleep 5" --runs 2 --timeout 1 >/dev/null; check "flake_check: timeout counts as failure" 1 $?
printf 'import pytest\ndef test_sk():\n    pytest.skip("x")\n' > ../test_skip_only.py
python3 "$S/flake_check.py" --cmd "python3 -m pytest -q -p no:cacheprovider ../test_skip_only.py" --runs 3 >/dev/null
check "flake_check: all-skipped runs = NOT_PROVEN" 2 $?
printf 'import sys, time\nsys.exit(0 if time.strftime("%%z") == "+0000" else 1)\n' > ../tzdep.py
TZ=UTC python3 "$S/flake_check.py" --cmd "python3 ../tzdep.py" --runs 4 >/dev/null; check "flake_check: TZ-dependent test is not hidden by a pinned TZ = FAIL" 1 $?
printf 'import os, sys\nsys.exit(1 if os.environ.get("PYTHONHASHSEED") == "0" else 0)\n' > ../seed.py
python3 "$S/flake_check.py" --cmd "python3 ../seed.py" --runs 5 >/dev/null; check "flake_check: hash seed not pinned to 0 = PASS" 0 $?
n=$(python3 "$S/flake_check.py" --cmd true --runs 3 | python3 -c 'import json,sys;r=json.load(sys.stdin)["env_runs"];print(len(r), len({x["TZ"] for x in r}), len({x["PYTHONHASHSEED"] for x in r}))')
check "flake_check: per-run env in JSON (3 runs, TZ and seed vary)" "3 3 3" "$n"
n=$(python3 "$S/flake_check.py" --cmd true | python3 -c 'import json,sys;print(json.load(sys.stdin)["runs"])')
check "flake_check: default 149 runs (2% at 95%)" 149 "$n"

# ---- tree_hash ------------------------------------------------------------------------------------
idx_before=$(git ls-files -s | shasum); st_before=$(git status --porcelain | shasum)
h0=$(bash "$S/tree_hash.sh"); check "tree_hash: clean tree = HEAD^{tree}" "$(git rev-parse 'HEAD^{tree}')" "$h0"
echo new > untracked.txt
h1=$(bash "$S/tree_hash.sh"); [ "$h1" != "$h0" ]; check "tree_hash: untracked file changes the hash" 0 $?
check "tree_hash: same content, same hash" "$h1" "$(bash "$S/tree_hash.sh" "$PWD/tests")"
printf 'ignored.log\n' > .gitignore; h2=$(bash "$S/tree_hash.sh"); echo junk > ignored.log
check "tree_hash: ignored file does not change the hash" "$h2" "$(bash "$S/tree_hash.sh")"
check "tree_hash: real index untouched" "$idx_before" "$(git ls-files -s | shasum)"
st_now=$(git status --porcelain | grep -v -e untracked.txt -e .gitignore | shasum)
check "tree_hash: status untouched" "$st_before" "$st_now"
git add -A; check "tree_hash: equals git add -A && git write-tree" "$h2" "$(git write-tree)"
git reset -q; rm -f untracked.txt .gitignore ignored.log
bash "$S/tree_hash.sh" "$T" >/dev/null 2>&1; check "tree_hash: not a repository = exit 2" 2 $?

# ---- check_report ---------------------------------------------------------------------------------
TREE=$(bash "$S/tree_hash.sh")
cat > ../ok.md <<EOF
# REPORT demo · попытка 1
EXIT: DONE
BRIEF: /tmp/brief.md
WORKTREE: /tmp/wt
SHA: $BASE
TREE: $TREE
HYPOTHESIS: confirmed — the divisor was wrong
ROOT: the percent divisor, calc.py:2
CHANGED: calc.py, tests/test_discount.py
CONTRACT_EDITS: none
INVARIANT: tests/test_discount.py::test_twenty
MEASURE:
  cmd: \`python3 -m pytest -q tests/test_discount.py\`
  before: 1 failed
  after: 1 passed
PARENT_RED:
  cmd: \`python3 scripts/prove_fix.py --base $BASE --cmd "python3 -m pytest -q tests/test_discount.py"\`
  expected: exit 1 by assert
  fact: "armA": {"verdict": "PASS", "why": "red by assertion in 1/1 runs"}
GATE:
  line: 2 passed in 0.02s
  log: /tmp/gate_1.txt
CRITERIA:
- discount 20% of 50 is 40: PASS — \`python3 -m pytest -q tests/test_discount.py\` exit=0 «1 passed»
WITNESSES:
- W1
  cmd: \`python3 -c "from calc import discount; print(discount(50, 20))"\`
  expected: 40.0
  fact: 40.0
  source: calc.py:2 «price * pct / 100»
NOT_CHECKED: none
DEVIATIONS: none
OPEN_RISKS: none
EOF
cr() { python3 "$S/check_report.py" "$@" >/dev/null 2>&1; echo $?; }
check "check_report: filled report = PASS" 0 "$(cr ../ok.md)"
{ cat ../ok.md; printf '\n## CLOSING\n- README (5 lines max): discount divisor fixed, 2 tests in gate\n- Follow-ups: none\n- Plan line: discount fixed per spec section 2\n- Commit message: fix: discount divides by 100; before 1 failed, after 2 passed\n- Paths: calc.py, tests/test_discount.py\n- Metrics row: demo,1,0\n'; } > ../ok_closing.md
check "check_report: report with CLOSING section = PASS" 0 "$(cr ../ok_closing.md)"
TPL="$S/../templates/report.md"
if [ -f "$TPL" ]; then check "check_report: raw template = FAIL" 1 "$(cr "$TPL")"; fi
sed 's/^EXIT: DONE/EXIT: mostly done/' ../ok.md > ../bad1.md
check "check_report: verdict outside vocabulary = FAIL" 1 "$(cr ../bad1.md)"
sed 's/^EXIT: DONE/EXIT: BLOCKED(no staging access)/' ../ok.md > ../blk.md
check "check_report: BLOCKED(reason) = PASS" 0 "$(cr ../blk.md)"
sed 's/^EXIT: DONE/EXIT: BLOCKED/' ../ok.md > ../bad2.md
check "check_report: BLOCKED without reason = FAIL" 1 "$(cr ../bad2.md)"
grep -v '^  fact: 40.0' ../ok.md > ../bad3.md
check "check_report: witness without fact = FAIL" 1 "$(cr ../bad3.md)"
sed 's/^CONTRACT_EDITS: none/CONTRACT_EDITS: none, 42 passed earlier/' ../ok.md > ../bad4.md
check "check_report: number without a command = FAIL" 1 "$(cr ../bad4.md)"
sed 's/^OPEN_RISKS: none/OPEN_RISKS: 2 теста в tests\/legacy не запускались/' ../ok.md > ../fr.md
check "check_report: number in free-text OPEN_RISKS = PASS" 0 "$(cr ../fr.md)"
sed 's/^HYPOTHESIS: .*/HYPOTHESIS: confirmed — ставка 0.18 вместо 0.20 в calc.py:2/' ../ok.md > ../fr2.md
check "check_report: number in HYPOTHESIS rest = PASS" 0 "$(cr ../fr2.md)"
sed 's/^HYPOTHESIS: .*/HYPOTHESIS: maybe the divisor/' ../ok.md > ../bad7.md
check "check_report: HYPOTHESIS outside vocabulary = FAIL" 1 "$(cr ../bad7.md)"
check "check_report: --numbers warn = PASS" 0 "$(cr ../bad4.md --numbers warn)"
sed 's/^TREE: .*/TREE: abc/' ../ok.md > ../bad5.md
check "check_report: TREE not a hash = FAIL" 1 "$(cr ../bad5.md)"
grep -v '^GATE:' ../ok.md > ../bad6.md
check "check_report: missing GATE = FAIL" 1 "$(cr ../bad6.md)"
cat > ../ok.json <<EOF
{"BASE": "$BASE", "TREE": "$TREE", "VERDICT": "NOT_REPRODUCED",
 "GATE": {"line": "2 passed in 0.02s", "log": "/tmp/gate.txt"},
 "WITNESSES": [{"cmd": "python3 -m pytest -q", "expected": "2 passed", "fact": "2 passed in 0.02s"}],
 "NOT_CHECKED": "none"}
EOF
check "check_report: JSON, built-in schema = PASS" 0 "$(cr ../ok.json --template /nonexistent)"
sed 's/"fact": "2 passed in 0.02s"/"fact": ""/' ../ok.json > ../bad.json
check "check_report: JSON witness without fact = FAIL" 1 "$(cr ../bad.json --template /nonexistent)"
check "check_report: unreadable report = exit 2" 2 "$(cr ../nope.md)"

# ---- guard_diff (owned by its own test) -----------------------------------------------------------
if [ -f "$S/test_guard_diff.sh" ]; then
  bash "$S/test_guard_diff.sh" >"$T/guard_diff.log" 2>&1; c=$?
  [ $c -ne 0 ] && tail -n 20 "$T/guard_diff.log"
  check "test_guard_diff.sh" 0 $c
else
  echo "skip test_guard_diff.sh: not present (not_checked)"
fi

[ "$(git worktree list | wc -l | tr -d ' ')" = 1 ]; check "no leftover worktrees" 0 $?

echo; [ $fails -eq 0 ] && echo "selftest: $total/$total passed" || echo "selftest: $fails of $total failed"
exit $((fails > 0))
