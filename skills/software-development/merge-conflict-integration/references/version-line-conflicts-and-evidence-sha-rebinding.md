# Version-line conflicts across N PR branches, and body-bound evidence gates

Measured 2026-10-22/23, `jleechanorg/disk_magician` PRs #241 / #243 / #244.

## Shape of the conflict

All three PRs were `mergeable: CONFLICTING` / `mergeStateStatus: DIRTY`. Sizing the
conflict before touching anything showed the whole cluster was the **same single line**:

```bash
git fetch origin
for b in feat/quarantine-reconcile fix/ios-release-dd-reclaim work/detached-on-origin-removal; do
  echo "=== $b"
  git merge-tree --write-tree refs/remotes/origin/main origin/$b 2>&1 | sed -n '2,12p'
  git show origin/main:pyproject.toml | grep -n '^version'
  git show origin/$b:pyproject.toml     | grep -n '^version'
done
```

```
main 0.2.265 | PR 0.2.264 | PR 0.2.266 | PR 0.2.263   (merge base 0.2.262)
CONFLICT (content): Merge conflict in pyproject.toml
```

Three "conflicting PRs waiting on CI" were one version-pin bump each. **Sizing before
triaging turns a quota-blocked cluster into a five-minute mechanical fix** — do it before
concluding a lane is stuck.

## Resolution

- Take the merge (`--no-ff`), never a rebase. A rebase rewrote three heads and every push
  came back `! [rejected] … (non-fast-forward)`; the merge push fast-forwards with no
  force at all. (Skill rule 1 — never rebase a published branch — held exactly here.)
- Resolve to **one value strictly above `origin/main`** for all branches (0.2.266), not
  each branch's own value: the repo's gate is monotonic (>= highest historical), and one
  value keeps the batch consistent as the PRs land in any order.
- Prove with the repo's own checker, not an eyeball:
  `python3 scripts/check_version_monotonic.py` →
  `[PASS] current version '0.2.266' is >= highest historical version '0.2.265'`.

## The trap: rewriting the version line is not removing the conflict block

A regex anchored on `^version = ".*"$` rewrites the value **and leaves the markers**:

```
[project]
name = "disk-magician"
<<<<<<< HEAD
version = "0.2.266"
=======
version = "0.2.265"
>>>>>>> origin/main
```

Consequences, both measured:

1. **The repo's version checker still PASSES.** `check_version_monotonic.py` extracts the
   version with a regex fallback *after* `tomllib.loads` throws, so an invalid TOML file
   reports `[PASS]`. Never treat that checker as TOML validity.
2. **The breakage surfaces much later**, as
   `ERROR: …/pyproject.toml: Invalid statement (at line 7, column 1)` on the first
   `python3 -m pytest` run — after the merge commit was already pushed to three PR heads.

Correct collapse, for the version-only case:

```python
PATTERN = re.compile(
    r"<<<<<<< [^\n]*\nversion = \"[^\"]*\"\n=======\nversion = \"[^\"]*\"\n>>>>>>> [^\n]*\n"
)
t = PATTERN.sub('version = "0.2.266"\n', t)
tomllib.loads(t)                      # raises on a botched collapse
assert not re.findall(r"^(?:<<<<<<<|=======|>>>>>>>)", t, re.M)
```

Then `git add` + `git commit --amend --no-edit` (an `--amend` on a merge commit **keeps
both parents** — verify with `git log --oneline -1 --parents`) +
`git push --force-with-lease origin HEAD:<branch>`, and re-run the PR's suites at the new
head. A force-with-lease back onto your own PR branch after amending your own merge
commit is the only force this class needs; the resolution itself never needs one.

## Body-bound evidence gates: the SHA is part of the gate

The repo's `Evidence Gate` (`pull_request_target`) fails with:

```
Evidence Gate: FAIL: Evidence SHA 2b6ee57… does not match PR head c121231…
```

A merge commit moves the head, so **every PR whose body pins an `**Evidence SHA:**` must be
re-bound after the merge.** Do not just rewrite the SHA — re-run the evidence commands at
the new head, then edit the body with the re-verification line:

```
**Evidence SHA:** <new head>
**Re-verified at this head (<date>):** <suites + counts>. Delta vs the previously recorded
evidence SHA is only the merge of origin/main plus a version-line conflict resolution; no
behavioral source changed.
```

`gh pr edit --body-file` re-triggers `pull_request_target`, which is what makes the gate
re-evaluate.

## Read the latest run per check, not `statusCheckRollup`

After the body edit the rollup still listed **two `FAILURE` entries per PR** while the
newest run was green — `statusCheckRollup` carries every historical run for a check name:

```
gh run list -R <repo> --branch <branch> --limit 3 --json databaseId,name,status,conclusion,headSha,event
 39901266101 Evidence Gate completed success  e02e434 pull_request_target   <- authoritative
 39900909121 Evidence Gate completed failure  e02e434 pull_request_target   <- stale, same SHA
```

So: `mergeStateStatus: BLOCKED` with stale `FAILURE` rows is not a red gate — resolve it by
listing runs and quoting the newest run per check name. Conversely, a single green newest
run is the claim to make; the rollup entry is not.

## Batch mechanics that held up

- One fresh worktree per PR branch under `~/.worktrees/<repo>/<slug>`, never the primary
  clone that already had a dirty detached tree and other lanes' files.
- Remove a leftover worktree with `git worktree remove --force <path>` before re-adding;
  `git worktree add --force -B res_<slug> <path> origin/<branch>`.
- Run each test script as its own literal command. `for t in a.sh b.sh; do bash $t; done`
  is refused by the safety net (`analysis.dynamic-shell-source`, "shell execution source
  cannot be verified safely") — the loop form of test execution is not available.
- Final state to report: per-PR `mergeable`, new head SHA, newest run conclusion per check
  name, and the re-run suite counts.
