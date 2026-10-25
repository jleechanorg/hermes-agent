# Two-head RN/Expo-web capture against a loopback mock backend

Verified 2026-10-24 on `jleechanorg/worldai_frontend` PR #115 (debug/timing panel: scattered ms
footer → one consolidated panel in seconds). Everything below was actually run in that session;
the quoted panel strings are the ones rendered by the harness.

## Why the dev server cannot be used

- Web uses **relative** URLs so requests hit the Metro origin:
  `private url(path) { if (Platform.OS === 'web') return path; }`
- The in-app bypass is explicitly off for web:
  `shouldBypassAuth() { if (Platform.OS === 'web') return false; }`
- `metro.config.js` proxies `/api/*` only to `BACKEND_TARGETS.stable` / `.dev` (Cloud Run), and its
  own bypass injection is gated on a **loopback** target, which those never are.

Net effect: a dev-server web session either talks to production Cloud Run or 401s. Do not "just add
`EXPO_PUBLIC_ALLOW_TEST_AUTH_BYPASS=true`" — it cannot reach a local backend from web.

## Working harness

### 1. Export both heads

```bash
# candidate
cd <pr-worktree>      && nvm use 22.22.0 && npx expo export --platform web --output-dir /tmp/web-after
# baseline: separate worktree at origin/main, node_modules symlinked from the candidate checkout
cd <main-worktree>    && ln -s <pr-worktree>/node_modules node_modules \
                      && npx expo export --platform web --output-dir /tmp/web-before
```

Record each bundle hash for provenance:
`shasum -a 256 /tmp/web-<ref>/_expo/static/js/web/index-*.js` (filenames differ per head — that is the
cheapest "the two exports really are different sources" receipt).

### 2. Loopback backend with mock services + test bypass

```bash
cd <wa-repo>
GAC=/dev/null MOCK_SERVICES_MODE=true TESTING_AUTH_BYPASS=true WORLDAI_DEV_MODE=true \
  PORT=8081 python3 -m mvp_site.main serve          # direct; ./local.sh also demands an MCP port
```

Prove the bypass header pair (names matter — a single `X-Test-Bypass-Auth` alone 401s):

```bash
curl -s -H 'X-Test-Bypass-Auth: true' -H 'X-Test-User-ID: test-harness-1' \
  http://localhost:8081/api/settings      # -> 200 + debug_mode/cerebras_model/...
```

A turn stream returns SSE with `metadata` / `chunk` / `state` / `done`. The `done` payload carries
`structured_response.debug_info` **and** a top-level mirror; in mock mode it contains
`agent_mode/model/agent_name` and **no** `time_to_first_chunk_seconds` /
`llm_stream_generation_seconds` — that is why panels read “unavailable”.

### 3. Static + API proxy (`scripts/static_api_proxy.py`)

One process per ref: serves the export, forwards backend paths to `:8081` with the bypass headers.
Because the browser is same-origin, no CORS work is needed. Note: do **not** send a
`Transfer-Encoding: chunked` header yourself — `http.client` already decoded the body; let the
connection close delimit it (`protocol_version` default 1.0), which keeps SSE streaming working.

### 4. Seed the two app-level gates

```python
CONSENT = (
  "localStorage.setItem('@worldclaw/auth-token','harness-token');"
  "localStorage.setItem('@worldclaw/auth-source','manual');"
  "localStorage.setItem('@worldclaw/ai-data-consent','granted');"
  "localStorage.setItem('@worldclaw/ai-data-consent-scopes',JSON.stringify(['*']));"
)
ctx.add_init_script(CONSENT)
```

Symptoms when a gate is missing:

| missing | symptom |
|---|---|
| `@worldclaw/auth-token` | landing page: “Sign in · Continue with Google” |
| `@worldclaw/ai-data-consent` | turn never POSTs; toast “AI data sharing is off, so your action was not sent.”; `proxy.log` shows only GETs |

### 5. Capture

- `pw.chromium.launch(headless=True, channel="chrome")` when the ms-playwright browser cache is absent.
- `context(record_video_dir=…, record_video_size=viewport)` needs Playwright's ffmpeg:
  `python -m playwright install ffmpeg` (one file, ~1 MiB) even though Chrome launches fine.
- Create nothing inside the page; **reuse an existing campaign** and click
  `[data-testid="campaign-item-<id>"]`. A campaign created moments earlier can fail to appear in the
  rendered list and the click times out.
- A scene-illustration zoom overlay can auto-open and hide the list (visible text
  `zoom harness | reopen | ×`, only ~8 test ids). Dismiss (click `×` / `Escape`) before asserting the
  list exists.
- Type with `click()` + `keyboard.type(...)`, not `fill()` — RNW controlled inputs need the events.
- Selector per head (see SKILL.md §0.8); scan **all** matching nodes and take the one whose text has
  real values, never `.last`.

Observed panel strings (the actual evidence, same campaign, same replayed turn):

```
BEFORE  origin/main 887cae70   TTFC: 7084ms · First narrative: 7200ms · Stream: 16073ms · Total: 23157ms · Chunks: 6
AFTER   PR head b5191b21       Time streaming start: 7.1 s
                               Stream time: 16 s
                               Total time: 23 s
                               Agent: CharacterCreationAgent (character_creation)
                               Model: gemini/gemini-3.8-flash
                               First narrative: 7.2 s · Chunks: 6 · Req: req-pr115-replay
```

### 6. Replaying telemetry the mock cannot produce

`readDebugTurnInfo` / the stream parser read the timings off the `done` **envelope** (top level), not
`structured_response`. So patch there:

```python
def handle(route):
    resp = route.fetch(); body = resp.text()
    out = []
    for line in body.split("\n"):
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev.get("type") == "done":
                ev["payload"].update(REPLAY)          # time_to_first_chunk_seconds, llm_stream_generation_seconds, ...
            out.append("data: " + json.dumps(ev)); continue
        out.append(line)
    route.fulfill(status=resp.status, headers=resp.headers, body="\n".join(out))
```

Use values from a **real** recorded turn (here: the operator's own screenshot, 7,084 ms / 23,157 ms) and
say so on the artifact. This is rendering/formatting proof only.

### 7. Captions and side-by-side (macOS)

```bash
FONT=/System/Library/Fonts/Supplemental/Arial.ttf   # homebrew ffmpeg has drawtext
ffmpeg -y -i before.webm -vf "drawtext=fontfile=$FONT:text='BEFORE — origin/main <sha> — old footer (ms)':\
fontcolor=white:fontsize=15:box=1:boxcolor=black@0.75:boxborderw=8:x=(w-text_w)/2:y=48" \
  -c:v libx264 -pix_fmt yuv420p before.mp4
# unequal durations: freeze the shorter tail with tpad, then hstack
ffmpeg -y -i before.mp4 -i after.mp4 -filter_complex \
  "[1:v]tpad=stop_mode=clone:stop_duration=25[a];[0:v][a]hstack=inputs=2[v]" -map "[v]" \
  -c:v libx264 -pix_fmt yuv420p side-by-side.mp4
```

## Labelling rule

Every artifact from this lane states: *mock-at-network — local `mvp_site` `MOCK_SERVICES_MODE=true`,
bypass identity via task-owned proxy, timing values replayed from a real turn.* It is **supplementary**:
it proves the rendering/formatting delta, not real-auth or real-service latency. The genuine gate still
needs an authorized signed-in session (Google-OAuth-only sign-in means one manual sign-in or the native
lane) — report that as the remaining barrier, never as “blocked, here is a fixture instead”.

## Related dispatch gotcha (same session)

Dispatching the branch reconciler: `bash -lic 'pil -p "<multi-line prompt>"'` breaks on inner quotes
(`bash: syntax error near unexpected token '('`). Write the prompt to a file and use
`bash -lic 'cd <worktree> && pil -p "$(cat /tmp/<task>-prompt.txt)"'`.
