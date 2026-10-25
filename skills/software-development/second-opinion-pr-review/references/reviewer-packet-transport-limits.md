# Reviewer packet transport limits — measure the payload before you dispatch

Verified 2026-10-25 while running canonical `/advice` seats (A3 = `agy.real`, C = `/secondo`)
on two adapter PRs (`worldarchitect.ai#10847` @ `27dc3d67`, `worldai_frontend#279` @ `a8bb8e91`).
All numbers below are measured, not estimated.

## 1. A-seat (`agy.real`) input ceiling is a kernel limit, not a model limit

Print mode takes the prompt as **one CLI argument**. Linux `MAX_ARG_STRLEN` is 32 pages =
**131,072 B per single argument** (`ARG_MAX` is 2 MB but that is the *sum* of all strings).

Empirical probe (no model call needed — run it once and keep the receipt):

```bash
python3 - <<'PY'
import subprocess
for n in (120000, 131000, 140000, 500000):
    try:
        r = subprocess.run(["/bin/echo", "x"*n], capture_output=True)
        print(n, "rc=", r.returncode)
    except OSError as e:
        print(n, "OSError:", e)      # 140000 => [Errno 7] Argument list too long
PY
```

Observed: `120,000` ok · `131,000` ok · `140,000` E2BIG · `500,000` E2BIG.

Consequence: a PR562-sized packet (496,650 B: 15 files, 373 KB of source + 119 KB diff) **cannot**
be passed on `-p` at all. Small docs/adapter PRs can:

| Target | changed files | full-file source | full diff | final packet | fits 131,072? |
|---|---|---|---|---|---|
| `worldarchitect.ai#10847` @ `27dc3d67` | 7 | 67,298 B | 41,950 chars | **112,788 B** | yes |
| `worldai_frontend#279` @ `a8bb8e91` | 6 | 30,470 B | 14,887 chars | **49,076 B** | yes |

Budget rule of thumb: `sum(changed file bytes) + len(diff) + ~2.5 KB framing`. The diff is *not*
free — omitting it from the estimate is what produced an optimistic "~71 KB" that was really 112 KB.

`--input-format stream-json` exists and reads NDJSON from stdin, but neither the installed
`agy.real --help` (v1.4.7) nor the official reference page
(`https://antigravity.google/docs/cli/reference`, fetched 2026-10-25, 37,718 B, sha256
`fd5d123d…`) documents the message schema: 0 mentions of stdin, 0 of NDJSON, no example. Do **not**
guess a wire format for an approval lane; report the ceiling instead.

## 2. C-seat (`/secondo`) builder: positional-only, and one forgotten cap truncates silently

`~/.claude/skills/second_opinion_workflow/scripts/build_second_opinion_request.py`

- Usage is **positional only**: `OUTPUT_PATH QUESTION MAX_OPINIONS BASE_REF`. There is no
  `--file`, `--stdin`, or `@path` (grep `add_argument` → 0 matches), so the question travels as a
  CLI argument and **the only source the reviewer can receive is git diff hunks**.
- Caps are env overrides (defaults in parentheses):
  `SECOND_OPINION_MAX_DIFF_CHARS` (24000) · `SECOND_OPINION_MAX_PATCH_CHARS` (6000) ·
  `SECOND_OPINION_MAX_FILES` (20).
- `truncate_text()` keeps `text[:limit]` and appends `...[<label> truncated by N characters (limit L)]`,
  so truncation is self-reporting — read it.

**The failure this produces:** leaving `SECOND_OPINION_MAX_PATCH_CHARS` at 6000 on a PR whose
biggest file diff is 37,079 chars truncates the three decisive files to 6,000-char prefixes. The
reviewer then invents artifacts that do not exist in the PR (`contracts/contract-v2.yml`,
`bin/draft-first-pr`, `/er-allowlist.txt`) — a **fabricated-coverage signature**. That run is
`INVALID`, not a conditional verdict.

Required caps for a full hunk payload: `MAX_PATCH_CHARS >= largest single-file diff`,
`MAX_DIFF_CHARS >= total diff`, `MAX_FILES >= changed file count`. Note the request body carries the
full diff **and** the per-file patches, so serialized size ≈ 2× the diff (backend example ≈ 84 KB).
Server-side payload limits are **not** documented anywhere retained — declare that unknown rather
than claiming full coverage.

Coverage label that is always honest for C: *"untruncated diff hunks + question; unchanged file
bodies and repository context were not available"*. Never call it a full-file review, and per the
existing quorum rule a diff-only lane cannot be one of two full-coverage approvals.

## 3. The empty-packet trap: shallow base+head fetches have no merge base

Two depth-1 fetches of two SHAs create **unrelated histories**:

```bash
git init r && cd r && git remote add origin https://github.com/<org>/<repo>.git
git fetch -q --depth 1 origin <base-sha>
git fetch -q --depth 1 origin <head-sha>
git checkout -q <head-sha>
git diff <base-sha>...HEAD          # fatal: <base>...HEAD: no merge base
```

The builder swallows that error, reports `Changed files detected: 0 · Patches attached: 0`, and
sends a payload with **no source at all**. All three models then answer `WITHHELD` for lack of
context (2026-10-25: backend 27,199 tokens/$0.0116, frontend 19,656 tokens/$0.0094 — both spent on
an empty payload). That is an input defect, not a review.

Preflight that would have caught it, in order:

```bash
git rev-parse HEAD                          # == the exact head you meant to review
git merge-base <base> HEAD                  # must print a SHA, non-empty
git diff --name-only <base>...HEAD | wc -l  # must be > 0 and equal the PR's changed-file count
```

Then re-check the builder's own log line before trusting the run:
`grep -E "Changed files detected|Patches attached|truncated by" /tmp/c-<lane>.out`.

Provision history instead of two depth-1 SHAs: fetch the **branch ref**
(`git fetch --no-tags origin '+refs/heads/<branch>:refs/remotes/origin/<branch>'`) or use a partial
clone that keeps ancestry (`git clone --filter=blob:none`), then confirm `git merge-base` before
dispatch.

## 4. GitHub compare/contents APIs reject abbreviated SHAs

`gh api repos/<org>/<repo>/compare/<base12>...<head12> -H 'Accept: application/vnd.github.diff'`
returned a 102-byte body `{"message":"Not Found"}` and a 404 — twice, for both repos. Resolve short
SHAs to full 40-char SHAs first (`gh api repos/<org>/<repo>/commits/<short> --jq .sha`) and only then
call compare/contents. A 102-char diff is always this, never a real empty change.

## 5. Receipt shape to publish per seat

```
repo / PR / exact head / exact base
model + transport (direct agy.real vX, or second-opinion HTTP MCP)
packet bytes + sha256 + what it contained (files, diff chars, policy block)
UTC start / end, exit code, stdout bytes + sha256, stderr bytes
coverage declaration actually returned by the reviewer
verdict (+ explicitly: single-seat, not quorum)
```

Keep invalid attempts on disk under a labelled name (`INVALID-empty-payload/`) with the builder log;
they are evidence of the defect, and they must never be quoted as a vote.
