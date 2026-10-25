#!/usr/bin/env python3
"""Extract per-turn routing metadata from a testing_mcp SSE capture.

Reads an ``http_request_responses_*.jsonl`` file produced by ``MCPTestBase`` and
prints one TSV row per streaming ``done`` event:

    ts<TAB>campaign_id<TAB>agent_name<TAB>classifier_source<TAB>intent<TAB>execution_path

Why this exists: when ``create_evidence_bundle`` aborts (strict trace validation,
AGY-exclusive guard), the run leaves no ``scenario_results_checkpoint.json``, yet
the routing evidence is still present in the captured SSE stream. This recovers it
without re-running paid provider calls.

Only routing metadata is emitted; narrative text, prompts and headers are never
printed. Rows with no routing fields are skipped, so count rows accordingly.

Usage:
    python3 extract_routing_metadata.py <iteration_dir>/http_request_responses_*.jsonl
"""
from __future__ import annotations

import json
import sys

FIELDS = ("agent_name", "classifier_source", "intent", "execution_path", "router")


def pick(payload, out=None, depth=0):
    """Depth-bounded walk; first occurrence of each field wins."""
    if out is None:
        out = {}
    if depth > 6 or not isinstance(payload, (dict, list)):
        return out
    if isinstance(payload, dict):
        for key in FIELDS:
            if key in payload and key not in out:
                value = payload[key]
                if isinstance(value, (str, int, float)):
                    out[key] = value
        for value in payload.values():
            pick(value, out, depth + 1)
    else:
        for value in payload[:80]:
            pick(value, out, depth + 1)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = sys.argv[1]
    rows = 0
    emitted = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            if record.get("type") != "sse_event":
                continue
            event = record.get("event") or {}
            if event.get("type") != "done":
                continue
            meta = pick(event.get("payload") or {})
            if not meta:
                continue
            emitted += 1
            print(
                "\t".join(
                    [
                        str(record.get("timestamp", ""))[:19],
                        str(record.get("campaign_id", ""))[:12],
                        str(meta.get("agent_name", "-")),
                        str(meta.get("classifier_source", "-")),
                        str(meta.get("intent", "-")),
                        str(meta.get("execution_path", "-")),
                    ]
                )
            )
    print(f"# records={rows} done_events_with_routing={emitted}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
