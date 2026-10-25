# Metro/Expo two-arm A/B binding — shell vs bundle vs PID cwd

Worked example, 2026-10-24, `jleechanorg/worldai_frontend` PR #257 (RNW zoom viewer).

## The three identities, and which one is evidence

| Layer | Command | Proves |
|---|---|---|
| HTML shell | `curl -s http://127.0.0.1:$P/ \| shasum -a 256` | only that both arms run the same Metro dev shell (1,461 B, `3f0e731d…`). Says NOTHING about arm source. |
| JS bundle | `curl -s "http://127.0.0.1:$P/index.bundle?platform=web&dev=true&hot=false&lazy=true&transform.engine=hermes&transform.routerRoot=app&unstable_transformProfile=hermes-stable" \| shasum -a 256` | the source actually executing in the browser. Differs per arm (`ea1dd45e…` 4,434,138 B vs `a098203d…` 4,434,112 B). |
| Process binding | `lsof -nP -iTCP:$P -sTCP:LISTEN` → PID → `lsof -p $PID \| awk '$4=="cwd"{print $9}'` → `git -C <cwd> rev-parse HEAD` | which worktree/commit that port really serves. |

Note the bundle hash is **build-scoped** (see SKILL.md rule 13): a dev server rebuilds per request, so
record it as "this build only" and pair it with a head-bound marker count
(`grep -c '<string added by the fix>' bundle.js` → 1 candidate / 0 baseline).

## The IPv4/IPv6 collision that silently swaps arms

`lsof -nP -iTCP:8091 -sTCP:LISTEN` returned **two** rows:

```
Python 40373 127.0.0.1:8091   # /tmp/pr115_proxy.py /tmp/web115-after 8091  (SimpleHTTP + X-Test-Bypass-Auth)
node   52904 *:8091           # expo start --web, cwd = pr257-web-cand @ f32dbf5e
```

`http://127.0.0.1:8091/` resolves to the IPv4 row → **PR115's static export**, not the PR under test.
`http://[::1]:8091/` hits the Expo server. Capture scripts that hardcode `127.0.0.1` silently produced
20+ minutes of wrong-bundle "evidence" (identical frames on both arms because both were one bundle).

Detection: two listeners on one port, or a `Server:` header that is not Metro (`SimpleHTTP/0.6`).
Fix: bind every script to a port you proved with the PID+cwd triple, prefer a fresh port per arm, and
record the port inside the artifact JSON (`port`, `url`, `bundle_sha256`) so the artifact cannot be
re-read against the wrong arm.

## Exact-source packaging for another operator

```bash
git -C <worktree> archive --format=tar.gz -o /tmp/pr-src-<sha>.tar.gz <sha> \
  -- src assets public modules scripts package.json package-lock.json app.json \
     babel.config.js metro.config.js jest.config.cjs index.js App.tsx tsconfig.json .env.example
shasum -a 256 /tmp/pr-src-<sha>.tar.gz
```

`git archive` emits only the committed tree → no local harness shim, no `.env`, no `node_modules`, no
build output. Sanity checks before transfer:

```bash
ls -l .env* 2>/dev/null            # expect only .env.example (empty values)
grep -riE 'BEGIN .*PRIVATE KEY|client_secret|refresh_token|ya29\.' <extracted>/ | head
```

Deps without a network install: `ln -s <worktree-with-identical-lock>/node_modules <clean-arm>/node_modules`
after proving `shasum -a 256 package-lock.json` is identical in both.
