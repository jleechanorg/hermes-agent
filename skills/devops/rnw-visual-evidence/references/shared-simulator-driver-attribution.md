# Shared-simulator driver attribution — worked case (2026-10-24, worldai_frontend PR #125)

Task: iOS BEFORE/AFTER pixels for a Markdown→card renderer change on a shared Mac simulator.
Outcome: **no capture produced** (lane collision) — but the collision itself is the reusable lesson.
Do not read this file as "how to capture"; read it as "how to lose a device in four commands".

## Timeline (PDT)

| time | action | result |
|---|---|---|
| 22:53 | `simctl list devices booted` | answered in seconds → reported "control plane recovered" |
| 22:55 | started Metro `--port 8081` from PR worktree (`5346a56d`) | `packager-status:running`, 9 log lines |
| 22:56 | `simctl terminate` + `simctl launch … -jsLocation localhost:8081` | app not visible 18 s later; screenshot = SpringBoard |
| 22:58–23:02 | retried launch | `simctl launch` hung, exit 124; **PID appeared ~100 s later** |
| 23:02 | screenshot | app up, showing a *different campaign* (last saved screen) |
| 23:03 | `lsof -a -p <app-pid> -iTCP` | **8 ESTABLISHED sockets → 127.0.0.1:8082**, i.e. the other lane's Metro |
| 23:03 | own Metro log check | **zero** `Bundled`/`GET` lines → my tree never served the app |
| 23:04 | `strings …/WorldAIClaw.debug.dylib \| grep -oE "localhost:80[0-9][0-9]"` | literal `localhost:8082` (baked) |
| 23:05 | other agent's coordination message | live Scenes driver on the same UDID; ACK stand-down requested |
| 23:06 | `pkill -f "<worktree>/.bin/expo start --port 8081"` | port 8081 → 0 listeners; 8082 tunnel untouched |

## What each probe actually proves

```bash
# 1. Is my bundle the one on screen? (the only question that matters)
lsof -nP -a -p <app-pid> -iTCP | grep -c 8082        # 8  -> not my port
grep -E "Bundled|GET /" <my-metro>.log | wc -l       # 0  -> never served
tail -6 <their-metro>.log                            # "iOS Bundled 455ms index.js" at my relaunch minute

# 2. Why the launch flag was ignored
strings <App>.app/<App>.debug.dylib | grep -oE "localhost:80[0-9][0-9]"   # localhost:8082
```

- `ps` argv showing `-jsLocation localhost:8081` is **not** evidence the app used 8081; argv is what you asked for,
  sockets are what happened.
- `simctl list devices booted` healthy + `simctl launch` timing out is a normal mixed state, not a wedge verdict.
- The installed Debug shell had **no** `main.jsbundle` (`ls <App>.app/main.jsbundle` → absent) plus
  `WorldAIClaw.debug.dylib` → Metro-served shell; its packager port is fixed at build time.

## Lane-collision handling that the other driver accepted

1. First line: **"ACK stand-down"** + the released state (`:8081` stopped, 0 listeners; `:8082` untouched; their app
   reconnected; no simctl of mine in flight).
2. Explicit disclosure of what *had* run: one terminate, one launch, no install, no Metro repoint, no
   account/campaign/settings write, and which relaunch produced the screen they saw recover.
3. One-line proof per claim (`lsof` counts, Metro log line counts, their tunnel PIDs).
4. Retained source work (clean worktree at the PR head, deps staged) and a single next action gated on **their**
   handback — no second menu, no new device, no new writer.

## Anti-patterns this session committed

- Treated "ledger released + video finished" as "device free", then mutated the app.
- Started a Metro before proving which port the installed app reads.
- Reported "control plane recovered" from `list` alone; `launch` was still stalling.
- Answered repeated one-word "Status?" pings with full re-verification essays instead of a 5-line delta.
