# Bundle environment + auth-boundary receipts (RNW / Expo web)

Worked example, 2026-10-24, PR under test served from two locally-built Expo web arms.

## 1. "No `.env`" is not "variable unset"

Evidence gathered, in increasing strength:

```bash
ls -l .env*                      # only .env.example present  → weakest signal, says nothing final
grep -n '^EXPO_PUBLIC_GOOGLE' .env.example      # keys listed, values empty (template)
python3 -c "import json;print(json.load(open('eas.json'))['build'])"   # build-profile env (public values)
grep -rl 'apps.googleusercontent.com' --exclude-dir={node_modules,.git} .  # docs/tests often carry the public id
```

Then the decisive read — the **served bundle**:

```bash
curl -s "http://127.0.0.1:<port>/index.bundle?platform=web&dev=true&hot=false&lazy=true" -o b.js
grep -c '<the public client id>'          b.js     # value inlined?
grep -c 'disabled-web-client-id'          b.js     # fallback sentinel present?
```

Three states, report which you measured:

| value hits | sentinel hits | verdict |
|---|---|---|
| ≥1 | ≥1 | variable WAS set at build (value inlined) |
| 0 | ≥1 | built without it → app shows "Not Configured" |
| 0 | 0 | **inconclusive** — the module isn't in this bundle (harness/entry shim), say so |

## 2. Classify the auth outcome, don't collapse it

- **Configuration failure:** sign-in button disabled, or the app's own dialog
  (`testID: google-signin-unconfigured-dialog`, "This build has no Google OAuth client ID configured").
  Cheap to detect: `[data-testid="landing-google-sign-in"]` present but click yields an in-app dialog,
  no popup.
- **Authorization-configuration failure:** popup opens and the provider rejects the origin. Decode it:

```python
import base64, urllib.parse, json
u = json.load(open('clean-signin.json'))['popup_url']
e = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)['authError'][0]
print(base64.urlsafe_b64decode(e + '=' * (-len(e) % 4)).decode('utf-8', 'replace')[:400])
# -> "redirect_uri_mismatch\nYou can't sign in to this app because it doesn't comply with Google's OAuth 2.0 policy…"
```

- **Auth denial:** provider-side 401/403 for a registered origin (rare; usually it is the class above).

Rules:
- Never report a redirect-URI mismatch as "auth blocked" — it is fixable configuration, and fixing it
  is a Google-console (security-setting) change, outside a capture/evidence task.
- Never copy cookies/tokens or reuse another profile's auth state to get past any of these.
- Sessions are **origin-scoped**: `https://<registered-origin>` sign-in does not transfer to
  `http://127.0.0.1:<port>`. The only clean routes are (a) an operator already signed in *on that exact
  origin*, or (b) an origin already registered for that client.

## 3. Probe harness notes

- `record_video_dir` requires the Playwright `ffmpeg-*` binary in the browser cache; if it is missing,
  `context.new_page()` fails with *"Executable doesn't exist at …/ffmpeg-1011/ffmpeg-mac"* before any
  navigation. For a matrix-only reachability probe, omit video entirely and say the run had no video.
- Screenshot + DOM-matrix sampling is enough to answer "did the flow reach the provider"; a popup URL
  plus a decoded `authError` is a stronger receipt than a picture of an error page.
