# AGY-exclusive routing evidence at a pinned SHA (verified 2026-10-24)

Driving an existing routing harness (`testing_mcp/test_combat_intent_classifier_real_e2e.py`) at a
pinned candidate head and a pinned `origin/main` baseline, real server + real Firestore + real auth,
to answer "does the routing contract hold, and is it non-regressed?".

## Where the run can happen

| Host | AGY runtime home | Real-AGY run possible |
|---|---|---|
| macOS workstation | absent (`~/.cache/worldai/agy-clean-home-v1` missing) → `is_agy_provider_mode()` False → native Gemini SDK | no (SDK is allow-list-only for `testing_mcp/`) |
| Linux host (`jeff-ubuntu`) | present, `worldai-agy.env` + `.gemini/antigravity-cli/*`, `agy 1.4.7` | yes |

Probe (no provider call):

```bash
export AGY_RUNTIME_HOME=/home/jleechan/.cache/worldai/agy-clean-home-v1
export WORLDAI_DEV_MODE=true
/home/jleechan/projects/worldarchitect.ai/.venv/bin/python -c \
 'from mvp_site.llm_providers.provider_gateway import is_agy_provider_mode, get_gemini_facade_provider_type as f; print(is_agy_provider_mode(), f())'
# -> True agy
```

`is_agy_supported_model()` is the catalog gate: `gemini-3.8-flash` True;
`gemini-3-flash-preview`, `gemini-3.5-flash-lite` False. A non-catalog model is *supposed* to go to
the native SDK — which is exactly what the harness's AGY-exclusivity guard then flags.

## Worktree + interpreter

```bash
git -C <repo> fetch origin <branch> -q
git -C <repo> worktree add --detach <wt> <pinned-sha>      # clean, 0 porcelain lines
cd <wt>
# no venv in a fresh worktree, and vpython wants <wt>/venv/bin/activate:
PY=/home/jleechan/projects/worldarchitect.ai/.venv/bin/python   # sibling checkout's venv
```

Keep `cwd` at the pinned worktree so `mvp_site` imports resolve to the tested tree.

## Launch script (detached, pollable)

```bash
#!/usr/bin/env bash
set -uo pipefail
W=<pinned worktree>; cd "$W"
export AGY_RUNTIME_HOME=/home/jleechan/.cache/worldai/agy-clean-home-v1
source "$AGY_RUNTIME_HOME/worldai-agy.env"
export WORLDAI_DEV_MODE=true TESTING_AUTH_BYPASS=false ALLOW_TEST_AUTH_BYPASS=false
unset MOCK_SERVICES_MODE TEST_MODE USE_MOCK_FIREBASE USE_MOCK_GEMINI SMOKE_TOKEN 2>/dev/null || true
export PYTHONPATH="$W:$W/mvp_site"
LOG=${LOG:-/tmp/<run>.log}
echo "== RUN START $(date -u +%FT%TZ) sha=$(git rev-parse HEAD) host=$(hostname)"
"$PY" testing_mcp/<harness>.py --work-name <name> --user-id-prefix <prefix> 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
echo "== RUN END $(date -u +%FT%TZ) exit=$rc"; exit "$rc"
```

```bash
scp run.sh host:/tmp/run_pinned_real.sh
ssh host 'setsid bash /tmp/run_pinned_real.sh > /tmp/run.out 2>&1 < /dev/null & echo launched=$!'
```

Poll with tight output only:

```bash
ssh host 'pgrep -f <harness> >/dev/null && echo RUNNING || echo NOT_RUNNING;
  echo turns=$(grep -c "process_action total_ms" /tmp/run.out);
  tail -3 /tmp/run.out | cut -c1-150'
```

Successful turns land as `llm_response_cache process_action total_ms=… user_input=… campaign_id=…`,
roughly 20 s–205 s each; a 9-min gap means an `agy.real` child is on its `--print-timeout`.

**Never** run `pgrep -fa agy` unfiltered — each `agy.real` argv embeds a multi-KB JSON schema and one
such listing produced 85k chars of tool output.

## Reading the result without the bundle

`doctor_report.json`:

```json
{"generated_at_utc": "...", "server_base_url": "http://127.0.0.1:8014",
 "failure_messages": ["...", "..."],
 "http_probes": {"/health": {"body_excerpt": "{\"git_commit\":\"<pinned sha>\", ...}"}}}
```

That `/health` body is the served-source pin for the run. Failure messages observed:

- `unexpected turn-handoff classifier metadata or transport`
- `unexpected non-active persisted context, transport, or semantic classifier metadata`
- `unexpected active combat setup, persisted state, or state-based classifier metadata`
- `Local AGY-default evidence leak: Gemini SDK or BYOK override detected when agy provider was expected — gemini_http_request_responses.jsonl: line 1.. contains Gemini SDK host`
- `Gemini streaming capture mismatch: successful process_action calls=4, gemini_http_requests=0, llm_requests=24, native_agy_pairs=12`
- `run_scenarios crashed: create_campaign returned unexpected payload: {'error': 'HTTP 401 UNAUTHORIZED: ...'}` (mid-run token/auth boundary; not a product verdict)

`iteration_*/artifacts/collection_log.txt` is the abort receipt — `core_files:` all `missing` means
`create_evidence_bundle` never wrote a results checkpoint, so no assertion-bound artifact exists.

## Routing evidence from a bundle-less run

- SSE: `http_request_responses_*.jsonl` rows with `type: sse_event` and `event.type == "done"` carry
  `agent_name`, `classifier_source`, `intent`, `execution_path` → `scripts/extract_routing_metadata.py`.
- Server log: `campaign_id=<id> | 🧠 ROUTING_DECISION: provider=legacy_fastembed mode=<m> confidence=<c> source=legacy`.
- Readback: `Captured campaign snapshot for <id>` (one line per campaign) + the campaign export step.

## Shared-log trap

`/tmp/worldarchitect.ai/unknown/app.log` holds days of every lane's traffic (unified logging writes
there when `work-name` is not applied at import time). Grepping it for `dispatching to agy` or
`retryable failure` yields *host* counts. Always scope by `campaign_id` or by the run's UTC window and
label the scope in the report.

## Non-PR findings worth separating

At the candidate head the two failing self-hosted shards were
`UserSettingsReadError: User settings are temporarily unavailable` in
`test_gemini_request_size_logging.py` (3) and the `TestStreamCacheFallback` class of
`test_llm_service_error_handling.py` (4) — the credential-less-CI root cause already patched test-side
for other suites, i.e. a coverage gap, not a routing regression. Classify these before implying the
routing contract caused them.

## Multi-host custody / bead check

- A bead id can exist in only one host's store. `rev-49erx` was absent from the Mac
  `.beads/issues.jsonl` and present (OPEN, live-evidence hold) on the Linux store — always check both
  before writing "bead not found".
- An `ao/<repo>-<n>` worktree listed as `prunable` with its directory gone, no `~/.ao` state, no
  process, and no matching `*.chat` marker means the lane exited; reconcile by describing that state
  and leaving the marker/registration untouched, not by clearing it.
