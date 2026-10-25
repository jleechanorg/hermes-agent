#!/usr/bin/env bash
# Retry the /advice primary pair for llm-wiki PRs 28/27/26 after reviewer quota resets.
# Logs to a durable path (never /tmp for evidence). Posts the verdict as a PR comment.
set -uo pipefail
export PATH="/Users/jleechan/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
REPO=/Users/jleechan/llm_wiki
LOG="$HOME/Documents/llm-wiki-advice-retry.log"
RUNNER="$HOME/.claude/skills/advice/scripts/run_primary_pair.py"
mkdir -p "$(dirname "$LOG")"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

cd "$REPO" || { log "FATAL repo missing"; exit 1; }
if [ -n "$(git status --porcelain)" ]; then log "SKIP dirty checkout"; exit 0; fi

for N in 33 28 27 26; do
  HEAD=$(gh pr view "$N" --repo jleechanorg/llm-wiki --json headRefOid -q .headRefOid 2>/dev/null)
  [ -z "$HEAD" ] && { log "PR $N: no head"; continue; }
  # skip if a verdict comment already exists at this head
  if gh pr view "$N" --repo jleechanorg/llm-wiki --json comments -q '.comments[].body' 2>/dev/null | grep -q "VERDICT: APPROVED at $HEAD\|APPROVED at ${HEAD:0:10}"; then
    log "PR $N: already approved at $HEAD"; continue
  fi
  OUT="$HOME/.cache/llm-wiki-advice/$N-$(date +%s)"
  mkdir -p "$(dirname "$OUT")"
  cat > "/tmp/lw-packet-$N.txt" <<PKT
Senior engineer second opinion.

DECISION:
llm_wiki PR #$N. Read the diff yourself and judge correctness, duplication, and wiki-pattern compliance.

WHAT TO REVIEW:
https://github.com/jleechanorg/llm-wiki/pull/$N head $HEAD base main.
PKT
  if ! git fetch origin --quiet 2>/dev/null; then log "PR $N: fetch failed"; continue; fi
  timeout 1500 python3 "$RUNNER" --repo "$REPO" --ref "$HEAD" \
    --packet-file "/tmp/lw-packet-$N.txt" --output-dir "$OUT" \
    --reviewers codex,opus --timeout-seconds 1200 >> "$LOG" 2>&1
  RC=$?
  VERDICT=""
  for f in "$OUT"/codex.txt "$OUT"/opus.txt; do
    [ -f "$f" ] || continue
    v=$(grep -m1 '^VERDICT:' "$f" 2>/dev/null)
    [ -n "$v" ] && VERDICT="$VERDICT
$(basename "$f"): $v"
  done
  if [ -n "$VERDICT" ]; then
    log "PR $N: verdict(s) at $HEAD:$VERDICT"
    gh pr comment "$N" --repo jleechanorg/llm-wiki --body "**/advice** at \`$HEAD\`$VERDICT" >/dev/null 2>&1 || true
    /usr/bin/osascript -e "display notification \"llm-wiki PR #$N advice verdict received\" with title \"Advice retry\"" >/dev/null 2>&1 || true
  else
    log "PR $N: no verdict (rc=$RC) — still quota-limited or runner error"
  fi
done
