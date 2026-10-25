---
name: wa-npc-knowledge-boundary-leak
version: 1.0.0
category: worldarchitect
description: Use when an NPC states a fact it could not have observed.
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [worldarchitect, prompts, knowledge-boundary, hidden-identity, npc-omniscience, repro, pydantic-gap]
    related_skills:
      - wa-bq-forensics-read
      - wa-live-server-smoke
      - wa-emit-contract-gap-diagnosis
      - wa-prompt-engineering
related_skills:
  - wa-bq-forensics-read
  - wa-live-server-smoke
  - wa-emit-contract-gap-diagnosis
  - wa-prompt-engineering
last_verified: 2026-10-23
---

# WA NPC knowledge-boundary leak (NPC says what it could not know)

## When to Use

Fire this skill when a player reports any of:

- "they shouldn't know I'm <X>" / "he shouldn't know that" / "nobody told them"
- an NPC names the PC's secret parentage, true name, faction, ability, or plan never revealed
- an NPC references an event or location it was not present for ("convenience knowledge")
- an NPC treats a hidden identity as public ("the town has become suspicious of you")
- a `/repro` arrives as "the NPC knew something it shouldn't" (campaign state, not UI)

Bug class: the LLM attributes knowledge to an NPC that the NPC never observed, was never told, and
could not have inferred — most commonly a **hidden player identity** ("Caesar's blood or no, she was
alone with ten men"), but the same shape covers a protected secret, an unrevealed ability, a dead
NPC treated as alive, or knowledge of events the NPC was not present for.

Distinguish from neighbours:

| Symptom | Correct skill |
|---|---|
| NPC states an unobserved fact | **this skill** |
| A UI field renders blank / internal text leaks into the UI | `wa-emit-contract-gap-diagnosis`, `player-facing-content-leak-diagnosis` |
| The player's God-Mode directive was ignored | `repro` Step 0.77 / `wa-bq-forensics-read` |
| NPC treated as alive after death (state, not knowledge) | `wa-bq-forensics-read`, npc-status sub-classes |

## What already exists in the prompt layer (check before proposing a fix)

There are **three** pre-existing shared contracts, and the delivery asymmetry between them is the
usual root cause:

| File | Included in | Covers |
|---|---|---|
| `mvp_site/prompts/shared/npc_knowledge_boundaries.md` | `narrative_system_instruction.md:244`, `narrative_lite_system_instruction.md:201` | generic witness/hearsay rule, 0–5 rumor ladder, "convenience knowledge" anti-pattern |
| `mvp_site/prompts/shared/hidden_identity_knowledge_boundaries.md` | **`god_mode_instruction.md:144` ONLY** | the identity-specific boundary, per-NPC `knowledge_tier` / `rumors` / `direct_observations` / `reveal_witnesses` |
| `mvp_site/prompts/shared/witness_based_reveal_continuity.md` | `god_mode_instruction.md:310`, ascension ceremonies only | witness-set bounding of a reveal |

So the contract that actually forbids "this NPC knows the PC's true identity" is delivered to the
**God-Mode agent**, not to any agent that writes narrative (Story / Dialog / HeavyDialog / Combat).
That asymmetry is the finding to prove or disprove first.

`docs/designs/audit/lane2-prompt-surface.md` records the companion gap: those four knowledge fields
are **prompt-named only — no HANDLER** (no Pydantic class, no JSON-schema entry, no TypedDict). The
prompt tells the model to consult records nothing writes.

## Diagnostic — three static checks, no live turn needed

**1. Is the owning contract in the narrative prompt set at all?**

```bash
grep -rn "PROMPT_INCLUDE:shared/hidden_identity_knowledge_boundaries\|PROMPT_INCLUDE:shared/npc_knowledge_boundaries" \
  mvp_site/prompts/*.md mvp_site/prompts/*/*.md
```

If the identity contract appears only under `god_mode_instruction.md`, stop here — the narrative
agents never received it, and no amount of prompt-rule rewording in `narrative_*.md` helps until the
include is added.

**2. Where does the generic rule land in the SERVED prompt?**

Pull the failing turn's full `request_json` (see `wa-bq-forensics-read` — the `turn_index IS NULL`
row carries the ~900 KB payload; the `turn_index=N` row is a ~400-byte stub) and report hit count
**plus percent position** for `hidden identity`, `knowledge_tier`, `direct_observations`,
`reveal_witnesses`. Past ~85% = buried in the lost-in-the-middle zone. Verified 2026-10-23
(CombatAgent turn 322, 903,111 bytes): `hidden identity` 0 hits; `knowledge_tier` 10 hits at
72.0–72.5% and 84.9–85.0%; the "convenience knowledge — if the record does not support it, the NPC
does not know it" clause at **85.4%**.

**3. Does the canonical record the rule references actually exist?**

```python
nd = state["npc_data"]
fields = sorted({k for v in nd.values() if isinstance(v, dict) for k in v})
"knowledge_tier" in fields                  # → False on the verified campaign
"npcs" in state["custom_campaign_state"]    # → False
```

Observed `npc_data` key union on a 48-NPC campaign: `age, alignment, attitude, attitude_to_party,
class_name, entity_id, gender, hp_current, hp_max, level, location, mbti, name, relationships,
relationships_obj, role, status, tier`. No knowledge fields anywhere → the rule has nothing to
consult, so the model falls back on narrator omniscience.

## Evidence gathering (source campaign, read-only)

Read Firestore directly instead of copying: `users/<uid>/campaigns/<cid>/game_states/current_state`
plus the `story` subcollection sorted by `timestamp`. Doc IDs are `turn_rid_<rid>_user` / `_ai`, so
the failing turn's `rid` falls out of the quote's doc ID. Grep the **U+2019** apostrophe form —
`"Caesar's blood"` with ASCII `'` returns 0 hits on the user's own prose.

For the strongest check, look for the NPC having *correctly* only suspected earlier: on the verified
campaign Spartacus had said "She calls herself Gaia of Ariminum… But it is a mask. A lie" without
naming parentage, and two scenes later a different NPC asserted the parentage outright. A prior
correctly-bounded line in the same campaign is the best proof that the later line is an unsupported
claim rather than a prior reveal.

Do the same for the cover directive: the player's own words ("I go incognito as a lower tier noble
woman") are the canonical boundary, not the narration.

## Reproduction

Ablate the player's post-bug patch on a twin copy (remove the campaign-local identity directive +
the matching correction `core_memory`), then replay the exact input through local Flask with real
services. Full boot/auth/SSE mechanics: `wa-live-server-smoke` § "Copy-campaign SSE replay lane".

Verdict discipline: a single non-reproducing sample is `NON-REPRO` for the exact phenotype, **not**
proof of a fix — the copy always sits tens of turn indices past the original. The static checks
above are the root-cause proof; the replay is only the phenotype check.

## Fix shape (prompt-layer, campaign-agnostic)

Per `mvp_site/prompts/AGENTS.md` § "Shared rules across agents" — one rule, one file, included via
`{{PROMPT_INCLUDE:...}}`, pinned by a contract test:

1. Add `{{PROMPT_INCLUDE:shared/hidden_identity_knowledge_boundaries.md}}` to
   `narrative_system_instruction.md` and `narrative_lite_system_instruction.md` (and confirm the
   CombatAgent prompt set covers it), with a contract test pinning the include per narrative agent.
2. Move the "convenience knowledge / the NPC does not know it" clause above the ~85% budget cut so
   it lands inside the attended window.
3. Either add a handler/emission contract for `knowledge_tier` / `direct_observations` /
   `reveal_witnesses` or retire those field names from prompt prose — instructing the model to
   consult records that do not exist is itself the defect.
4. Never ship a per-campaign directive as the fix. A campaign-local `god_mode_directives` entry
   (e.g. "Spartacus, Crixus, Sura … do NOT know that Gaia Julia is Julius Caesar's daughter") patches
   one campaign; every fresh hidden-identity campaign repeats the leak.

## Pitfalls

1. **Treating the campaign-local player directive as root cause.** It was filed *after* the leak and
   names specific NPCs; it cannot generalize and it is not where the bug lives.
2. **Grepping only one phrase.** `hidden identity` returned 0 hits while `knowledge_tier` returned
   10 — reporting the first alone would have falsely claimed total absence.
3. **Reading the stub BQ row.** The 442-byte `turn_index=322` row makes every token look absent.
4. **Claiming a fix from a clean replay.** See verdict discipline above.
5. **Including the identity contract but leaving it buried at 85%.** That reproduces the same failure
   with a different file name.

## Reference

- `references/2026-10-23-hidden-identity-leak-caesar.md` — the verified end-to-end case: source
  scene quote + doc IDs, the three static checks with exact hit counts and positions, the ablation
  replay result, and the filed issue/bead.
