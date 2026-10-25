# Preview-workflow provenance, stamped health, CORS and reviewer custody

Session evidence: 2026-10-24, `jleechanorg/worldai_frontend` PR #247 (`ci/pr-web-preview`), head
`c6a2a5af8c88c23eee22a093df4ef0aa8de1eace`, deploy run `39889162730`, live preview
`https://worldai-frontend-pr-247-i6xf2p72ka-uc.a.run.app`, backend
`https://mvp-site-app-dev-i6xf2p72ka-uc.a.run.app`.
Lane role: Hermes = reviewer; the branch had a declared sole writer, so nothing was pushed.

Companion pitfall: P25 in `SKILL.md`.

---

## 1. Provenance: what was built vs what was labelled

Run metadata says one thing, the checkout log says another:

```
$ gh run view 39889162730 --repo jleechanorg/worldai_frontend \
    --json headSha,event,conclusion --jq '{headSha,event,conclusion}'
{"conclusion":"success","event":"pull_request","headSha":"c6a2a5af8c88c23eee22a093df4ef0aa8de1eace"}

$ gh run view 39889162730 --repo ... --log | grep -aE 'Checking out the ref|HEAD is now at'
##[group]Checking out the ref
HEAD is now at a5fb4e2 Merge c6a2a5af8c88c23eee22a093df4ef0aa8de1eace into 6ae9f4fd056f5e4f6d068644d1907045b2a508a6

$ ... --log | grep -aE 'commit-sha|serves commit-sha'
  --labels "pr-number=247,commit-sha=***,app=worldai-frontend-preview"
✅ worldai-frontend-pr-247-00001-fvg serves commit-sha=c6a2a5af8c88c23eee22a093df4ef0aa8de1eace
```

Reading: the image was built from synthetic merge `a5fb4e21…` (head + base `6ae9f4fd…`), while the
revision label and the "verify" step both name the head. The label is written by the deploying job, so
it attests intent only.

Recovering the historical merge sha: **the run log is the only durable source.** `refs/pull/247/merge`
had already moved to `cc1ba0a0…` (merge of head into the newer main) by review time, so `ls-remote`
would have produced a plausible but wrong sha.

### Hardening applied in the retained patch

```yaml
# build job
- uses: actions/checkout@<pin>
  with:
    persist-credentials: false
    ref: ${{ env.PR_HEAD_SHA }}     # NOT the default refs/pull/<N>/merge

- name: Stamp build provenance into the export
  run: |
    set -euo pipefail
    HEAD_SHA=$(git rev-parse HEAD)
    [ "$HEAD_SHA" = "$PR_HEAD_SHA" ] || { echo "::error::built $HEAD_SHA != head $PR_HEAD_SHA"; exit 1; }
    shopt -s nullglob
    BUNDLES=(dist-web/_expo/static/js/web/*.js)
    [ "${#BUNDLES[@]}" -eq 1 ] || { echo "::error::expected one bundle, got ${#BUNDLES[@]}"; exit 1; }
    BUNDLE="${BUNDLES[0]#dist-web/}"
    grep -q "/${BUNDLE}" dist-web/index.html          # fail closed if index doesn't reference it
    BUNDLE_SHA=$(sha256sum "dist-web/${BUNDLE}" | cut -d' ' -f1)
    INDEX_SHA=$(sha256sum dist-web/index.html | cut -d' ' -f1)
    printf '{"pr_number":%s,"commit_sha":"%s","built_from_sha":"%s","event_sha":"%s","bundle":"/%s","bundle_sha256":"%s","index_sha256":"%s"}\n' \
      "$PR_NUMBER" "$HEAD_SHA" "$HEAD_SHA" "$EVENT_SHA" "$BUNDLE" "$BUNDLE_SHA" "$INDEX_SHA" \
      > dist-web/build-info.json
```

Post-deploy gate (binds served bytes, not labels):

```bash
SERVED=$(curl --fail -s "$PREVIEW_URL/build-info.json")
echo "$SERVED" | jq -e --arg sha "$PR_HEAD_SHA" '.commit_sha == $sha' >/dev/null
[ "$(jq -r .bundle_sha256 dist-web/build-info.json)" = "$(echo "$SERVED" | jq -r .bundle_sha256)" ]
curl --fail -s -o /dev/null "$PREVIEW_URL$(echo "$SERVED" | jq -r .bundle)"
curl --fail -s "$PREVIEW_URL/" | grep -q "$(echo "$SERVED" | jq -r .bundle | sed 's|^/||')"
```

Also split the jobs so PR-controlled build steps never see the SA key:
`build-web` (checkout → node → `npm ci` → `expo export` → stamp → upload-artifact, **no credentials**)
and `deploy-preview` (`needs: build-web` → creds guard → download-artifact → auth → deploy → verify).
Pinned artifact actions used: `upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02`,
`download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093` (resolve your own with
`gh api repos/actions/<action>/commits/v4 --jq .sha`).

---

## 2. `/health`: the behavioural proof harness (no docker needed)

`brew install nginx` is an acceptable autonomous install; then run the real server block instead of
trusting "it looks valid".

```bash
NGX=/opt/homebrew/opt/nginx/bin/nginx; T=$(mktemp -d /tmp/ngxcheck.XXXXXX); mkdir -p "$T/www" "$T/tmp" "$T/conf"
# 1) syntax, verbatim block (only ${PORT} substituted, as the image does)
sed 's/${PORT}/8080/' deploy/web-preview/nginx.conf > "$T/conf/server-verbatim.conf"
# 2) behavioural block: root substituted to a temp dir
sed -e 's/${PORT}/18081/' -e "s|root /usr/share/nginx/html;|root $T/www;|" deploy/web-preview/nginx.conf > "$T/conf/server.conf"
cat > "$T/conf/nginx.conf" <<EOF
worker_processes 1;
error_log $T/err.log;
pid $T/nginx.pid;
events { worker_connections 64; }
http { access_log off;
  client_body_temp_path $T/tmp; proxy_temp_path $T/tmp; fastcgi_temp_path $T/tmp;
  uwsgi_temp_path $T/tmp; scgi_temp_path $T/tmp;
  include $T/conf/server-verbatim.conf; }
EOF
$NGX -t -c "$T/conf/nginx.conf"        # syntax is ok / test is successful
```

Observed matrix (after switching the gate to `$document_root/build-info.json`):

| state | `GET /health` |
|---|---|
| `build-info.json` absent (empty/unstamped export) | `503 missing export stamp` |
| `build-info.json` present | `200 ok` |
| `GET /build-info.json` | `200 application/json`, `Cache-Control: no-store` |
| `GET /_expo/static/js/web/index-*.js` | `200` |
| `GET /game/abc` (SPA deep link) | `200` (try_files fallback intact) |

**Trap that cost a cycle:** the first version gated on the literal
`/usr/share/nginx/html/build-info.json`. The harness substituted only `root`, so the check looked at a
nonexistent path and returned 503 in *both* states. `$document_root` removes the duplication and makes
the block root-agnostic.

### envsubst matrix (why `$uri` / `$document_root` survive in the image)

`20-envsubst-on-templates.sh` computes `defined_envs=$(printf '${%s} ' $(env | cut -d= -f1))` and runs
`envsubst "$defined_envs"`.

| invocation | `${PORT}` | `$uri` | `$document_root` |
|---|---|---|---|
| `envsubst "$DEF"` where DEF comes from `env` (mirrors the image) | → `8080` | preserved | preserved |
| `envsubst` with no variable list (naive) | → `8080` | **blanked** | **blanked** |

Reproduce:

```bash
DEF=$(export PORT=8080; printf '${%s} ' $(env | cut -d= -f1)); export PORT=8080
envsubst "$DEF" < deploy/web-preview/nginx.conf | grep -nE 'listen|document_root|try_files'
```

Gotcha while measuring: `DEF=$(PORT=8080; printf ...)` does **not** export PORT to `env`, so `${PORT}`
stays unsubstituted and the experiment silently proves nothing. Use `export`.

---

## 3. Preview-origin CORS: observed, with a control

```bash
ORIGIN=https://worldai-frontend-pr-247-i6xf2p72ka-uc.a.run.app
BE=https://mvp-site-app-dev-i6xf2p72ka-uc.a.run.app
curl -sS -X OPTIONS -o /dev/null -D - -H "Origin: $ORIGIN" \
  -H 'Access-Control-Request-Method: GET' -H 'Access-Control-Request-Headers: authorization,content-type' \
  "$BE/api/campaigns" | grep -i access-control        # -> (nothing)  HTTP/2 200
curl -sS -X OPTIONS -o /dev/null -D - -H 'Origin: https://worldarchitect.ai' \
  -H 'Access-Control-Request-Method: GET' "$BE/api/campaigns" | grep -i access-control
# -> access-control-allow-origin: https://worldarchitect.ai
#    access-control-allow-methods: DELETE, GET, OPTIONS, PATCH, POST
```

200 without `Access-Control-Allow-Origin` is still a browser-side block. Source of the allowlist
(worldarchitect.ai `origin/main`): `mvp_site/main.py:387-396` — `CORS_RESOURCES = {r"/api/*": {"origins":
[f"http://localhost:{_FRONTEND_PORT}", "https://worldarchitect.ai"], ...}}`. There is no `*.run.app`
entry and no wildcard, so every per-PR preview host is blocked. Fixing it is a backend PR owned
elsewhere; a frontend preview workflow cannot close it. Google OAuth authorized JS origins have the
same shape of problem and do not accept wildcards.

Useful secondary proof that the *export* is fine even when auth is blocked:

```bash
curl -sS -o /tmp/idx.html -w 'code=%{http_code} bytes=%{size_download}\n' "$PREVIEW/"
grep -oE 'src="[^"]+"' /tmp/idx.html      # -> /_expo/static/js/web/index-<hash>.js
```

---

## 4. Reviewer custody: retained patch instead of a push

Because the workflow triggers on `pull_request: [opened, ready_for_review, reopened, synchronize]`, a
push to the branch deploys to Cloud Run. Reviewer without deploy authority therefore:

```bash
git worktree add --detach ~/.worktrees/<repo>/<name> <head>   # /tmp paths are refused by the shim
git checkout -B review/<topic>                                # local only, no upstream
git -c user.name=… commit -F - <<'MSG'
<runtime>/<model>: <subject>
MSG
git diff <head>..HEAD > ~/hermes-artifacts/<topic>/<name>.patch
git format-patch -1 --stdout > ~/hermes-artifacts/<topic>/<name>.mbox
shasum -a 256 ~/hermes-artifacts/<topic>/*
# prove it still applies without touching the branch:
git archive <head> | tar -x -C "$(mktemp -d)" && git apply --check <patch>
```

State the no-deploy publication options explicitly: a **draft** PR is skipped by the
`github.event.pull_request.draft == false` guard; an unset backend variable does **not** disable the
job; otherwise publication needs an intended, observable deploy by the owner.

### Offline contract-test skeleton for cleanup/janitor scripts

`gcloud` and `gh` are stubs on `PATH`; assertions are on decisions, not on GCP behaviour.

```bash
sandbox() {
  TMP=$(mktemp -d); mkdir -p "$TMP/bin"; : > "$TMP/calls.log"
  cat > "$TMP/bin/gcloud" <<'STUB'
#!/usr/bin/env bash
echo "gcloud $*" >> "${STUB_LOG:?}"
case "$1 $2 $3" in
  "run services list")   printf '%s\n' "${GC_SERVICES_JSON:-[]}"; exit 0 ;;
  "run services delete") [ -n "${GC_DELETE_ERR:-}" ] && printf '%s\n' "$GC_DELETE_ERR" >&2; exit "${GC_DELETE_EXIT:-0}" ;;
  "run revisions list")  printf '%s\n' "${GC_REVISIONS_JSON:-[]}"; exit 0 ;;
  "artifacts docker images")
    case "${4:-}" in list) printf '%s\n' "${GC_IMAGES_JSON:-[]}"; exit 0 ;;
      delete) [ -n "${GC_IMAGE_DELETE_ERR:-}" ] && printf '%s\n' "$GC_IMAGE_DELETE_ERR" >&2; exit "${GC_IMAGE_DELETE_EXIT:-0}" ;; esac ;;
esac
exit 0
STUB
  cat > "$TMP/bin/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "${STUB_LOG:?}"
[ "$1 $2" = "pr view" ] || { echo "unexpected gh call" >&2; exit 1; }
s=$(awk -v n="$3" '$1==n{print $2}' "${GH_STATE_FILE:-/dev/null}")
[ -n "$s" ] && [ "$s" != "__FAIL__" ] && { printf '%s\n' "$s"; exit 0; }
exit 1
STUB
  chmod +x "$TMP/bin/gcloud" "$TMP/bin/gh"
}
invoke() { env PATH="$TMP/bin:$PATH" STUB_LOG="$TMP/calls.log" "${E[@]}" "$BASH_BIN" "$@"; }
```

Cases that caught real behaviour (8/8 green): non-numeric PR rejected without calling gcloud; `DRY_RUN`
makes no destructive call; not-found in stderr is success; `PERMISSION_DENIED` exits non-zero; only
CLOSED/MERGED services deleted while OPEN and unresolvable stay; non-numeric `TARGET_PR_NUMBER`
rejected; empty service list exits 0; the digest a live revision runs is kept while stale/orphan
digests are pruned.

Two portability notes: `prune-stale-*.sh` uses `mapfile`, which is bash ≥ 4 — macOS `/bin/bash` 3.2
fails, so the test locates `/opt/homebrew/bin/bash`; and give the test a caller (build job and both
janitors) or it is dead code with no signal.
