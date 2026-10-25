# Account-switch (A → sign out → B) reproduction preconditions

Class of task: a bug report says "after switching accounts I get *Request blocked: signed-in
account changed* / *Failed to load campaigns*". This is a **multi-identity** repro. Before spending
a single capture cycle, prove you actually have two usable identities in **one** browser context,
and prove you can get your session back before you destroy it.

Measured 2026-10-24 on `worldai_frontend` (RNW mobile web, Expo dev server, real Flask backend).

## 1. Preflight, in this order (cheap → expensive)

| # | Check | Command / probe | What it decides |
|---|---|---|---|
| 1 | Which browser identities exist | `aside account list` | one Google identity per profile → **no switch possible** without a password |
| 2 | How many Google accounts a profile holds | `aside --account uN repl "openTab('https://accounts.google.com/AccountChooser?continue=https%3A%2F%2Fmyaccount.google.com%2F')"` then read `document.body.innerText` | "Choose an account: <one row> / Use another account" = **single identity**. Read-only; no credentials touched |
| 3 | Is there an existing app session on the origin | open the app URL, read `document.body.innerText` for `Signed in with Google · <email>` | a warm session exists (per origin *including port*) |
| 4 | **Can sign-in be started at all** | hook `window.open`, real-click the sign-in button, read the popup URL | `redirect_uri_mismatch` ⇒ no sign-in on that origin; also tells you what you will lose by signing out |
| 5 | Is the app deployed on a registered origin | `curl` `/mobile`, `/app`, `/expo`, `/_expo/static/js/web/index.js` | all 404 ⇒ the dev server on `localhost:<port>` is the only mobile-web lane |

Run 4 **before** 5's consequence bites: signing out a warm session on an origin whose sign-in
is broken is unrecoverable from your lane.

## 2. Hard invariants that decide feasibility

- **Firebase web auth persistence is per origin, port included.** A session on
  `http://localhost:8099` does not exist on `http://localhost:8082`. Never assume a warm session
  transfers between dev-server ports.
- **Google (GAIA) identity is per Chromium profile.** Two Aside accounts (`u0`, `u2`) are two
  browser profiles, i.e. two separate sessions — switching between them never exercises the
  same-tab path the bug lives in. Do not present two-profile captures as an A→B switch.
- **A second identity in one profile requires a password.** "Use another account" is password
  entry. Ask for it; never copy tokens/cookies between profiles (`storage_state` transplant of a
  Firebase session is credential copying, not acceptance).
- **Fence error is thrown client-side, before the network call.** In `worldai_frontend`
  `src/services/sendGuard.ts`, `assertSendAllowed()` throws
  `Request blocked: signed-in account changed` when `currentSubject() !== pin.subject`
  (`getFirebaseAuth().currentUser?.uid`). So an authentic repro may contain **no failing HTTP
  request** — expect 200s in the network log and the error only in the rendered UI/console.
- **Which environments can even produce it:** `guardApplies()` is
  `(!__DEV__ && Platform.OS !== 'web' && isReleaseBaseline(EXPO_PUBLIC_BACKEND_URL)) || (__DEV__ && Platform.OS === 'web')`
  — i.e. **dev-mode web** or **release-native on the stable backend**. A production web build is
  inert; a dev-web `expo start --web` lane is valid. Say which one you ran.

## 3. Capture technique: get the true OAuth failure, not the generic one

`el.click()` from `evaluate()` has **no user activation**, so `window.open` is refused and the app's
generic catch reports `Google Sign-In Failed / Could not start Google login flow` — a misleading
result that looks like an app defect. Real CDP input grants activation and surfaces the real error.

```js
// 1. hook BEFORE any click so the authorize URL is recorded
await t.evaluate(() => {
  window.__open = [];
  const ow = window.open;
  window.open = function () {
    let res = null, err = null;
    try { res = ow.apply(window, arguments); } catch (e) { err = String(e).slice(0, 200); }
    window.__open.push({args: Array.prototype.slice.call(arguments).map(String), ret: res ? 'window' : 'null', err});
    return res;
  };
});
// 2. real input at the button's centre, not a JS click
const r = await t.evaluate(() => { const b = [...document.querySelectorAll('[role=button],button,a,[tabindex]')]
  .find(e => /Continue with Google/i.test(e.innerText || '')); const q = b.getBoundingClientRect();
  return {x: Math.round(q.x + q.width / 2), y: Math.round(q.y + q.height / 2)}; });
await t.mouse.click(r.x, r.y);
// 3. read the popup URL — it usually carries the verdict
console.log('OPEN=' + JSON.stringify(await t.evaluate(() => window.__open)));
```

The authorize URL gives the receipt directly:
`redirect_uri=http%3A%2F%2Flocalhost%3A8099`, `response_type=id_token`,
`client_id=<web client>`. When Google rejects the origin the popup lands on
`accounts.google.com/signin/oauth/error?authError=<base64url>`, and decoding it yields
`redirect_uri_mismatch` plus Google's policy sentence:

```python
import base64
print(base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', 'replace'))
```

## 4. Screenshots: never print the base64 into the transcript

`annotatedScreenshot(t)` returns `{base64Image}`; one shot was ~430 KB and two inline prints blew
past 500 KB of tool output and got truncated. Redirect the REPL to a file and decode it:

```bash
aside --account u2 repl "$(cat /tmp/flow.js)" > /tmp/flow.out 2>&1
```

```python
# one JSON object per line: parse line-prefixed, not with a greedy regex across SHOT1..SHOT3
for line in open('/tmp/flow.out'):
    if line.startswith('SHOT5='):
        open(png, 'wb').write(base64.b64decode(json.loads(line[6:])['base64Image']))
        print(os.path.getsize(png), hashlib.sha256(open(png, 'rb').read()).hexdigest())
```

Report size + sha256 for the delivered path only. Also read the measured viewport
(`innerWidth x innerHeight`, `devicePixelRatio`) and put it in the report; macOS window resizing
does not necessarily change the tab viewport, so never label a capture "mobile width" without the
measured number.

## 5. Provenance while the tree is dirty

Worktree `origin/main` can be **ambiguous** (`git show-ref | grep remotes/.*/main`), which makes
`git rev-parse origin/main` disagree with `git rev-list HEAD..origin/main`. Pin the full ref
(`refs/remotes/origin/main`), then record ancestry explicitly:

```bash
git merge-base --is-ancestor HEAD refs/remotes/origin/main && echo ancestor=yes
git rev-list --count refs/remotes/origin/main..HEAD   # ahead
git rev-list --count HEAD..refs/remotes/origin/main   # behind
```

Hash the served dev bundle too (`curl '/index.bundle?platform=web&dev=true&…' | shasum -a 256`)
and name the backend process (`lsof -p <pid> | cwd`, repo HEAD, start time) — a warm `:8081`
`python -m mvp_site.main serve` may be many commits behind its own origin.

## 6. When the repro is impossible: the capability receipt

Return, in this order: what you ran (URL, port, head, bundle sha, backend pid/head, viewport/UA) →
real runtime results with statuses → the exact blocker(s) with raw provider output → what is NOT
proven → **side effects you caused**. In this session that last item mattered: signing out
`jleechantest@gmail.com` cleared its `localhost:8099` session and the origin's sign-in was broken
(`redirect_uri_mismatch`), so it could not be restored — the Google account was untouched, but the
warm session was gone. Always state that class of cost explicitly.
