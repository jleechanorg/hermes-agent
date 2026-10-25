# Campaign-creation → opening view: the three raw-text defects (verified 2026-10-24, PR #277)

Scope: `jleechanorg/worldai_frontend` — what the Adventure screen shows immediately after the wizard
creates a campaign. All three symptoms appear in one 10.8 s device recording; all three have distinct
root causes and distinct proofs.

## 1. The `GOD` row full of `Character: … | Setting: … | Description: …`

- That row is the campaign's **first saved story entry**, not a client artefact: `mvp_site`
  `create_campaign` writes the server-built `initial_prompt` with the deterministic doc id
  `seed-prompt-<i>` (`mvp_site/firestore_service.py:5934`, format built by
  `world_logic.py`'s `_build_campaign_prompt` — the legacy pipe-delimited string is documented at
  `mvp_site/world_logic.py:7240`). Wizard campaigns write the same pair via `add_story_entry`.
- The client mirrors the doc id: `mvpSiteClient.ts` history mapping sets `serverId: e.id`, so the row
  is identifiable **positively by id** — never by content sniffing.
- **The row must stay in the transcript**: bead `jleechan-uh3.3` / PR #126 renders the seed row from
  stream start so opening-story completion inserts nothing (removes an ~80 px prose jump). So the fix
  is "keep the row and its reserved height, drop the internal text" — a labelled placeholder with a
  `minHeight`, not a removal, and no `GOD` mode label on it.
- Real God-mode **actions** are written by the normal turn path with server-minted random ids, so an
  id-based predicate can never hide them; keep a test asserting exactly that.

## 2. Upside-down "Preparing your opening story…" card

- `GameScreen` renders openings upright (`inverted={!readingOpening}`) but the empty-state style
  carried `transform: [{ scaleY: -1 }]` unconditionally. An inverted `FlatList` already flips its
  `ListEmptyComponent`, so the counter-flip must exist **only while the list is inverted**.
- Fix shape: one `const listInverted = !readingOpening` feeding both the list prop and a separate
  `emptyContainerInverted` style; assert both orientations in a component test.

## 3. Literal `### Campaign Summary` / `- **Title** — …` while the turn streams

- PR #270 taught `MessageBubble` to render the *completed* creation turn as a callout + label/value
  card, and explicitly left streaming raw (its "Streaming note (known limit)").
- Streaming text is rendered as plain tail text, so the fix locates only the creation-summary heading
  in the tail (including a half-typed `### Camp…`), renders complete rows through the existing
  structured renderer, and returns text before/after the block verbatim.
- **Wrapper-gating trap**: `splitStreamingCreationSummary()` always returns `{ narrative, summary }`
  with `summary: null` when nothing matched. Gating the JSX on `if (result === null)` is never true,
  so every streaming message silently took the summary branch and the caret left the tail text — a
  regression the *targeted* suites missed and the full suite caught. Gate on the inner block.

## Evidence shape that was accepted

- Component-lane RN-web renders of the real `MessageBubble` with the verbatim saved seed string, at
  393×720 @2x, base head vs PR head, page errors 0, sha256 per artifact, committed under
  `docs/evidence/pr277-creation-seed/` with a README naming the method and the limits.
- The orientation fix is proven by a jest style assertion, **not** by those frames (it needs the full
  `GameScreen` surface) — say so rather than implying the pixels cover all three.
- Real-device recording stays the BEFORE for the user-visible symptom; fixture/component renders are
  supplementary, never native proof.
