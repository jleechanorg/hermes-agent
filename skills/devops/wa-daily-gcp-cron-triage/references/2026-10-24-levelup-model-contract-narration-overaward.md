# 2026-10-24 `wa-daily-level-up-test` RED — narration + over-award + deferred crossing

Worked example of the **model-contract** class: five findings, two causes, one narrative class, and
**no** persistence/save-path defect. Read-only investigation (no rerun, no campaign mutation).

## Verdict

| Finding | Real cause |
|---|---|
| `[turn_xp_contract] expected exact 34% band XP delta 105 (102 per roll × 2, capped at 105) … got 204` | Model followed the injected directive ("34% per band **per qualifying roll**", no per-turn cap) on a 2-roll turn; served contract caps a turn at ≤35% band (105) |
| `[crossing_flow] saved XP 102 -> 306 reached Level 2 but the saved level stayed 1` | Model wrote cumulative XP 306 but not the paired `level`; contract says the server does NOT apply the level |
| `[atomicity] raw model emitted numeric XP/experience in narrative` ×3 | `narrative` field carried numeric tokens; narration-only, no state effect |

Findings are **one chain**: at L1 (band 300) the expected award would have left 102 + 105 = **207 <
300**, so the crossing (and its finding) only exists because the over-award raised XP to 306.

## Run-bound provenance

- Execution `wa-daily-level-up-test-jpjz6`, evidence id `eb4f02518329445594d00570d65b4935`.
  Created 2026-10-24T07:00:03Z, task start 07:00:40.957Z, completion 07:06:57.089Z,
  `NonZeroExitCode` exit 1.
- Runner image `gcr.io/worldarchitecture-ai/wa-daily-level-up-test@sha256:f6c9a83c…d252d`, SLSA level 3,
  build `1ff081a8-40b2-46cc-ad5d-23ae036ccca7` (04:57:05→05:01:06Z) with
  `--build-arg=GIT_COMMIT=c792d02410677947dda12494ea10ce612783d6bc -f testing_mcp/infra/Dockerfile.test-runner`;
  source tarball sha256 `4b6c4222…3033`.
- Served dev revision `mvp-site-app-dev-od7c23cc1-6adc3a1f` created 04:54:57.799Z, label
  `commit-sha-full=c792d0241…`, image `mvp-site-app@sha256:012009b3…c053`; **zero** revisions created
  07:00–07:07; run-bound `/health` at 07:06:44.111Z returned `git_commit=c792d0241…`. Traffic later
  moved to `68aaa40` (08:29Z) — not used as evidence.
- Bundle `SHA256SUMS.txt`: **50 ok / 0 bad / 0 missing**. `summary.json` sha256 `e41b7265…`; campaign
  snapshot `42YkO7PfF6KRS9wJSnyS.json` sha256 `5de791fb…` (final L2, XP 612/900).

## Per-turn chain (`raw_state_updates.jsonl`, 19 rows)

| turn | stage | raw `reward_event.xp` | raw PCD xp/level | persisted | narrative numeric-XP tokens |
|---|---|---|---|---|---|
| 12 | `organic_target_2_action_2` | 102 / significant | 102 / 1 | 102 / 1 | `102 XP` |
| 13 | `organic_target_2_action_3` | 0 / none | – | 102 / 1 | – |
| 14 | `organic_target_2_action_4` (`…db626eb9…`) | **204 / major** | 306 / **1** | 306 / 1 | none |
| 15 | `organic_target_2_action_5` | 102 / major | 408 / 2 | 408 / 2 | `102 XP`, `XP 306` |
| 16 | `…_review` | 0 / none | – | 2 | – (audit: "Repaired missing Level 2 … spells/features") |
| 17–18 | choices | – | 408 / 2 | 2 | – |
| 19 | `post_review_gameplay` | 204 / major (band 600 ceiling = 210 ⇒ legal) | 612 / 2 | 612 / 2 | `204 XP`, `612 XP`, `900 XP`, `XP: 408` |

Model's own justification at t14: "Two qualifying attack rolls resolved this turn … (2 x 102 = 204
XP)" — it followed the directive verbatim, so this is instruction conflict, not model drift alone.

## Same-SHA pass on the same day (kills "regression")

Execution `tlbtv` 05:20:40Z, evidence `9e713e45f41c4e309ee5408b475dcaff`: `status PASS`,
`strict PASS`, `selected_gate model_authored_advancement_v1`, `errors: []`, **same** runner SHA
`c792d024…` and same served SHA. Its raw chain was 102 / 102 / 306@L2 — the model authored the level
on the crossing turn. ⇒ today's red is model-output variance, not code.

## Contract vs harness (the stale half)

`mvp_site/prompts/shared/reward_event_contract.md` @ c792d024:
- "Per turn award at most a fraction of the current-level band … `major` ≤ 35%. Level 1 (band 300):
  12 / 36 / 105 … Tier must DESCRIBE the value: if `gained` exceeds its tier ceiling, raise
  `xp.tier`; never change `gained` to fit."
- "The server never enforces pacing ceilings or reduces authored `gained` for pacing."
- "When an award crosses a progression threshold, the server does not apply the level: write the
  resulting `level`, cumulative `experience.current`, and complete sheet … in the same response."

`mvp_site/rewards_engine.py` @ c792d024 preserves authored `gained` and only upgrades `tier` to the
smallest ceiling that fits — matching #10753 (`f53e9ebc`, 2026-10-22, "move XP pacing to the prompt,
stop cutting authored XP"; `git log -S "never cuts for pacing"`).

Harness @ c792d024:
- `_CAMPAIGN_THIRTY_FOUR_PERCENT_PACING` (lines ~753-772): 34% per qualifying roll, no turn cap →
  contradicts the served per-turn ceiling whenever ≥2 qualifying rolls resolve.
- line ~3532 comment: "The server caps one turn's award at the major-tier share of the band, so
  several qualifying rolls can never persist more than it." → **stale**; the 105 number it computes
  (`min(102 × rolls, 0.35 × band)`) still matches the prompt.

Recommended repair: fix the directive text + the stale comment (add the per-turn cap). Never re-add a
server clamp.

## Sanitized extraction recipe

- State per turn: parse `unknown/daily-scheduled-<date>-<exec-id>/raw_state_updates.jsonl`.
- Narration: run `_NUMERIC_XP_MENTION_RE` (from `testing_mcp/lib/level_up_model_compliance.py`) over
  each turn's `response_text` in `iteration_001/llm_request_responses_<id>.jsonl`; report only matched
  tokens. That file has no prompt field, so the run-bound directive text must be cited from the
  harness source at the run's own SHA.
- Integrity: `gcloud storage cp -r "gs://wa-test-evidence/daily/<date>/<id>" bundle/` (not `/**`),
  then verify `SHA256SUMS.txt`.

## Prior art

Open bead `rev-s209rx` (`type=bug`, "levelup defect: turn_xp_contract [single_organic]") already tracks
this assertion class on another run — cite it instead of filing a duplicate.
