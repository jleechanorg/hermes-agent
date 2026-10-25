# Gesture-ordering route limit: can the web lane even reach the changed line?

Verified 2026-10-24 on `worldai_frontend` PR #257 (Photos-style zoom viewer, head `f32dbf5e`).
Three agents burned several capture rounds on a fix the web lane could never exercise. Decide this
**before** the first capture.

## 1. Read the fix's own trigger condition, then ask whether the platform can produce it

The fix under review changed one branch of `ZoomableImageViewer`'s pan handler:

```ts
if (st.base.scale <= MIN_ZOOM + 0.01 && !st.pinchActive && e.numberOfPointers === 1) { … dismiss mode … }
...
.onEnd((e, success) => {
  if (dismissY.value > 0) { finish('pan'); … }   // <- the line f32dbf5e adds
```

Trigger, in words: **a pinch ends while the pan is still ACTIVE**, committing a rubber-banded
sub-1x base, and only then does a one-finger drag enter dismiss mode. So the state the test needs is
`!pinchActive && panActive && numberOfPointers === 1`.

## 2. Check the platform's shipped handler, not the docs and not the harness

React Native Gesture Handler **2.28.0** on web —
`node_modules/react-native-gesture-handler/lib/module/web/handlers/PanGestureHandler.js`:

- `onPointerUp` (lines 212-230): if `state === ACTIVE` → `this.end()` **else** `resetProgress(); this.fail()`.
  A pan therefore terminates on *any* pointer-up, including the lift that ends a two-finger pinch.
- `onPointerRemove` (pointer-cancel class, lines 232-245) is the only path that can keep a pan alive
  when `trackedPointers >= minPointers`.
- The pinch keeps gesture ownership until the **last** finger lifts.

Consequence: the required state is structurally unreachable on RNW. Measured both ways —

- CDP partial pointer-up is expressible (`touchEnd[(175,400,id=1)]` → `pointerup id=2`,
  `touchend touches=1 ids=1`), yet after a verified single-finger lift a 40 px drag left
  `scale` frozen at `0.750` and `translateY 0.0` on **both** heads, release sprang to `1.000`
  on both;
- the harness trajectory shows the same: `0.8214 → 0.9244 → 0.9854 → 1.000`, `ty` stays `0.0`,
  `closes 0` on base and candidate.

So the two heads are **pixel-identical** on that route. That is a route limit, not a driver bug:
do not keep re-driving the same gesture hoping for a delta, and do not report END vs CANCEL as if
they were shown to differ.

## 3. Get a discriminating proof from the lane that can actually reach it

Handler-level replay of the *head's* regression test against the *base* source (`jest`) discriminates
cleanly — see `regression-test-proof-validity/references/head-tests-against-base-source.md`:

- base source + head test file → `4 failed, 26 passed` (`Expected: ArrayContaining [1, 0]`,
  `Received: [0]`);
- head source → `30/30 passed`.

Label that **regression proof**, never "visual evidence".

## 4. Auth reachability: prove it in one grep before promising an app-shell capture

The gate-accepted lane is a real signed-in run. Determine whether an agent can even open a session:

```bash
grep -rnE "signInWith(CustomToken|EmailAndPassword|Credential|Popup)|signInWithApple|signInWithGoogle" src/ | head
grep -rn  "EXPO_PUBLIC_DEV_|FIXTURE|DEV_CAMPAIGN|test_client_token_login" src/ app.json | head
```

In this repo the answer was **Google + Apple OAuth only** (`useFirebaseSignIn.ts` →
`signInWithGoogleFlow`; `services/firebase.ts` → `signInWithApple` / `signInWithCredential`),
with **no** email/password, custom-token, or dev-bypass seam in `src/`. OAuth-only ⇒ an interactive
human sign-in is required; say that once and name the owner instead of proposing fixtures.

Note: a dev-mode test login minted for the **python web app** (`/api/test_client_token_login` on
`:8081`, `WORLDAI_DEV_MODE=true`) does **not** transfer into a separate-origin Expo bundle — Firebase
web persistence is per-origin. It is not a shortcut around the interactive sign-in.

## 5. Reporting shape that survived review

- Served identity by **head + source-only marker**, not bundle hash: Metro `?dev=true` bundles are
  rebuilt per request (`:8093` sha256 `ea1dd45e…` → `bafff3d3…` within an hour, same marker count `1`).
- State the route limit as measured (handler source lines + the `ty 0.0`/`scale frozen` numbers),
  then the discriminating proof, then the single unblock and its owner.
- Attach the contact sheet **with its own caption** saying "identical on both heads = NOT
  discriminating" so a reader cannot mistake it for a fix demonstration.
