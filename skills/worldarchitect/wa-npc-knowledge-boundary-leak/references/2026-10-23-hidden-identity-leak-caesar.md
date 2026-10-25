# Worked case — hidden identity leak, campaign `ZRj2cblbfGr5C19xO3wW` (2026-10-23)

Campaign **Rome: Gaia Julia**, scene 481. Issue
`https://github.com/jleechanorg/worldarchitect.ai/issues/10817`, bead `rev-shre2t`.

## Symptom

Player PC travels Capua under the cover "Gaia of Ariminum" (equestrian heiress). The player set the
cover themselves: *"I go incognito as a lower tier noble woman for fun and to scout"* (user turn in
the Capua-arc planning prompt), and actively maintained it (asking NPCs "what do you think of my
namesake Gaia Julia", deflecting Sura with *"I'm just bored… wouldn't hurt Spartacus or her"*).

Scene 481 narrative leaked the parentage into an NPC's mouth:

> Agron (Level 4, Age ~26) … **"We were fools to let that Roman girl walk,"** … **"Caesar's blood or
> no, she was alone with ten men. We could have slit her throat and taken her rings!"**

Story doc `turn_rid_mvksdpa0_lr75ncv7kv1mxuuv3us6_ai`, `ts=2026-10-23 09:48:20Z`, CombatAgent
`turn_index=322`. Export artifact: `/tmp/wa-repro-caesar/source_story.txt` line 5434 (966 story docs,
1,066,466 chars).

**Best single piece of evidence** — the same NPC had been correctly bounded two scenes earlier:

> Spartacus: "She calls herself Gaia of Ariminum. She plays the petulant daughter of a merchant…
> But it is a mask. A lie." … "the power that coils in her blood… it is ancient. Predatory."

He suspected a mask; he never named Caesar. Scene 481 is a new, unsupported knowledge claim, not the
resurfacing of a prior reveal.

## Player correction (arrived AFTER the bug)

God-Mode turn `turn_rid_mvksizs0_ncri7x94epz6ajmpykak_user` (`2026-10-23 09:51:55Z`):
*"he shouldn't know I'm Caesar daughter"*. The God-Mode agent returned
`[God Mode turn — no narrative]` and persisted `directive_062d0899`:

> "Spartacus, Crixus, Sura, and the Capuan gladiator rebels do NOT know that Gaia Julia is Julius
> Caesar's daughter; they only know her as 'Gaia of Ariminum'…"

plus a matching `custom_campaign_state.core_memories` correction string. Both are campaign-local —
this is the patch, not the fix.

## Static diagnosis (the actual root cause)

1. **Delivery gap.** `shared/hidden_identity_knowledge_boundaries.md` is included only at
   `mvp_site/prompts/god_mode_instruction.md:144`. `narrative_system_instruction.md` and
   `narrative_lite_system_instruction.md` include only the generic
   `shared/npc_knowledge_boundaries.md` (lines 244 / 201).
2. **Burial.** On the served request for the failing turn
   (`CombatAgent`, `turn_index IS NULL` row, 903,111 bytes,
   `/tmp/wa-repro-caesar/req_turn322_full.json`):

   | token | hits | % of served prompt |
   |---|---|---|
   | `hidden identity` | 0 | — |
   | `true identity` | 1 | 71.5% |
   | `knowledge_tier` | 10 | 72.0–72.5%, 84.9–85.0% |
   | `direct_observations` | 4 | 71.8%, 72.5%, 85.2–85.3% |
   | `reveal_witnesses` | 10 | 71.8–72.5%, 84.7–84.9% |
   | `convenience knowledge` clause | 1 | **85.4%** |

3. **No record to consult.** All 48 `npc_data` entries expose only
   `age/alignment/attitude/attitude_to_party/class_name/entity_id/gender/hp_*/level/location/mbti/name/relationships/relationships_obj/role/status/tier`;
   `custom_campaign_state.npcs` absent; `npc_data["Spartacus"].knowledge_tier is None`; `Agron` had
   no `status`/`level` at all. Matches `docs/designs/audit/lane2-prompt-surface.md`
   ("prompt-named only — no HANDLER").

## Replay (ablation) — NON-REPRO, single sample

- Test subject `sdRkTbh9IGa5FY5Z5qfu` under `jleechantest@gmail.com`
  (`0wf6sCREyLcgynidU5LjyZEfm7D2`), copied from the source campaign.
- Ablation: removed `directive_062d0899` (35 → 34 directives) and the matching correction memory.
- Ingress: local Flask, real services; `POST /api/campaigns/sdRkTbh9IGa5FY5Z5qfu/interaction/stream`
  with `X-Test-User-ID` + `X-Test-Bypass-Auth: true`, exact turn-322 user string.
- Result: 7,532 chars, scene 503, 38 s. Gladiator dialogue: *"A pampered Roman girl in silk—why did
  we not slit her throat and strip her gold?"* → Spartacus: *"Because you are fools… Did you look
  upon her guard?"* Zero `Caesar` hits in NPC speech (the 2 occurrences are narrator-side "Umbrae
  Caesaris" / "Julian supply networks").
- Verdict: `NON-REPRO` for the exact phenotype in a single sample; the source scene stands as a
  `HISTORICAL RED ARTIFACT`. The copy sat ~22 turns past the original, so the negative is not a fix.

## Artifacts

`/tmp/wa-repro-caesar/{source_story.txt, req_turn322_full.json, replay_run2.log,
replay_narrative.txt, ablation.txt, issue-body.md, verdict-comment.md}`
