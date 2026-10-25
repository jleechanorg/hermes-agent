# Inherited-main-red vs PR-caused: read-only proof recipe

Use when a required check fails on a PR whose diff plausibly cannot cause it (prompt-contract
hash, schema manifest, LOC ratchet, generated-artifact gate). The question is not "is it flaky"
— it is **"did main already fail this check before this PR's base?"**

This recipe needs **no worktree**: `git worktree add` can stall behind disk-admission control
(`admission_degraded:producer_estimate`, 180s+), and a checkout is unnecessary when GitHub
serves exact blob bytes.

## Worked example (2026-10-23, worldarchitect.ai)

Symptom: check `Prompt / Tool Contract Hash Validation` FAILURE on PR #10796 at `e3257b3`,
which touched neither `mvp_site/prompts/scene_image.md` nor its manifest entry.

```bash
# 1. The failing gate's own message names the pair — read it, don't guess
gh run view --job <job-id> --repo <owner/repo> --log-failed | grep -iE 'hash mismatch|version='

# 2. Actual file bytes at MAIN, hashed exactly as the validator hashes them
gh api repos/<owner/repo>/contents/mvp_site/prompts/scene_image.md?ref=main --jq .content \
  | base64 -d > /tmp/main_scene_image.md && shasum -a 256 /tmp/main_scene_image.md

# 3. Recorded hash in the tracked manifest at MAIN
gh api repos/<owner/repo>/contents/mvp_site/schemas/prompt_tool_contracts.json?ref=main \
  --jq .content | base64 -d > /tmp/main_contracts.json
# then walk the JSON in Python for the entry whose path/version you care about
```

Mismatch on **main** = inherited, not caused by the PR.

## Always run the control group

Before claiming "main is red", prove the method: hash several manifest entries the same way
and confirm they MATCH. In the worked example 7 of 8 matched and only `scene_image` mismatched —
that both validates the base64/sha256 path (no CRLF or transport transformation) and localises
the single drifted contract. A recipe that says "everything mismatches" is a broken recipe, not
a broken repo.

## Then ask how it got merged — the bypass is the real defect

```bash
gh pr view <merged-pr> --repo <owner/repo> --json number,mergedAt,mergeCommit,statusCheckRollup \
  > /tmp/pr.json
```

Parse in Python; `--jq` filters using `test(...)` explode on `name:null` entries with
`test("Contract Hash"; null) cannot be applied to: null`.

In the worked example the culprit PR had merged **with that exact check at FAILURE**, i.e. a
merge-gate bypass (admin merge / unprotected required check), which then reddened the required
check on *every* open PR. Report that as the root cause and file the gate question separately
from the one-line repair.

## Reporting shape

1. Failure is inherited or caused — state which, with the two hashes and the control-group count.
2. Name the commit/PR that introduced it (`commits?path=<file>&sha=main`, compare its timestamp
   against the last commit on the manifest).
3. Name the incumbent repair PR if one exists (see pre-dispatch incumbent check) and its gate state.
4. File the harness gap (merged-with-failing-required-check) as its own issue/bead — never fold it
   into the repair PR.
