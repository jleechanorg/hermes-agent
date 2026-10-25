# Worked case — WA scene 579: "should that have been a roll?" (2026-10-23)

Campaign `ZRj2cblbfGr5C19xO3wW` ("Rome: Gaia Julia"), scene 579. Player presented two
already-signed treaties to Julius Caesar for formal ratification. The UI showed
`Persuasion (Present Dual Reconciliations to Caesar)` — `1d20+11`, die 13, total 24 vs
DC 16 — for an action whose outcome was already determined by the delivered documents.

## Specimen binding

- request id `ZRj2cblbfGr5C19xO3wW_154c7c798c5343cab94cec5af55c9452` (in `extra_json`)
- body 960,595 B, `sha256 426e95a0…e0c0` == `extra_json.request_json_source_sha256`
- served `systemInstruction` `sha256 f3b638d3c6c5b0cada8dd03ff8acc269faf30076fa1d8398df19a625caaa4200`
- pre-turn state: `social_hp_challenge {objective_continues: true, social_hp: 2,
  social_hp_max: 5, successes: 1, successful_attempts: 2, failed_attempts: 0}` —
  note the object had **no objective/NPC identity field**, which is why it can outlive
  satisfaction
- row selection: two rows share the turn's `ingested_at`; the one carrying the real body is
  the `>100000`-byte one (`turn_index` NULL), the indexed row is a stub

## Arms (26 real Gemini calls, control first)

| Arm | One-variable change | Rolled |
|---|---|---|
| A | verbatim control | 6/6 |
| B | blank the `HIGH-TIER NPC ACTIVE … FORBIDDEN` banner sentences (in `contents` dynamic tail, same length) | 5/5 |
| D | insert a satisfied-demand no-roll clause at the auto-success list (same length; also removed one existing sentence → two-variable, weaker arm) | 5/5 |
| E | close the pre-turn challenge in served state (`social_hp`→0, `objective_continues`→false) | 5/5 |
| F | replace the Social-HP mandate block ("STILL REQUIRES DICE ROLLS") with an explicit satisfied-objective no-roll close | 5/5 |

Verdicts: banner → REFUTED-AS-SUFFICIENT; stale-challenge-survives-satisfaction →
REFUTED-AS-SUFFICIENT (E is the arm that kills it); prompt-clause insertion and mandate
rewrite → REFUTED-AS-SUFFICIENT. The roll is over-determined; the model adjudicates
"present demands to a sovereign" as a contested attempt on its own.

Control reproduced production exactly: identical die 13, total 24, DC 16, and
`dc_reasoning` "base DC 18 … strategy/argument (-2) … repetition (+4) … momentum (-4) = DC 16".

## Prompt-source findings behind the complaint (read at the serving commit)

- `mvp_site/prompts/shared/zero_roll_rule.md:3-7` gates a roll on
  (uncertain **AND** stakes) **OR** contested/hazardous.
- The same file's social carve-out (`:13`) reads "ONLY when an interaction is actively
  resisted, **high-stakes**, or contested" — a disjunction that drops the uncertainty
  requirement, so "high-stakes" alone licenses a check. This is the over-roll channel.
- `narrative_system_instruction.md:277-288` — significant-NPC interactions MUST activate
  Social HP, and "SOCIAL HP STILL REQUIRES DICE ROLLS … you must still roll for the attempt";
  the trigger table has no row for delivering completed obligations.
- `shared/dc_calibration.md:27-29` prices conclusive documentary leverage as a −2…−4 DC
  discount — i.e. it makes the check *easier* rather than unnecessary. Scene 579's
  base 18 → DC 16 is exactly that shape.
- `mvp_site/agent_prompts.py` `SOCIAL_HP_EARLY_REMINDER` is injected by
  `_maybe_add_social_hp_early_reminder` whenever *any* saved `npc_data` entry is
  `god_primordial` / `king_ancient` / `lord_general` or level ≥15 — no co-presence and no
  relevance predicate.

## Side defect (independent, worth its own bead)

The served dynamic tail carries the banner **double-escaped**: the model reads literal
`\u2550` / `\u2551` instead of ═ ║. Behaviourally inert in this experiment, but the block
renders as escape soup in every high-tier-NPC turn, which is why `text.index("╔")` fails
and why banner edits must anchor on an ASCII sentence.

## What the null result licensed

No prompt patch was shipped. A contract test asserting the new clause exists would have
passed while behaviour was unchanged — the prompt-substring anti-pattern the owner had
already flagged in issue #10680 (adjudication calibration). Next discriminating arm
(unrun): neutralize the `SOCIAL ENCOUNTERS MUST RESOLVE … MUST roll skill checks` line to
separate "prompt pressure" from "action semantics"; if it still rolls, the fix is
product-level, not prompt-level.

## Artifacts

- `/tmp/gaia-roll/ABLATION_REPORT.md`, `/tmp/gaia-roll/runs/*.jsonl` (per-run raw + scored),
  `/tmp/gaia-roll/spec/` (captured request/response/parts, served system text, exec code).
