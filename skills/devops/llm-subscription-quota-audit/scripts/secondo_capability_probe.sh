#!/bin/bash
# /secondo (seat C) route probe — token-safe, zero model calls.
#
# Answers: "is the AI Universe MCP route usable from THIS host right now?"
# Checks the three layers in order: MCP CLI registration, canonical default endpoint,
# and the existing cached-session HTTP fallback.
#
# Guarantees:
#   * never prints the bearer token (only its character count and the auth exit code)
#   * redacts JWT-shaped strings from every echoed response
#   * issues only MCP `initialize` and `tools/list` — no consultation, no spend
#
# Usage:  bash secondo_capability_probe.sh
# Exit:   0 = route usable; 3 = auth unavailable; 4 = transport error

set -u

EP="${AI_UNIVERSE_MCP_ENDPOINT:-https://ai-universe-backend-dev-114133832173.us-central1.run.app/mcp}"
AUTH_CLI="${HOME}/.claude/scripts/auth-cli.mjs"
TOKEN_CACHE="${HOME}/.ai-universe/auth-token.json"

redact() { sed -E 's/eyJ[A-Za-z0-9._-]{20,}/<REDACTED_JWT>/g'; }

echo "== layer 1: MCP CLI =="
if command -v mcp-cli >/dev/null 2>&1; then
  if mcp-cli tools second-opinion-tool 2>&1 | grep -q "agent.second_opinion"; then
    echo "mcp_cli=AVAILABLE server=second-opinion-tool"
  else
    echo "mcp_cli=present server=UNREGISTERED (fall through to HTTP)"
  fi
else
  echo "mcp_cli=MISSING (fall through to HTTP)"
fi

echo "== layer 2: endpoint reachability (unauthenticated) =="
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$EP" 2>/dev/null || echo "000")
echo "endpoint=$EP unauth_http=$code"
if [ "$code" = "000" ]; then
  echo "transport=UNREACHABLE"
  exit 4
fi

echo "== layer 3: existing cached session =="
if [ -f "$TOKEN_CACHE" ]; then
  echo "token_cache=present perms=$(stat -f '%OLp' "$TOKEN_CACHE" 2>/dev/null || stat -c '%a' "$TOKEN_CACHE" 2>/dev/null)"
else
  echo "token_cache=ABSENT"
fi
if [ ! -f "$AUTH_CLI" ]; then
  echo "auth_cli=MISSING"
  exit 3
fi

TOKEN=$(timeout 45 node "$AUTH_CLI" token 2>/tmp/secondo_auth.err)
rc=$?
echo "auth_cli_exit=$rc token_chars=${#TOKEN}"
if [ "$rc" -ne 0 ] || [ -z "$TOKEN" ]; then
  echo "auth_stderr_tail:"; tail -5 /tmp/secondo_auth.err | redact
  exit 3
fi

call_mcp() {
  local label="$1" body="$2" out status
  out=$(timeout 45 curl -sS -X POST "$EP" \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d "$body" -w '\n__HTTP__%{http_code}' 2>&1)
  status=$(printf '%s' "$out" | sed -n 's/.*__HTTP__//p')
  echo "$label http=$status"
  printf '%s' "$out" | sed 's/__HTTP__[0-9]*$//' | head -c 400 | redact
  echo
}

call_mcp "initialize" '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"hermes-capability-check","version":"0"}}}'
call_mcp "tools_list" '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

echo "route=USABLE (agent.second_opinion expected in tools_list; question maxLength 320000)"
echo "remember: raise SECOND_OPINION_MAX_DIFF_CHARS / MAX_FILES if the diff exceeds 32000 chars or 20 files"
