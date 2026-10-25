# Pre-dispatch incumbent check (mandatory, 1 call)

**Failure this prevents (2026-10-23).** Main went red after a merged PR. I diagnosed the
root cause, dispatched `pil` to open a fix PR — and only afterwards ran
`gh pr list --search`, which showed an incumbent fix PR (`#10810`) already existed and was
**fully green**. My dispatch produced a duplicate (`#10816`) with its own failing
`deploy-preview`; it had to be closed and its branch deleted. Cost: a full CI run, a failed
preview deploy, a public close-comment, and a correction I had to disclose to the user.

The search costs one tool call. Do it **before** dispatching, not after.

## Step 0 — before any fix dispatch (including "drive it green" / "main is red")

```bash
# 1. Symptom/keyword sweep over open PRs
gh pr list --repo <owner/repo> --state open \
  --search "scene_image hash OR contract hash OR prompt_tool_contracts" \
  --json number,title,headRefName --jq '.[]|[.number,.headRefName,.title]|@tsv'

# 2. Branch-name sweep (lanes usually name the branch after the fix)
gh pr list --repo <owner/repo> --state open --limit 100 \
  --json number,headRefName --jq '.[]|select(.headRefName|test("contract|hash|<keyword>"))|"\(.number)\t\(.headRefName)"'

# 3. Decisive check: does any open PR already contain the exact lines you intend to write?
for n in <candidates>; do gh pr diff $n --repo <owner/repo> | grep -E '<the exact old/new literal>'; done
```

Step 3 is the real discriminator: a matching `+`/`-` pair for the exact literal means the fix
is already in flight. Confirm the incumbent's gate state before anything else:

```bash
gh pr view <incumbent> --json number,headRefName,headRefOid,mergeable,statusCheckRollup \
  --jq '{n:.number,head:.headRefName,oid:.headRefOid,mergeable:.mergeable}'
```

Parse `statusCheckRollup` in Python, not with a `--jq` `test(...)`: entries can carry `name:null`
/`conclusion:null` and a jq expression like `select(.name|test("Hash"))` then fails with
`test("Contract Hash"; null) cannot be applied to: null`.

## Decision matrix once an incumbent exists

| Incumbent state | Action |
|---|---|
| Green, mergeable, same single fix | **Do not open anything.** Report it and name the remaining human gate (e.g. `MERGE APPROVED`). |
| Green but mixed scope (extra unrelated files) | Do not duplicate. Annotate/comment on the scope question; let the owner of that PR split it, or ask before opening a clean replay. |
| Red / stale / wrong fix | Take over that same PR (fresh branch off its head only if you own it) instead of racing a second PR. |
| Closed/abandoned | A replay PR is correct — cite the closed PR in the body. |

## Pitfalls

- Searching by *title* alone misses incumbents written by other lanes with different titles; search
  by the **file path** and by the **literal value** (hash, version, constant) too.
- A "one-line mechanical fix" is exactly the kind of work several idle lanes dispatch at once — the
  smaller the fix, the higher the duplicate risk.
- If you already opened the duplicate: close it with a comment naming the incumbent, delete the
  branch, and disclose the duplicate in your report. Do not silently leave it green-ish.
- Verify the incumbent actually contains the fix (`gh pr diff <n> | grep <new literal>`), not just a
  plausible title.
