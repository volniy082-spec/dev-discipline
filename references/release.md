# Release: prove the running code is the verified commit

An adaptable module: take what your platform does not already guarantee. CI/CD with an immutable image
pinned by digest reduces items 1–4 to a digest check. Manual deploy (rsync, ssh to a VM) needs the whole list.

The core rule in one line: **a release is not done until the running artifact is matched to the verified
commit and the changed behaviour has run in the deployed environment.** Health 200 only proves
the process started.

## 1. An executable preflight
Release conditions are a script, not a paragraph. It prints which condition failed and exits non-zero.

```bash
set -euo pipefail
die(){ echo "PREFLIGHT FAIL: $*"; exit 1; }
[ -z "$(git status --porcelain -- $SHIPPED_PATHS)" ] || die "dirty tree in shipped paths"
git fetch -q origin
[ "$(git rev-list --count origin/main..HEAD)" = 0 ] || die "HEAD not pushed"
DEPLOYED=$(curl -fsS "$URL/version" | jq -r .commit)          # what the target runs now
git merge-base --is-ancestor "$DEPLOYED" HEAD || die "target is newer or has foreign code: $DEPLOYED"
ssh "$HOST" 'mkdir /var/lock/app-deploy' || die "lock held"    # atomic; released by a trap
echo "PREFLIGHT OK $(git rev-parse --short HEAD)"
```

- Only the holder releases the lock (a trap set after a successful acquire). A stale lock is not broken
  automatically: a human removes it, or a script that has verified the holding process is dead.
- Will the restart kill running jobs? Drain with a timeout or an explicit `--force`, otherwise stop.
- No override flags in the normal flow. Every guard prints why it stopped: a guard exiting silently
  under `pipefail` reads as a network failure.

## 2. A rollback point before touching the target
Before changing the target, take a snapshot (code, config, a DB dump if needed) and record **which commit
it contains**. Pick the rollback target by the recorded identity, not by name, sort order or "latest".

## 3. Health asserts identity
- The build embeds `version` and `commit` into the artifact; `/health` or `/version` returns them.
- The release gate passes only if the returned `commit` equals `git rev-parse HEAD`. Otherwise roll back.
- CI rejects a release where the code changed but the version or build id did not.

```bash
EXP=$(git rev-parse HEAD); GOT=$(curl -fsS "$URL/health" | jq -r .commit)
[ "$GOT" = "$EXP" ] || { echo "IDENTITY MISMATCH got=$GOT exp=$EXP"; exit 1; }
```

## 4. Artifact equals commit: content hash or image digest
A version string is a claim, not proof. **Containers:** the running image digest equals the digest
CI built from this commit.

```bash
kubectl get pods -l app=$APP -o jsonpath='{..imageID}'          # or
docker inspect --format '{{.Image}}' $CONTAINER
```

**Files on a host or in a container.** Hashes of the changed files, then a digest of the whole tree:

```bash
git diff --name-only "$DEPLOYED" HEAD -- $SHIPPED_PATHS > files.txt
xargs sha256sum < files.txt > local.txt                          # clean tree = HEAD
ssh "$HOST" "cd $APP_DIR && xargs sha256sum" < files.txt > prod.txt
diff local.txt prod.txt && echo "changed $(wc -l < files.txt)/$(wc -l < files.txt) equal"
# whole tree: find . -type f ! -path './.git/*' | sort | xargs sha256sum on both sides, comm -3
```

The report gets `N/N equal` plus the "prod only" and "local only" lists. Extra files on prod
(rsync without `--delete`) are an observation, not a reason to delete silently.

## 5. Differential smoke: local versus deployed
The smoke runs the **changed behaviour**, not liveness. The same file runs on the verified commit
locally and in the deployed environment; the outputs are compared byte for byte.

```bash
python smoke.py > smoke_local.txt
ssh "$HOST" "docker exec -i $CONTAINER python -" < smoke.py > smoke_prod.txt
diff smoke_local.txt smoke_prod.txt && echo BYTE-EQUAL || echo DIFFER
```

- Output is deterministic and named: `metric_name=value`, inputs named. The expectation comes from running
  the script on the commit, never from memory: a bare number without a metric name cannot be compared.
- Each probe distinguishes failure classes. A login with garbage must give 401 or 422; 404 means the
  proxy strips the prefix. A probe that is green in both the healthy and the broken state is not a probe.
- The smoke prints only aggregates and catalogue data, never customer data.
- A long smoke over an ssh pipe breaks: run it detached, write to a file. Keep the tools in the repository.

## 6. Canonicalize before digesting (numbers only)
Only for numeric output across machines: a raw float `repr` measures the platform (libm, BLAS,
solver iterations), not the code.

```python
def canon(v, nd=9):                       # nd above the measured noise; record the reason next to it
    if isinstance(v, float):
        return "nan" if v != v else repr(round(v, nd))
    if isinstance(v, dict):
        return {k: canon(v[k], nd) for k in sorted(v)}
    if isinstance(v, (list, tuple)):
        return [canon(x, nd) for x in v]
    return v
```

Strip timestamps, paths, random ids. If code identity is proven by hash (§4) and the digest still
differs, debug the probe first, then the product.

## 7. Multi-layer release
The diff touches more than one layer (code, image, env, proxy, DB schema) — a table before release:

| Layer | What changes | Delivered by | Rolled back by | Probe |
|---|---|---|---|---|

A normal deploy script usually delivers only code. Schema migrations are a separate step before the code.

## 8. Close with a re-measure on prod
- The expectation or corridor (`+N…+M`, `≥k/n`) and the re-measure command are written **before** release.
  The expectation can change only before the run, in a separate commit.
- The re-measure on prod data is **read-only**. Every outlier is attributed by a targeted probe or
  becomes a finding. A class the re-measure finds goes into the gate in the same commit as the fix.
- **Writes to prod data, migrations without rollback, manual DB edits — only with a human.**
- Verdict: `DONE` if inside the corridor or explained; otherwise `BLOCKED(reason)` and the partial
  state in words.

## 9. Rollback and a torn release
After a failed or partial release, first establish the actual state by hash comparison (§4),
then choose between retry and rollback. The snapshot of a torn attempt may already contain new code.
After a rollback run the same identity check and the same smoke as after a release.

## 10. Who decides
A reversible release with identity, rollback and smoke is done by the agent itself when the acceptance chain
is green, and reported afterwards. This removes no guard. Left to a human: writes to prod data,
payments, host security and permissions, deleting someone else's state. In team work the checkpoint
is PR review and the environment's rules.

## 11. Release in batches when proof is expensive
When identity checks, smoke and the re-measure cost much more than the change itself, release in batches
instead of per change. Release after at least two accepted changes or at the end of the working day, with
one preflight, one identity and artifact check, and a smoke covering every change in the batch. Record one
proof per batch. A target that is down for hours should not stall the development queue: accepted changes
wait in the batch. This trades release latency for orchestration time. Do not batch a fix that users are
waiting for, or a migration.

## Release report
```
PREFLIGHT OK <sha>
IDENTITY  health.commit=<sha> == HEAD
ARTIFACT  changed N/N equal, tree M/M equal (or image digest == CI digest)
SMOKE     BYTE-EQUAL (smoke_local.txt vs smoke_prod.txt)
REMEASURE corridor <recorded in <file>@<sha>>, fact <number>, command <...>
VERDICT   DONE | BLOCKED(...)
```

## Anti-patterns
| I notice | I do |
|---|---|
| "Health 200, so it shipped" | §3–5: identity and behaviour smoke |
| Digest differs while code is equal | canonicalize, debug the probe |
| Rolling back to the "latest" snapshot by name | pick by recorded identity |
| Verdict from a pipeline's `$?` or `tail` | the tool's summary line |
