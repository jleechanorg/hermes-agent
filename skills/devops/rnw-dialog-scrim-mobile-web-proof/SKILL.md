---
name: rnw-dialog-scrim-mobile-web-proof
description: Use when proving RN-web dialog outside-tap dismissal.
---

# RN-web dialog dismissal: real mobile-web BEFORE/AFTER proof

Proves, on the actual Expo/RN-web renderer against a real backend, that a dialog
closes on an outside-scrim tap, stays open on an inside-card tap, and that a
dialog with unsaved edits does NOT close.

## When to use
- A PR changes scrim/backdrop dismissal on `worldai_frontend` (`src/screens/*`, `src/components/*`).
- Unit tests only assert source strings (e.g. "block contains backdrop testID") and real visual acceptance is missing.

## Stack recipe (worldai_frontend + worldarchitect.ai)

1. **Backend** (no provider spend, real Firestore):
   ```bash
   cd ~/repos/jleechanorg/worldarchitect.ai
   PORT=8191 PYTHONPATH="$(pwd):$(pwd)/mvp_site" TESTING_AUTH_BYPASS=true ALLOW_TEST_AUTH_BYPASS=true \
     nohup ./vpython mvp_site/main.py serve > /tmp/wa-backend-8191.log 2>&1 &
   ```
   - `mvp_site/main.py serve` takes **no** `--port`; use the `PORT` env var.
   - **Both** `TESTING_AUTH_BYPASS` and `ALLOW_TEST_AUTH_BYPASS` are needed, and requests must send
     `X-Test-Bypass-Auth: true` (the Metro proxy adds it; bare `X-Test-User-ID` alone returns 401 "No token provided").

2. **Frontend worktree** for each candidate (head and base):
   ```bash
   git worktree add --detach ~/.worktrees/worldai_frontend/verify-<label> <sha>
   ln -s <pr-worktree>/node_modules node_modules
   printf '{"stable":"http://localhost:8191","dev":"http://localhost:8191"}\n' > src/services/backendTargets.json
   ```
   - `metro.config.js` proxies `/api/*` to `src/services/backendTargets.json`, **not** to
     `EXPO_PUBLIC_BACKEND_URL`, and it injects the dev-bypass headers only when that target is
     loopback. Pointing `stable`/`dev` at `localhost:8191` is the one local-only edit; keep it out of the PR branch.
   - Start: `EXPO_PUBLIC_ALLOW_TEST_AUTH_BYPASS=true DEV_USER_ID=dev-user-web DEV_USER_EMAIL=dev@worldarchitect.ai CI=1 npx expo start --web --port 1909X`
     (Node 22 via nvm).

3. **Playwright** (iPhone 15 viewport 393x852, DPR 2, `is_mobile`, `has_touch`, `channel="chrome"`):
   ```python
   ctx.add_init_script("localStorage.setItem('@worldclaw/auth-token','rt-mw-bypass');"
                        "localStorage.setItem('@worldclaw/auth-source','manual');")
   page.goto(url, wait_until="load")   # networkidle never settles on Metro
   ```

## Opening the surfaces
- Dashboard: `campaign-edit-<id>` (edit dialog, `testID="edit-dialog"` on the **backdrop**, no scrim → must stay open), `campaign-item-<id>` (play screen).
- Play screen info panel: click `session-pill-spells` / `session-pill-equipment` (NOT the overflow menu).
- Settings: `settings-button` then `content-policy-row`.
- DOM shapes: `info-panel-modal > div > div > [scrim button(data-testid=info-panel-backdrop), card div]`; the card is a bottom sheet (full width, bottom ~241px).

## Geometry proof (the part reviewers accept)
Never assume "outside". For every tap record `document.elementFromPoint(x,y)` and its `closest('[data-testid]')`:
- outside tap must resolve to the scrim testid (`info-panel-backdrop`, `content-policy-backdrop`, `edit-dialog`);
- inside tap must resolve inside the card and leave the dialog visible.

## Build the video
Compose BASE (left) / HEAD (right) PNGs with PIL captions, then
`ffmpeg -framerate 1/3 -i frame-%02d.png -vf fps=24,format=yuv420p -c:v libx264 -crf 22 out.mp4`.
Then `vision_analyze` one composited frame to confirm the panels/captions match the claim.

## Pitfalls
- `EXPO_PUBLIC_BACKEND_URL` is ignored on this path; the app calls same-origin `/api/*`.
- Playwright may lack its bundled Chromium → pass `channel="chrome"`.
- RN-web `Modal` children unmount when `visible=false`, so presence+box>0 is a valid "closed" signal.
- A `card` testID added by the fix does not exist at BASE — fall back to fixed coordinates measured on HEAD and record the hit testid.
- Keep `data-wfcard` tagging off the backdrop: tagging the backdrop makes every point read "inside card".

## Evidence bundle
Commit `docs/evidence/<slice>/` with `before-after.mp4`, `head/`, `base/` PNGs + `receipt.json`
(per-step `at_utc`) and a README stating stack, identity, campaign, timestamps and limits
(shared RN-web ≠ iOS-native; dev-bypass identity ≠ human Firebase sign-in).
