# `/secondo` route audit + reviewer-seat arithmetic (worked example, 2026-10-25)

Session: PR254 review of a frontend test-harness port. Both `/advice` primaries were walled,
so the C seat (`/secondo`) and the A3 `agy` rung decided whether any verdict was reachable.
Two of my own conclusions had to be retracted; both retractions are the point of this file.

## 1. "Is `/secondo` available here?" — three layers, not one variable

My first answer was "absent, because `AI_UNIVERSE_MCP_ENDPOINT` is unset." That was wrong, and
the operator rejected the generalization ("we will not label all dots' `/secondo` capability
unavailable from one unset environment variable alone").

Actual audit result on the Mac:

| layer | observation |
|---|---|
| `mcp-cli` | `command -v mcp-cli` → MISSING; no `second-opinion-tool` server in any `~/.claude.json` project entry (registered: `aside-mcp`, `claude-design`, `slack`, `ios-simulator-mcp`, `worldarchitect`); mcporter has only `granola`, `lens-studio` |
| canonical default endpoint | skill defaults `AI_UNIVERSE_MCP_ENDPOINT` to `https://ai-universe-backend-dev-114133832173.us-central1.run.app/mcp`; unauthenticated `GET /mcp` → **HTTP 400 in 0.32 s** (up, auth required) |
| existing cached session | `~/.ai-universe/auth-token.json` present, mode **600**; `node ~/.claude/scripts/auth-cli.mjs token` → exit 0, 1157 chars; `initialize` → **200** `serverInfo: ai-universe-server 2.0.0`; `tools/list` → **200** with `agent.second_opinion` |

Conclusion recorded: route **usable** via the documented HTTP fallback, and no new grant was
needed. The primary MCP-CLI layer was the only closed one.

Reusable rules:
- An unset per-deployment env var is not absence when the skill ships a default endpoint.
- Reachability check costs nothing: unauthenticated GET, read the status code.
- Never echo the token; capture it and report `exit code` + `token_chars` only.

## 2. Payload coverage is a second gate

Diff under review: `git diff 9d9cbf4e ec4cb61d` → **140,011 chars** (140,012 with the trailing
newline), **2,639 lines**, **21 files**.

- Tool limit: `agent.second_opinion.question` `maxLength: 320000` → the whole diff fits.
- Skill defaults: `SECOND_OPINION_MAX_DIFF_CHARS=32000` and `SECOND_OPINION_MAX_FILES=20`
  ⇒ roughly 23% of the diff and 20 of 21 files, with `gitContextNotices` truncation markers.
- The packet builder (`skills/second_opinion_workflow/scripts/build_second_opinion_request.py`)
  does not exist on this host — every `second-opinion*` skill dir held only `SKILL.md`. Manual
  assembly is explicitly allowed by the skill's "FALLBACK APPROACH: Manual CLI" section.

Manual submission that worked (payload 148,694 bytes, sha256 recorded before send):
`POST /mcp` → `tools/call` → `agent.second_opinion`, `question` = decision + inventory + the
byte-identical diff. Response: HTTP 200, 42.9 s, 111,308 bytes, three model opinions (all
APPROVE: `cerebras-primary`/Qwen3-Thinking, `gemini-3-flash-preview`, `grok-4-fast`).

Disclose both counts when they differ: the operator's "140011 characters" excluded the trailing
newline; the exact byte length was 140012. State which one the hash covers.

## 3. Multi-model does not mean multi-seat

`/secondo` returned three independent model verdicts. Under the installed rule the C seat is
**one vote** regardless: "A vote + C (`/secondo`) vote → 2 (A + C) → APPROVED". Counting three
would have manufactured a quorum. Say "three model opinions, one seat-C vote" out loud.

## 4. A3 `agy` — voting when it is the only A leg

Two readings exist and only one is correct:
- "A3 shares seat A and never adds a vote" → a surviving *primary* plus A3 is still 1 (A).
- "Codex unavailable + Opus unavailable + A3 APPROVE → 1 (A, fallback chain)" → the A3 verdict
  **is** seat A's single vote, and A + C = 2 → `APPROVED`-eligible.

I initially wrote "agy is a non-voting A3 rung" and had to retract it. The operator supplied the
canonical anchor (jleechan-skills `6b8888445d83b54e1cb90559660f64caaaf7d6d0`,
blob `e6873fad94733119e497cc3299c454823db33001`, lines 343–345) and asked for the installed
text/hash to be reconciled before any vote was counted.

Reconciliation method that settled it:
```bash
git hash-object ~/.claude/skills/advice/SKILL.md          # installed blob
curl -sS -o /tmp/canonical.md "https://raw.githubusercontent.com/jleechanorg/jleechan-skills/<sha>/.claude/skills/advice/SKILL.md"
git hash-object /tmp/canonical.md                          # canonical blob
diff -u /tmp/canonical.md ~/.claude/skills/advice/SKILL.md
```
Result: 36 differing lines, all pointer/naming drift (`pr-lifecycle` vs `draft-first-pr`); the
**quorum table byte-identical**. So the rule was the same in both copies and the drift was not a
reason to withhold a ruling.

## 5. A3 invocation that actually produced a full-coverage verdict

```bash
cd <clean detached checkout at the exact review SHA>   # git status --porcelain == 0 lines
agy --model gemini-3.8-flash-high --print-timeout 600s -p "$(cat /tmp/review-packet.txt)"
```
Exit 0, stderr empty, 5,155 bytes. The packet named the base/head, the complete 21-file
inventory, the instruction to run `git diff <base> <head>`, and the requirement to declare
COVERAGE. Verdict: APPROVE, **COVERAGE 21/21 files + complete 2,639-line diff**, CONFIDENCE high,
with grounded identifiers (`validate_bearer_token`, `NoRedirect`, `_require_complete_body`,
`response.length`, SSE terminal validation, `runtime-provenance.json`).

Note the contrast with the C seat: `agy` ran **inside the checkout with tools**, so it could
actually read the diff; the `/secondo` models received an inline packet and had no tool access,
which is why their "sources" were constructed blob URLs rather than fetched pages. Say which
reviewer had tools when reporting coverage.

Long `agy`/`claude` review lanes must be backgrounded with a captured log, never foregrounded:
these runs take minutes and a foreground call invites an opaque timeout.

## 6. Synthesis note

The orchestrator counts and binds votes; it does not cast one. Final form used:

```
VERDICT: APPROVED at <head-sha>            # code only
```
plus an explicit exclusion sentence for runtime/video evidence, which neither reviewer claimed
to have seen.
