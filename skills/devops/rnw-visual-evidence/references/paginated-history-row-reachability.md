# Reaching a specific historical row for a capture (verified 2026-10-25)

Goal shape: a fix hides/rewrites one row identified by id (e.g. `seed-prompt-0`), and the proof needs
that exact row rendered in both a pre-deletion build and the candidate build — without creating data,
minting tokens, or injecting state.

**Verified end state (2026-10-25, `worldai_frontend` PR277):** the marked opening row WAS reached in
both phases, on the same campaign (`YjQyXr4n87k3GbjGujrZ`), same session, same driver, producing a
matched pair — pre-deletion `6575b8ae` renders the literal `CAMPAIGN SETUP` label; candidate `0c9201f9`
renders the same row node (`y:102, h:28`) with no text. Both phases: **8 control clicks, 690 wheel
gestures, 19 history pages**, ending at `scrollTop == scrollHeight − clientHeight` with the control gone.

## 1. Inventory the real controls before writing the driver

```bash
# the loader the UI actually calls (scrolling alone never calls it)
sed -n '4206,4222p' src/screens/GameScreen.tsx
#   <Pressable testID="load-older-entries" accessibilityLabel="Load older entries"
#              disabled={olderHistoryLoading || isLoading || isStreaming || undoInFlight}
#              onPress={() => { void handleLoadOlderHistory(); }} />
# the row marker the candidate renders when it hides content
grep -rn 'message-creation-seed-row' src/components/MessageBubble.tsx
# dashboard list/search semantics
grep -n 'filterAndSortCampaigns\|campaign-search-input\|campaign-item-' src/screens/CampaignsScreen.tsx
```

`filterAndSortCampaigns(campaigns, searchQuery, …)` reads only the **loaded** page, so search cannot
find a campaign that infinite scroll has not fetched. If the app *itself* resumes the target campaign on
`GET /` (body contains the campaign title / `resumed_marked: true`), use that — it is the app's supported
resume flow, not injected navigation.

## 2. Driver loop: click to page, wheel to reveal — BOTH, alternating

The single most expensive mistake: treat these as alternatives. They are two halves of one loop.

- **Clicking pages the data** (`scrollHeight` grows, e.g. `14,257 → 112,437`) but the viewport stays
  where it was, so the newly prepended row is thousands of px away and **never renders** (`seed_nodes: 0`
  even though the payload contains `seed-prompt-0`).
- **Wheeling only** reaches the end of *currently loaded* content and stops, with the
  `Load older entries` control still on screen — that is not the campaign start.
- **Scripted `scrollTop`/`dispatchEvent('scroll')`** is a third trap: it can drive a container that is
  not the rendered list at all. Verified: 138 synthetic scroll steps reported `at_end: true` while the
  screenshot stayed byte-identical to the pre-scroll frame. Never diagnose a pagination failure from it.

```python
STATE = """() => {
  const el=document.querySelector('[data-testid="messages-list"]');
  const body=document.body.innerText||'';
  const hit=document.elementFromPoint(197,420);   // WHICH surface is under the wheel
  return {top: el?Math.round(el.scrollTop):null, ch: el?el.clientHeight:null, sh: el?el.scrollHeight:null,
          max_reachable: el?Math.round(el.scrollHeight-el.clientHeight):null,
          seed_nodes: document.querySelectorAll('[data-testid="message-creation-seed-row"]').length,
          has_btn: !!document.querySelector('[data-testid="load-older-entries"]'),
          hit: hit?{tag:hit.tagName, testid:hit.getAttribute('data-testid'),
                    text:(hit.innerText||'').trim().slice(0,40)}:null};}"""

page.mouse.move(197, 420)                      # once; keep the pointer over the transcript
for cycle in range(1, 26):
    btn = page.query_selector('[data-testid="load-older-entries"]')
    if btn is not None:                        # 1) page the data with the real control
        before = len(pages)
        btn.scroll_into_view_if_needed(timeout=10000); page.wait_for_timeout(800)
        btn = page.query_selector('[data-testid="load-older-entries"]')
        if btn is not None and btn.is_enabled():
            btn.click(timeout=6000, force=True)
        for _ in range(40):                    # wait for the real cursor request
            page.wait_for_timeout(500)
            if len(pages) > before: break
        page.wait_for_timeout(1500)
    # 2) reveal the NEW loaded end with ONE monotonic direction, settled after each gesture
    stagnant = last = 0
    for _ in range(40):
        st = page.evaluate(STATE)
        if st["top"] >= st["max_reachable"] - 4: break
        if st["top"] == last:
            stagnant += 1
            if stagnant >= 3: break
        else:
            stagnant, last = 0, st["top"]
        page.mouse.wheel(0, -1500)             # sign that ADVANCES toward older (measure it, don't assume)
        page.wait_for_timeout(650)
    st = page.evaluate(STATE)
    if st["seed_nodes"] or st["has_btn"] is False and st["top"] >= st["max_reachable"] - 4:
        break
```

Record per cycle: `clicked`, `wheels`, `top`, `sh`, `max_reachable`, `seed_nodes`, `has_btn`, pages so
far. Record per response: every `/story` URL+status, `n`, `first`, `last`, `has_older`, `oldest_id`,
and any `seed-*` ids. Stop reasons worth naming: `window_established`, `control_absent_hasOlder_false`,
`max_cycles`.

## 3. Failure signatures and what they mean

| receipt | meaning | next step |
|---|---|---|
| `campaign_item_absent_from_dashboard` / `_after_search` | specimen beyond the loaded page; search is client-side | drive the list's own infinite scroll, or use the app's resume flow |
| `clicks: 0`, `pagination_requests: []`, `row_nodes: 0` | never entered the transcript | fix navigation first, not assertions |
| clicks load pages (`sh` grows) but `seed_nodes: 0` and viewport mid-campaign | **row prepended out of view** | wheel monotonically to the new end, keep looping |
| monotonic wheel stops with `Load older entries` still visible | end of *loaded* content, not campaign start | click to page more, then wheel again |
| `scrollTop` oscillates between two values | you alternated wheel direction, or the control is disabled mid-load | one direction only; wait for the request |
| both phases byte-identical sha256 | classifier never matched the persisted ids | check the id scheme against the record before capturing (§0.48) |

**Do not call it a container clamp** unless a *monotonic* sequence stalls at `top == max_reachable`.
A bidirectional probe manufactures its own ceiling and will make you report a false blocker.

## 4. Assertion traps that faked a negative

- **Case-sensitive text detectors.** `body.includes('Campaign setup')` returned `false` on the
  pre-deletion build because the UI renders `CAMPAIGN SETUP`. The frame showed the label plainly. Use
  case-insensitive matching, and when the boolean and the pixels disagree, the pixels win — disclose the
  detector bug instead of citing the flag.
- **Identity from rendered text.** `signed_in = "My Campaigns" in body` wrote `signed_in: false` while
  every `/api/` request carried a bearer token and account data rendered. Never publish a heuristic
  boolean as identity evidence; read real SDK claims (`currentUser.getIdTokenResult(false)` →
  `uid`, `email`, `email_verified`, `firebase.sign_in_provider`) in memory and record booleans only.
- **Zero rendered nodes ≠ absent data.** Virtualized lists render only the window. Establish row
  presence from the API payload (ids/flags only, no body text) and row visibility from the frame.

## 5. Video/hash hygiene for these runs

- **Hash `record_video` files only after `ctx.close()`.** Hashed earlier, Playwright's webm is a partial
  chunk: observed snapshot sizes `1,048,576` (1 MiB) and `524,288` (0.5 MiB) that later became
  `1,225,172` and `841,081`. Daily-looking sizes that are exact powers of two are the tell.
- An `ffmpeg -f concat` aggregate over per-context webms will **never** equal the sum of parts (container
  rewrite), and if the source directory changed after the aggregate was built the mismatch is arbitrary.
  Record the concat list, the aggregate sha256, and compare `ffprobe` durations — or do not present the
  aggregate and the receipts as one packet.
- A long run produces 2+ webm per context (Playwright rolls files); list every one with size + sha256.

## 6. Host pitfalls (Linux headless Chrome, persistent profile)

- A killed run leaves the profile's `SingletonLock`, so the next launch dies with
  `Failed to create a ProcessSingleton for your profile directory`.
- **Do not** `pkill -f "<profile path>"`: the pattern also matches your own ssh/bash command line and
  kills the session you are working in. Kill by inspecting `/proc/*/cmdline` and only signalling
  processes whose `argv[0]` starts with the browser binary, e.g.:

```python
for pid in filter(str.isdigit, os.listdir("/proc")):
    argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    if argv and argv[0].startswith(b"/usr/bin/google-chrome") and b"<profile>" in b" ".join(argv):
        os.kill(int(pid), signal.SIGKILL)
```

Then `rm -f <profile>/SingletonLock` and relaunch. Long runs should be detached (`nohup … &`) with the
receipt log polled, because a foreground ssh call dies at the terminal tool's timeout while the browser
keeps holding the lock.

## 7. API-side existence search (read-only, no UI)

```
GET /api/campaigns?limit=40                       -> campaign list
GET /api/campaigns/<id>?story_limit=50            -> newest window (often a BOUNDARY, has_older:true)
GET /api/campaigns/<id>/story?before_id=<oldest>  -> page backwards to campaign start
```

Search all returned entry ids against the classifier regex. Report `scanned`, `pages`,
`first_window_was_newest_boundary`, and any match with `{campaign, id, actor, mode, is_initial}` — never
the narrative text. A match found only on a deep page is normal, not a contradiction of an earlier
"not found". Also record whether the final page reports `has_older: false` and `oldest_id` — that is how
you prove history start rather than inferring it.
