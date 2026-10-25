# RN old-site parity: instant next-scene header + follow the live end (worldai_frontend, 2026-10-23)

Case: user posted two phone screen recordings — one of the legacy site, one of the RN app — with
*"iOS and new website needs to render the header for next scene and scroll down like old website.
Right now it does not. I want the iOS header to load immediately even faster than old site."*

## 1. Derive the parity spec from the recordings before touching code

```bash
# both files arrive at ~720x1558 (phone). Tile them so one vision call compares many frames.
ffmpeg -v error -i <old>.mp4 -vf "fps=1/4,scale=200:-1,tile=5x5" -frames:v 2 /tmp/a_tile_%d.png
ffmpeg -v error -i <new>.mp4 -vf "fps=1/2,scale=200:-1,tile=4x3" -frames:v 1 /tmp/b_tile_1.png
```

Then ask the vision pass concrete questions: *does the content shift on send? when does the Session
card first appear? does a "scroll to view" pill appear?* Tile frames at 1 fps for the send window when
the tile resolution is too low to time an event.

Findings that mattered:
- **Old site**: on Send the story area jumps to the bottom and the next scene's `.session-header`
  (Timestamp/Location/HP/XP/Gold + Equipment/Stats/Spells) is painted into the pre-narrative region as
  soon as server metadata lands. Reader then stays at the live end.
- **RN app**: on Send it *did* scroll and *did* show `SCENE N · NARRATOR · Writing…` + skeleton, but the
  Session card only appeared at the end, and a `New story streaming, scroll to view ↓` pill appeared —
  i.e. the header was missing and the view had drifted off the live end.

Reading the recordings this way prevents the wrong fix ("iOS doesn't scroll at all") — the actual asks
were *header content* and *staying at the end*.

## 2. Read the LEGACY implementation, not the new one, to define the target

`mvp_site/frontend_v1/app.js` (old site) anchors:
- `scrollToBottom(storyContent)` at submit (~:9304) — the live-end placement.
- `buildStreamingSessionHeaderHtml(fullData)` (~:8049) — the card + quick-action pills, with an explicit
  placeholder guard: `!header || header === "undefined" || /Location:\s*Unknown/i.test(header)` → render
  nothing rather than "Unknown".
- `renderStreamingPreSections` called from `streamingClient.onMetadata` — this is *when* the card appears.
- `scheduleInitialNarrativeReveal` / `readerFollowing` — follow only while the reader has not moved.

## 3. Root causes in the RN app (worldai_frontend @ ccfeb348)

1. `src/state/gameStore.ts` `APPLY_CHUNK` dropped the header-only chunk:
   `if (currentTurnGmIdx < 0 && !sceneText?.trim()) return state;`
   `mvpSiteClient` dispatches `{delta:'', scene_text:'', session_header}` when it sees
   `[SESSION_HEADER]` or `metadata.session_header` before any text — that dispatch was discarded, so the
   card could only appear with the first narrative chunk (or `done`).
2. The view-level in-flight cell (`IN_FLIGHT_GM_ID`) rendered `InFlightMeta` + `InFlightSkeleton` only —
   no Session card, so nothing to show even if the header were in state.
3. The single authorized submit placement (`attemptSubmitReveal`) targeted the response's **beginning**
   via `sectionRevealOffset(edge, viewport)`, and the growth anchor (`preserveWebPosition` /
   `maintainVisibleContentPosition`) deliberately pinned the view there ("IOS-2: the reader's position is
   authoritative"). Net effect: the growing turn drifted off screen and the KeepReading pill appeared.

## 4. Delivered fix shape (PR #260)

- `gameStore`: new `streamingSessionHeader: string | null`. The header-only chunk is *recorded*, not
  dropped; it still does **not** open the GM message (keeps the `Sending…` hold + skeleton, spec 4.3).
  The first narrative chunk / `APPLY_DONE` hands it onto the real GM message and clears the capture.
  Cleared on `SEND_MESSAGE`, `CREATE_SESSION`, `LOAD_HISTORY`, `APPLY_DONE`, `FAIL_TURN`, `CANCEL_TURN`
  so it never leaks across turns.
- `StoryInfoCards`: extract `SessionHeaderCard` (card + pills) so the in-flight cell and settled turns
  share one implementation — the card cannot double-render during the hand-off.
- `GameScreen`: in-flight cell renders `streamingSessionHeader ?? previousGm?.sessionHeader`
  (carry-forward ⇒ visible *before* the server responds, i.e. faster than the legacy site; no card at all
  when neither exists, never fabricated "Unknown").
- `GameScreen` scroll: LIVE placement targets inverted offset 0 (the live end) instead of the response
  beginning; `followLiveEnd` re-pins on **owned growth only** (submitted cell + list header, growth-only,
  never from `onScroll`, so it cannot feed itself); every manual-movement provenance (drag begin, wheel
  with delta, movement keys, touch/pointer, scrollbar drag) clears following; the pill re-arms following
  while the turn is still writing. OWED RETURN placement and the ownership latch (submissionId +
  campaign + epoch) untouched; the opening-reader placement untouched.

## 5. Verification — and the gap to state honestly

- `npx tsc --noEmit` clean; 8 focused suites / 107 tests; full `npx jest` 310 suites / 3248 tests
  (one pre-existing load-flaky suite proven on the unmodified baseline).
- **Gap**: `react-test-renderer` does not simulate native `maintainVisibleContentPosition`, so the follow
  path is proved as wiring + pure geometry, not as device behavior. On iOS the native anchor can produce a
  non-zero offset before the layout-driven follow runs; if that exceeds the 48 pt end tolerance the follow
  may skip one growth event. Say this plainly and require a signed-in mobile-web + iOS-sim run before
  claiming `/es`.

## 6. Reversal note

This work *undoes* the earlier "IOS-2: never auto-scroll during streaming" decision that the same repo
shipped weeks before. Both were user-requested. Treat the scroll policy as instruction-scoped: read the
current request, keep the provenance-cancellation machinery, and rewrite the comments/tests that encode
the old rule instead of leaving contradictory docs behind.
