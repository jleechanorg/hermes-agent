# Native iOS before/after by swapping the JS bundle (no xcodebuild)

Measured 2026-10-24 producing before/after pixels for a `CampaignsScreen` row change
(campaign-list portraits, worldai_frontend PR #276) when the host was at load average ~600
and an xcodebuild was not affordable.

Use this lane when **only JS/TS changed** (no `package.json` / `app.json` / `ios/` / Podfile drift
since the installed build) and you need real iOS pixels for A/B of the exact candidate.

If the thing you are evidencing is "a list field the app expects is missing", read
[campaign-list-payload-fields.md](campaign-list-payload-fields.md) first — the list endpoint projects a
fixed field mask, so the server (not the client) is usually the missing link.

## 0. Two facts that decide everything

- A **Debug** sim build bakes its Metro port into the binary (`WorldAIClaw.debug.dylib`, no
  `main.jsbundle`). If another lane owns that Metro port, you cannot serve your own JS — use a
  **Release** app (it embeds `main.jsbundle`, Hermes bytecode) instead.
- A Release binary only runs JS that matches its **native module set**. Check before you plan:

```bash
for d in ~/Library/Developer/CoreSimulator/Devices/*/; do
  app=$(ls -d "$d"data/Containers/Bundle/Application/*/*.app 2>/dev/null | head -1); [ -n "$app" ] || continue
  exe=$(ls "$app"/WorldAIClaw "$app"/WorldAI "$app"/seedhead 2>/dev/null | head -1); [ -n "$exe" ] || continue
  echo "$(basename $d) bundle=$([ -f "$app/main.jsbundle" ] && echo yes || echo no) \
push=$(strings -a "$exe" | grep -c ExpoPushTokenManager) secure=$(strings -a "$exe" | grep -c ExpoSecureStore)"
done
```

Symptom of a mismatch: launch returns to SpringBoard, and
`~/Library/Logs/DiagnosticReports/WorldAIClaw-*.ips` shows
`RCTFatalException: Unhandled JS Exception: Error: Cannot find native module 'ExpoPushTokenManager'`
(`RCTFormatError` in `lastExceptionBacktrace`). The crash report does **not** carry the JS message —
read it from `xcrun simctl spawn <UD> log show --last 5m --predicate 'process == "WorldAIClaw"'`.

## 1. Find a signed-in device without reading auth values

Signed-in state lives in
`<data container>/Library/Application Support/ai.worldarchitect.app/RCTAsyncLocalStorage_V1/manifest.json`.
Test only **key-name presence** (`"@worldclaw/auth-token" in data`); never print or copy values.
A scripted scan is in `scripts/scan-sim-apps.sh` (auth-key presence, Release bundle, native modules).

## 2. Build the bundle (two commands)

```bash
cd <worktree>
EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8099 npx expo export:embed \
  --platform ios --entry-file index.js \
  --bundle-output "$OUT/main.js" --assets-dest "$OUT/assets" \
  --dev false --unstable-transform-profile hermes

<worktree>/node_modules/react-native/sdks/hermesc/osx-bin/hermesc \
  -emit-binary -O -out "$OUT/main.jsbundle" "$OUT/main.js"     # -out, NOT -output
```

- Verify the format: `head -c 8 main.jsbundle | xxd` → `c61f bc03 …` (same Hermes magic as the
  installed bundle).
- Prove which side a bundle is with a source marker: `grep -c "campaign-portrait" main.js`
  (0 for origin/main, ≥1 for the candidate) and `grep -c "127.0.0.1:8099" main.js`.
- `EXPO_PUBLIC_*` is inlined at bundle time, so a swapped bundle can point the app at a **local
  backend** with no native rebuild. The sim reaches the host at `127.0.0.1`; the app's Info.plist has
  `NSAllowsLocalNetworking = true`.

## 3. Local backend that accepts the app's existing token

```bash
cd <backend PR worktree> && bash -lic '
  export PORT=8099 WORLDAI_DEV_MODE=true
  export CAMPAIGN_RATE_LIMIT="1000000 per hour, 100000 per minute"   # + the other *_RATE_LIMIT vars
  python3 -m mvp_site.main serve > /tmp/localbackend8099.log 2>&1'
```

- **`WORLDAI_DEV_MODE=true` is required** or every request 401s with
  `ValueError: WORLDAI_GOOGLE_APPLICATION_CREDENTIALS requires WORLDAI_DEV_MODE=true`.
- Without generous rate limits the app renders `getCampaignsPage: 429`.
- Service-account creds come from `~/.bashrc` (`bash -lic`), so real Firestore works and the sim's
  existing Firebase ID token (same project) authenticates — no re-login.
- Before blaming the client, prove the data path with the real code:
  `python3 -c "from mvp_site import firestore_service; ..."` in the PR worktree and print
  per-campaign field presence (this is also good PR evidence).

## 4. Swap, capture, restore

- **Back up the installed `main.jsbundle` first.** Overwriting it without a copy is not recoverable
  from the device; you must rebuild or reinstall.
- Copy only `main.jsbundle`. The font warnings
  (`assets/assets/fonts/Geist-Medium.ttf: No such file or directory`) are non-fatal; the app still runs.
- `simctl terminate` + `launch`, then screenshot at ~30 s **and** ~120 s: a large account
  (7 245 campaigns) is still on skeleton loaders at 35 s.
- Same device, same account, same backend, only the bundle swapped = a clean A/B. Restore the original
  bundle when done.

## 5. Host contention and input

- `simctl` wedges (even `xcrun simctl version` hangs, 19 stale `simctl help` children):
  `kill -9 $(ps aux | grep '[C]oreSimulator.CoreSimulatorService' | awk '{print $2}')` — launchd
  restarts it on the next call; then `pkill -9 -f simctl` and retry. Booting a shutdown device via
  `launch` also blocks; prefer `xcrun simctl bootstatus <UD> -b`.
- On a heavily loaded host every simctl call takes minutes: run capture sequences as **one background
  script with notify_on_complete**, never foreground, and never `| tail` a long-running lane
  (buffered output = zero visibility until exit).
- `idb ui tap` fails with `Could not create instance of SimulatorKit.SimDeviceLegacyHIDClient /
  No Legacy HID port found` on headless-booted devices (Xcode 26). Fall back to the window:
  `open -a Simulator --args -CurrentDeviceUDID <UD>`,
  `osascript -e 'tell application "Simulator" to activate'`, then `cliclick c:<x>,<y>`.
  Measured mapping (iPhone Air, window at 634,38 size 460x981, device 420x912 at scale 1.0):
  `screen = (654 + deviceX, 86.5 + deviceY)`.
- A click that changes nothing is not proof of a broken handler: hash two consecutive screenshots.
  Identical sha256 = the input never landed (same rule as
  `references/native-sim-input-and-harness.md`).

## 6. Package the evidence honestly

- State: device class + OS, exact bundle shas for both sides, and that the native binary, account and
  backend were identical.
- Disclose unrelated frame differences instead of hiding them (e.g. the `Showing 50 of N campaigns`
  counter reads `50 of 50` vs `50 of 7246` because the server's optional `total_count`
  count-aggregation intermittently returns null — not part of the change).
- Publish for the PR body: `diskm evidence-push <dir> --repo <repo> --slug <slug>` →
  `gs://wa-test-evidence/agent-evidence/<repo>/<slug>/…`, and verify the
  `https://storage.googleapis.com/…` URL returns 200 before linking it.
