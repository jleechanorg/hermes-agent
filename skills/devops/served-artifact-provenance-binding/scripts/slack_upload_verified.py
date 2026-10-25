#!/usr/bin/env python3
"""Upload files to a Slack channel/thread and REFUSE to claim success unless shared.

Why this exists: `files.completeUploadExternal` returns {"ok": true} even when the
uploaded file ends up unshared (`shares: []`, `channels: []`) and therefore invisible
to the user. Two known triggers, both silent:
  * passing `alt_txt` to files.getUploadURLExternal
  * passing `thread_ts` to files.completeUploadExternal
So: no alt_txt, prefer `channel_id` alone, and gate on files.info.

Usage:
    SLACK_BOT_TOKEN=xoxb-... python3 slack_upload_verified.py \
        --channel C0123456789 --thread-ts 1792896173.688169 \
        path/to/a.webm path/to/receipt.json

Exit code 0 only if EVERY file reports a real share. Prints one JSON line per file
with name, bytes, sha256, file_id, permalink, shared channels. Never prints the token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://slack.com/api/"


def _post(method: str, body: bytes) -> dict:
    tok = os.environ["SLACK_BOT_TOKEN"]
    req = urllib.request.Request(
        API + method,
        data=body,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    return json.load(urllib.request.urlopen(req, timeout=120))


def _get(method: str, params: dict) -> dict:
    tok = os.environ["SLACK_BOT_TOKEN"]
    url = f"{API}{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def upload(path: str, channel: str) -> dict:
    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    base = os.path.basename(path)

    # NOTE: no alt_txt — it silently suppresses the later share.
    q = urllib.parse.urlencode({"filename": base, "length": len(raw)}).encode()
    tok = os.environ["SLACK_BOT_TOKEN"]
    got = json.load(
        urllib.request.urlopen(
            urllib.request.Request(
                API + "files.getUploadURLExternal",
                data=q,
                headers={
                    "Authorization": f"Bearer {tok}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            ),
            timeout=120,
        )
    )
    if not got.get("ok"):
        return {"name": base, "error": f"getUploadURLExternal:{got.get('error')}"}

    urllib.request.urlopen(
        urllib.request.Request(
            got["upload_url"], data=raw, headers={"Content-Type": "application/octet-stream"}
        ),
        timeout=300,
    ).read()

    # NOTE: channel_id only. thread_ts shares silently fail; post a thread summary instead.
    done = _post(
        "files.completeUploadExternal",
        json.dumps({"files": [{"id": got["file_id"], "title": base}], "channel_id": channel}).encode(),
    )
    if not done.get("ok"):
        return {"name": base, "error": f"completeUploadExternal:{done.get('error')}"}

    time.sleep(3)
    info = _get("files.info", {"file": got["file_id"]}).get("file", {})
    shares = list((info.get("shares") or {}).keys())
    channels = info.get("channels") or []
    return {
        "name": base,
        "bytes": len(raw),
        "sha256": sha,
        "file_id": got["file_id"],
        "shared": shares,
        "channels": channels,
        "permalink": info.get("permalink"),
        "verified": bool(shares) and channel in channels,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--thread-ts", help="only used to print a reminder; not passed to stage 3")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()

    if "SLACK_BOT_TOKEN" not in os.environ:
        print("SLACK_BOT_TOKEN not set", file=sys.stderr)
        return 2

    ok = True
    for p in a.paths:
        res = upload(p, a.channel)
        print(json.dumps(res), flush=True)
        ok = ok and bool(res.get("verified"))

    if not ok:
        print(
            "REFUSING to claim attachment: at least one file is unshared (see 'shared'/'channels').",
            file=sys.stderr,
        )
        return 1
    if a.thread_ts:
        print(
            f"files are shared at channel level; post a text summary into thread {a.thread_ts} "
            "listing file_id + permalink so readers can find them.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
