# Worked case: WorldAI iOS creation flow — seed row, upside-down card, raw summary

Observed 2026-10-24 from a 10.8s iPhone screen recording of the WorldAI app
(`video_d7b477af7106.mp4`, sha256 `9e5b30abb3109589d96515a6e1f6c7fdb13736ce83704bdaadddaf13a569b937`).
User's words: "Weird placeholder text during campaign creation delete it."

## String ledger (what the sweep found)

| t | Visible text | Role | Origin |
|---|---|---|---|
| ~8.6s | `Character: Luke \| Setting: Game of Thrones / Westeros \| Description: Universe / Fictional IP: Game of Thrones / Westeros` + `Protagonist: Luke` | conversation row labelled `GOD` | server-composed `initial_prompt`, displayed verbatim |
| ~8.6s | `Preparing your opening story…` / `Your campaign is saved. The narrator is writing your first scene.` | loading card | legit status — must be preserved |
| ~8.8s | panel content rendered 180° (OCR reads as reordered gibberish) | empty-state transform | orientation bug, not a text bug |
| ~10.4s | `### Campaign Summary`, `- **Title** — A Song of Iron and Shadows` | streaming narrator body | raw markdown during stream |

OCR-only reading of the flipped panel produced `bgnee obeuiva 2soLA / MLULIUG AONIL fILef eceuE` —
useless as a string but a reliable *signal* that a panel is inverted. Vision at 2× confirmed.

## Source binding

- The `GOD` label is not a subsystem: it is the **player-mode label resolver** on a seeded
  player row (`src/components/MessageBubble.tsx`, `resolvePlayerModeLabel` / `message-mode-label`).
  Grepping for `"GOD"` in the client finds nothing — grep for the label resolver instead.
- Client `src/` has **no** `Character: … | Setting: …` literal. The pipe format is
  server-side: `mvp_site/world_logic.py` documents it as the legacy
  `"Character: X | Setting: Y | Description: Z"` prompt format (in the worldarchitect.ai repo).
  Conclusion: render-side fix, not prompt-generation rewrite.
- Client-side composition lives in `src/utils/campaignWizard.ts` `composeDescription()`,
  which emits the `Universe / Fictional IP:` / `Protagonist:` marker lines used by the wizard.

## The contract that must NOT be regressed

Bead `jleechan-uh3.3` (PR126): *"show the seed prompt row from stream start so completion
inserts nothing (removes residual ~prompt-height jump)"*. The seed row exists on purpose —
hiding the row outright re-introduces the 80px prose jump at opening completion and the
blank band. Correct fix: hide/neutralise only positively identified seed-prompt rows, keep
their layout/height contribution.

Lesson: run `br list | grep -iE "seed|opening|summary"` before touching any "weird row" in a
creation/opening flow. A previously fixed scroll-anchoring bug is hiding behind ugly copy.

## Fix scope handed to the single writer

1. Hide only positively identified seed-prompt user/GOD rows; keep the height contract.
2. Empty-state transform must derive from the real list orientation (never double-flip).
3. Format/suppress the `### Campaign Summary` block during streaming without deleting real
   narrative or the `Preparing your opening story…` status.

Bead: `jleechan-xhi1`. Evidence rule: user's clip = BEFORE (full sha256 published);
AFTER = mobile-web (RNW) render of the same flow, captioned, no paid scene generation.
