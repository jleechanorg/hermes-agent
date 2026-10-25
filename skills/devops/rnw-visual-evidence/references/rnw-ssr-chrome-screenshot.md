# One-worktree RNW SSR → system-Chrome screenshot lane (verified 2026-10-24)

Session: `worldai_frontend` PR #287 — "Social Skill Challenge card should be light purple, reserve
yellow for tooltips". A two-line accent swap needed genuine dark/light before-after pixels, with no
Playwright dependency, no HTTP server, no second worktree, and no signed-in app.

This is the cheapest honest component lane when the change is a token/colour/prop swap. It is
**component-level** evidence — supplementary to `/es`, never acceptance.

## Shape

```
scratch_visual/
  SocialChallengeCardBefore.tsx   # copy of the component with ONLY the line under test reverted
  app.tsx                         # 2x2 grid: dark/light x before/after, real themes, captions
  render.tsx                      # renderToStaticMarkup(element + getStyleElement) -> index.html
  render.cjs / index.html         # generated
capture: before_after.png
```

## app.tsx core

```tsx
import { AppRegistry } from 'react-native-web';
import { themes } from '../src/theme/themes';
import { getLavenderColor, getAccentColor } from '../src/theme/styleguide';

function Panel({ themeName, before }) {
  const theme = themes[themeName];
  return (
    <div style={{ background: theme.backgroundColor, width: 360, padding: 18 }}>
      <div style={{ fontFamily: 'system-ui', fontSize: 12, textTransform: 'uppercase' }}>
        {themeName} — {before ? 'BEFORE' : 'AFTER'}
      </div>
      {/* caption prints the helper AND the hex that is actually in effect */}
      <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 10 }}>
        {before ? getAccentColor(theme) : getLavenderColor(theme)}
      </div>
      {before
        ? <SocialChallengeCardBefore card={MODEL} theme={theme} />
        : <SocialChallengeCard card={MODEL} theme={theme} />}
    </div>
  );
}

AppRegistry.registerComponent('App', () => App);
const { element, getStyleElement } = AppRegistry.getApplication('App', { initialProps: {} });
export { element, getStyleElement };
```

`MODEL` is the exact block from the reporter's screenshot (title, fields, HP, status text), so the
artifact answers the report rather than a synthetic placeholder.

## render.tsx core

```tsx
import fs from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { element, getStyleElement } from './app';

const body = renderToStaticMarkup(element);
const css = renderToStaticMarkup(getStyleElement());   // REQUIRED — RNW emits class CSS
fs.writeFileSync('index.html',
  `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#c9c9d2}*{box-sizing:border-box}${css}</style>` +
  `<body><div id="root">${body}</div></body>`);
```

## Commands

```bash
# the worktree needs its own deps; an empty node_modules in the main checkout makes symlinks useless
ls node_modules | wc -l            # 0 => run npm ci
npm ci --prefer-offline --no-audit --no-fund

npx --yes esbuild@0.23.1 render.tsx --bundle --platform=node --format=cjs \
  --outfile=render.cjs --alias:react-native=react-native-web --jsx=automatic --log-level=error
node render.cjs                    # -> index.html

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --hide-scrollbars --force-device-scale-factor=2 --window-size=840,900 \
  --screenshot="$PWD/before_after.png" "file://$PWD/index.html"
```

## Verification that counts

```bash
grep -oE "#d8b4fe|#d4a843|#7e22ce|#6b4400" index.html | sort | uniq -c   # all four present
grep -c "SURRENDERED" index.html                                        # one per panel
shasum -a 256 before_after.png                                          # record bytes + hash
```

Then read the PNG back with vision: four panels, correct captions, gold→lavender delta visible in
both themes, no clipping. Vision confirmed exactly that here; the DOM/token grep is the ground truth
and vision is the delta check.

## Traps hit this session

- `--format=cjs` makes `import.meta` empty → `new URL('./index.html', import.meta.url)` throws
  `ERR_INVALID_URL`. Write to a relative path after `cd`.
- Chrome prints `task_policy_set TASK_CATEGORY_POLICY: (os/kern) invalid argument (4)` and
  `Teardown watchdog expired; recording dump and terminating` **and still writes a correct PNG**.
  Never treat that stderr as a failed capture; check size/hash/vision.
- Without `getStyleElement()` the page is unstyled and every panel looks like browser-default text —
  the screenshot still succeeds, so this fails silently.
- `react-test-renderer` (the contract test, not this lane) has **no `.toJSON()`** on TestInstance, and
  `findAll(n => typeof n.type === 'string')` returns wrappers whose flattened style has no `color`.
  Read a coloured text node with
  `findAll(n => flatten(n.props.style ?? {}).color !== undefined)[0]`.
- A fresh worktree without deps fails `npx jest` with `Preset ts-jest not found relative to rootDir`
  — that is missing `node_modules`, not a jest config problem.

## Packaging

Keep `app.tsx`, `render.tsx`, `XBefore.tsx` + the PNG + `PROVENANCE.md` (sha256, bytes, source head,
base ref, reproduce commands, and the explicit "component render, not the app" line) in
`~/evidence/<topic>/`. The in-tree `scratch_visual/` directory is deleted after capture and
`git status --short` must be clean.
