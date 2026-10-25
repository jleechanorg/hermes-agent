#!/usr/bin/env python3
"""Replay a Codex session's real commands across every registered hook.

Why: the Codex TUI prints only "hook exited with code N" with no hook name, and
failed hooks are absent from logs_2.sqlite and the rollout jsonl. The only
defensible way to exonerate (or convict) a hook set is to replay the commands the
failing session actually ran and tabulate exit codes.

Usage:
  python3 replay_hooks.py --session ~/.codex/sessions/2026/10/16/rollout-....jsonl \
      --cwd-filter worktree_dropbox --limit 150 \
      --hook 'diskm guard-worktree-add' \
      --hook 'python3 ~/.codex/hooks/path-deletion-guard.py' \
      --hook 'bash ~/.claude/hooks/block-home-scan.sh' \
      --hook 'bash ~/.codex/hooks/rtk-hook-guard.sh'

  # or discover hooks.json + plugin hooks automatically:
  python3 replay_hooks.py --session <rollout> --auto

Exit codes: 0 = pass, 2 = intentional deny/block, 1/127 = the failure you want.
Prints a matrix plus a sample of every nonzero result with stdout/stderr.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import subprocess
import sys

PAYLOAD_CWD = "{cwd}"


def load_commands(session: str, cwd_filter: str | None, limit: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(os.path.expanduser(session), errors="replace") as fh:
        for line in fh:
            if '"CommandExecution"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            pl = d.get("payload") or {}
            if pl.get("type") != "item_completed":
                continue
            item = pl.get("item") or {}
            if item.get("type") != "CommandExecution":
                continue
            cmd = item.get("command")
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            cwd = str(item.get("cwd") or "")
            if cwd_filter and cwd_filter not in cwd:
                continue
            rows.append((cwd.replace("file://", ""), str(cmd)))
    return rows[-limit:]


def auto_hooks() -> list[str]:
    hooks: list[str] = []
    p = os.path.expanduser("~/.codex/hooks.json")
    if os.path.exists(p):
        try:
            data = json.load(open(p))
            for groups in (data.get("hooks") or {}).values():
                for g in groups:
                    for h in g.get("hooks", []):
                        hooks.append(h.get("command", "").strip())
        except Exception as exc:  # pragma: no cover
            print(f"warn: cannot parse {p}: {exc}", file=sys.stderr)
    for manifest in glob.glob(
        os.path.expanduser("~/.claude/plugins/cache/*/*/*/hooks/codex.json")
    ):
        try:
            data = json.load(open(manifest))
        except Exception:
            continue
        root = manifest.split("/hooks/")[0]
        for groups in (data.get("hooks") or {}).values():
            for g in groups:
                for h in g.get("hooks", []):
                    cmd = h.get("command", "")
                    if "${PLUGIN_ROOT}" in cmd:
                        # keep the newest cached version only
                        hooks.append(cmd.replace("${PLUGIN_ROOT}", root))
    return [h for h in hooks if h]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--cwd-filter")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--hook", action="append", default=[])
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()

    hooks = list(args.hook) + (auto_hooks() if args.auto or not args.hook else [])
    if not hooks:
        print("no hooks to test", file=sys.stderr)
        return 2
    cmds = load_commands(args.session, args.cwd_filter, args.limit)
    if not cmds:
        print("no commands matched", file=sys.stderr)
        return 2
    print(f"{len(cmds)} commands × {len(hooks)} hooks")

    matrix: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    samples: dict[str, list] = collections.defaultdict(list)
    for cwd, cmd in cmds:
        payload = json.dumps(
            {
                "session_id": "replay",
                "transcript_path": "/tmp/replay.jsonl",
                "cwd": cwd or os.getcwd(),
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            }
        )
        for h in hooks:
            try:
                r = subprocess.run(
                    ["/bin/bash", "-lc", h],
                    input=payload,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                )
                rc = r.returncode
                out, err = r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                rc, out, err = "TIMEOUT", "", ""
            matrix[h][rc] += 1
            if rc != 0 and len(samples[h]) < 3:
                samples[h].append((rc, cmd[:200], out[:200], err[-300:]))

    bad = 0
    for h in hooks:
        dist = dict(matrix[h])
        flag = "" if set(dist) <= {0} else "  <-- nonzero"
        if flag:
            bad += 1
        print(f"\n{h[:110]}\n  {dist}{flag}")
        for s in samples[h]:
            print(f"   sample rc={s[0]} cmd={s[1]!r}\n     out={s[2]!r}\n     err={s[3]!r}")
    print(f"\nsummary: {len(hooks)} hooks, {len(cmds)} commands, {bad} hook(s) returned nonzero")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
