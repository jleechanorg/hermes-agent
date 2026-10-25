#!/usr/bin/env python3
"""Real-provider ablation runner for a captured LLM payload.

Instrument: the captured generateContent body POSTed VERBATIM to the same model,
tools, safety settings and generationConfig. Nothing re-assembled, so there is no
production transformation to hold constant across arms -- say that in the report.

Usage:
    python3 replay_ablation.py <config.py> <ARM> <N> [tag]

config.py must define:
    BODY_PATH   path to the captured request JSON (the wire body, not a wrapper)
    MODEL       model slug, read from the capture if possible
    URL         full generateContent URL
    API_KEY()   -> str, fetched from your secret store at call time
    ARMS        {label: (name, fn(req) -> (new_req, note))}, fn MUST assert its edit
    SCORE(raw)  -> dict with at least {"rolled": bool}

Every run row records arm, run, ok, duration, model, provider, body sha256, the full
raw response, and the scored fields -- model/provider per row are routinely wanted
later. Keep superseded/buggy runs on disk and mark them do-not-cite rather than
overwriting them.
"""
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.request


def load_config(path):
    spec = importlib.util.spec_from_file_location("ablation_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    cfg = load_config(sys.argv[1])
    arm_label, n = sys.argv[2], int(sys.argv[3])
    tag = sys.argv[4] if len(sys.argv) > 4 else ""
    outdir = os.environ.get("ABLATION_OUTDIR", "./ablation_runs")
    os.makedirs(outdir, exist_ok=True)

    name, transform = cfg.ARMS[arm_label]
    with open(cfg.BODY_PATH) as f:
        base = json.load(f)
    req, note = transform(base)          # asserts its own effect before any API call
    body = json.dumps(req).encode()
    key = cfg.API_KEY()

    print(f"[arm {arm_label} {name}] {note}; bytes={len(body)}; n={n}", flush=True)
    for i in range(1, n + 1):
        t0 = time.time()
        row = {
            "arm": arm_label, "arm_name": name, "transform": note, "run": i,
            "model": cfg.MODEL, "provider": getattr(cfg, "PROVIDER", "real-api-rest"),
            "body_sha256": hashlib.sha256(body).hexdigest(), "tag": tag,
        }
        try:
            r = urllib.request.Request(
                cfg.URL, data=body,
                headers={"Content-Type": "application/json",
                         getattr(cfg, "KEY_HEADER", "x-goog-api-key"): key})
            with urllib.request.urlopen(r, timeout=getattr(cfg, "TIMEOUT", 300)) as resp:
                obj = json.loads(resp.read())
            row.update(ok=True, duration_s=round(time.time() - t0, 1), raw=obj)
            row.update(cfg.SCORE(obj))
        except Exception as e:  # noqa: BLE001 - per-run failure must not kill the arm
            detail = e.read().decode()[:800] if hasattr(e, "read") else ""
            row.update(ok=False, duration_s=round(time.time() - t0, 1),
                       error=f"{type(e).__name__}: {e} {detail}")
        print(f"  run {i}: ok={row['ok']} scored="
              f"{ {k: v for k, v in row.items() if k not in ('raw', 'usage')} }"
              .replace("'", "")[:200], flush=True)
        with open(os.path.join(outdir, f"{arm_label}_{name}{tag}.jsonl"), "a") as f:
            f.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
