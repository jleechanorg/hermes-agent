# Capturing a component that renders inside RN `<Modal>` (verified 2026-10-23)

Session: `worldai_frontend` PR #178 — `PlayOverflowSheet` theme row, "chips wrap under the label at
large Dynamic Type". Component render (supplementary lane) was required; the naive harness produced
four PNGs that measured correct DOM but showed the **wrong row** in the pixels. This file records
the mechanism and the recipe that actually produced reviewable frames.

## Why page-level capture fails
- The component renders inside `Modal` → position-fixed overlay with its own `ScrollView`
  (`[data-testid="play-menu-scroll"]`), independent of the page scroll position.
- `row.scrollIntoView({block:'center'})` scrolls the **page**, not the sheet's scroller, so the fixed
  caption moves relative to the content and the row you measured is no longer the row on screen.
- `page.screenshot(full_page=True)` captured the sheet scrolled to its last row (`Settings`), while
  `getBoundingClientRect()` for `menu-theme-row` reported y≈113 — both "true", describing different
  states. `offsetTop`-based `scrollTop` maths fails for the same reason (offsetParent ≠ scroller).
- A `position: fixed` caption div lands mid-frame once the page has been scrolled, so the caption can
  overlap the very row under test.

## Recipe that worked
1. Render in a **tall viewport** (`393x1000`, dsf=2) so the whole sheet fits with `scrollTop = 0`.
   Never call `scrollIntoView` in the entry or the renderer.
2. Measure with one JS function and keep the object:
   `{row_flex_wrap, group_present, group_flex_wrap, group_justify, chips_same_line,
    light_below_label, label/fantasy/light rects}`.
   Wrapping test that matched the user report: `chip.y > label.y + label.h/2`.
3. Capture the element, not the page:
   `page.locator('[data-testid="play-menu-sheet"]').screenshot(path=...)`.
4. Compose the caption in PIL: new RGB image = header strip + pasted sheet screenshot, draw the
   title lines on the strip, save as the final artifact. Nothing can overlap because the caption is
   outside the captured pixels.
5. Sanity check before believing any delta: at **default** text size a layout-only change should give
   **byte-identical** before/after sheets (`_sheet-before-default.png` and `_sheet-after-default.png`
   hashed equal here — that identity *was* the expected result, not a bug). A big difference at 1.0x
   means a caption/scroll leak.

## Playwright ffmpeg for video
`p.chromium.launch(channel="chrome")` works, but `new_context(record_video_dir=...)` +
`new_page()` fails with
`Executable doesn't exist at .../ms-playwright/ffmpeg-1011/ffmpeg-mac`.
Fix once per host: `~/.local/orch-venv/bin/python -m playwright install ffmpeg` (~1 MiB).

## Vision verification caveat
Reading a dense 393px-wide UI with a vision model is unreliable: it confidently reported "only the
Settings row is visible", "Settings at the top", and "Fantasy and Light sit above the Theme label"
for frames whose DOM said otherwise. Rules:
- Crop tightly around one element and upscale 2x before asking; ask for words + relative position,
  not a general impression.
- When vision and the live DOM disagree, the DOM measurement is the claim; say "measured in the live
  DOM" and stop iterating the harness to satisfy the model.
- Put the measurement text *inside* the artifact (PIL header/footer) so a reviewer reads numbers
  rather than trusting a description.

## Package layout produced
`evidence/<pr>/` with `before-default.png`, `before-large.png`, `after-default.png`,
`after-large.png`, `_sheet-*.png` (raw element captures), harness entries + `build.py`/`compose.py`,
and `manifest.json` carrying both SHAs, worktree paths, viewport, text-scale method, per-artifact
sha256+bytes, the measurement table, the SUPPLEMENTARY class line, and the exact limitation
("component render; no real backend/sign-in; primary gate still owed").
