#!/usr/bin/env python3
"""Read-only scene-image provenance lookup (WA prod).

Phase 1 (this script): resolve campaign by TITLE for a uid, read the
`scene_illustrations/{user_scene_number}` doc, download the stored blob, hash it,
and print a ready-to-run bounded BigQuery query for the generation payload row.

Phase 2 (manual, do NOT automate a write): run the printed `bq query`, then diff
`request_json.payload.prompt` against `git show <extra.git_commit>:mvp_site/prompts/scene_image.md`.

Never generates an image, never replays a turn, never writes Firestore.

Usage (from the repo root, so `firebase_admin` resolves from the repo venv):
    cd ~/worldarchitect.ai
    GOOGLE_APPLICATION_CREDENTIALS=~/serviceAccountKey.json WORLDAI_DEV_MODE=true \
      .venv/bin/python <skill>/scripts/scene_image_provenance.py \
        --uid <uid> --campaign-title "Rome: Gaia Julia" --scene 612 \
        --caption-token "Imperial Highland Castra"

Notes baked in from the 2026-10-25 run:
  * campaign display name is the `title` field, NOT `name`
  * collection_group(name|title ==) needs an index -> don't; scope to a uid
  * a heavy account has >300 campaigns -> equality query, never limit(300) + scan
  * .venv has firebase_admin but no google.cloud.bigquery -> bq CLI for phase 2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

import firebase_admin
from firebase_admin import credentials, firestore

PROJECT = "worldarchitecture-ai"


def cli() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True, help="owner uid (users/{uid})")
    ap.add_argument("--campaign-title", required=True, help="exact campaigns.title value")
    ap.add_argument("--scene", required=True, help="user_scene_number (string of an int)")
    ap.add_argument("--caption-token", default="", help="distinctive caption/heading substring for the BQ LIKE")
    ap.add_argument("--key", default=os.path.expanduser("~/serviceAccountKey.json"))
    ap.add_argument("--days", type=int, default=10, help="BQ scan window; table is day-partitioned")
    ap.add_argument("--out", default="/tmp", help="dir for the downloaded image")
    return ap.parse_args()


def main() -> int:
    a = cli()
    os.environ.setdefault("WORLDAI_DEV_MODE", "true")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(a.key), {"projectId": PROJECT}
        )
    db = firestore.client()

    camps = list(
        db.collection("users").document(a.uid).collection("campaigns")
        .where(filter=firestore.FieldFilter("title", "==", a.campaign_title))
        .limit(5).stream()
    )
    if not camps:
        print(f"NO_CAMPAIGN_MATCH title={a.campaign_title!r} (field is `title`, not `name`)")
        return 2
    cid = camps[0].id
    print("campaign:", cid[:8] + "…", "| title:", a.campaign_title)

    base = db.collection("users").document(a.uid).collection("campaigns").document(cid)
    snap = base.collection("scene_illustrations").document(str(int(a.scene))).get()
    if not snap.exists:
        ids = [d.id for d in base.collection("scene_illustrations").limit(400).stream()]
        print(f"NO_DOC for user_scene_number={a.scene}; present keys tail:",
              sorted(ids, key=lambda x: int(x) if x.isdigit() else 0)[-12:])
        print("HINT: client 'Scene N' label may be offset from the storage key — check neighbours.")
        return 2

    d = snap.to_dict() or {}
    meta = {k: v for k, v in d.items() if k != "prompt_redacted"}
    print("doc meta:", json.dumps(meta, default=str)[:1200])
    print("prompt_redacted_len:", len(d.get("prompt_redacted") or ""), "(pointer only — first 500 chars)")

    url = d.get("image_url") or ""
    if url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "read-only-diagnosis"})
            with urllib.request.urlopen(req, timeout=90) as r:
                blob = r.read()
            path = os.path.join(a.out, f"scene{a.scene}.png")
            with open(path, "wb") as fh:
                fh.write(blob)
            digest = hashlib.sha256(blob).hexdigest()
            print(f"download: {path} bytes={len(blob)} sha256={digest}")
            print("hash_match_doc:", digest == (d.get("sha256") or ""))
        except Exception as exc:  # noqa: BLE001 - diagnosis script, report not raise
            print("download_failed:", type(exc).__name__, str(exc)[:140])

    token = a.caption_token
    print("\n--- phase 2: generation payload row (run this, then dry-run first if unsure) ---")
    cond = f"\n  AND request_json LIKE '%{token}%'" if token else ""
    print(f"""bq --project_id={PROJECT} query --dry_run --use_legacy_sql=false "

SELECT ingested_at, campaign_id, user_id, model, extra_json, request_json
FROM \\`{PROJECT}.llm_forensics.llm_payloads\\`
WHERE ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {a.days} DAY)
  AND JSON_EXTRACT_SCALAR(extra_json,'$.portrait_source') = 'scene_illustration'{cond}
LIMIT 5"
""")
    print("Then match extra_json.image_sha256 to the sha256 above, and compare")
    print("request_json.payload.prompt against git show <extra.git_commit>:mvp_site/prompts/scene_image.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
