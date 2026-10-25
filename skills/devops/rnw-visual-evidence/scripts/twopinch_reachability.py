#!/usr/bin/env python3
"""Does an RNW pinch/pan ordering reach the state a fix claims to repair?

Usage:
    python3 twopinch_reachability.py <port> <label> [outdir]

Runs TWO gesture variants against a page that mounts the real zoom viewer
(`[data-testid="zoom-viewer-image"]`) and prints the rendered `matrix()`
scale per step, writing `<outdir>/<label>/twopinch.json`.

  pan_held  : finger A down for the whole test (pan stays down), pinch #1,
              lift finger B only, then try to restart pinch #2 while A is
              still down -> tests "second pinch from an out-of-range base".
  released  : every gesture fully released between pinch #1 and pinch #2
              -> tests whether the final hard clamp removes the precondition.

Measured on RNGH 2.28 web (2026-10-24): pan_held holds a sub-1x committed
base (0.79-0.95) through a drag, but pinch #2 NEVER restarts while a pointer
stays down (scale frozen); `released` clamps straight back to 1.0. Identical
trajectories on both heads => no web RED/GREEN from this input path. Report
the numbers as a platform limit; do not force component state to fake a step.

Notes:
- `record_video_dir` needs Playwright's own ffmpeg; if the cache lacks it the
  context raises on `new_page()`. Video is intentionally NOT enabled here —
  use `page.screenshot()` per step, or a Playwright env that has ffmpeg.
- Launch the browser explicitly (headless-shell path) and fall back to
  `channel="chrome"` so a cache hiccup does not read as "no browser".
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

EXE_GLOB = "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"

READ_JS = """() => {
  const img = document.querySelector('[data-testid="zoom-viewer-image"]');
  if (!img) return {present:false};
  const t = getComputedStyle(img.parentElement).transform;
  const m = t.match(/matrix\\(([^)]+)\\)/);
  let s = 1, x = 0, y = 0;
  if (m) { const p = m[1].split(',').map(Number); s = p[0]; x = p[4]; y = p[5]; }
  return {present:true, scale:+s.toFixed(4), tx:+x.toFixed(2), ty:+y.toFixed(2),
          closes:(globalThis.__harness||{}).closes, head:(globalThis.__harness||{}).head};
}"""


def launch(p):
    import glob
    cands = glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/" + EXE_GLOB))
    attempts = [{"executable_path": c} for c in cands] + [{"channel": "chrome"}, {}]
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, **kw)
        except Exception as exc:  # noqa: BLE001 - report and try next path
            print("launch failed", kw, str(exc)[:120])
    raise RuntimeError("no launchable chromium")


def drive(pg, cdp, variant, t0):
    steps = []

    def snap(tag, wait=0):
        if wait:
            pg.wait_for_timeout(wait)
        r = pg.evaluate(READ_JS)
        r["tag"] = tag
        r["t_ms"] = int((time.time() - t0) * 1000)
        steps.append(r)
        return r

    def touch(kind, pts):
        cdp.send("Input.dispatchTouchEvent", {
            "type": kind,
            "touchPoints": [{"x": q[0], "y": q[1], "id": q[2]} for q in pts]})

    cx, cy = 195, 420
    snap("00-initial")

    if variant == "pan_held":
        touch("touchStart", [(cx, cy, 1)])
        for dy in (6, 14, 22):
            touch("touchMove", [(cx, cy + dy, 1)])
            pg.wait_for_timeout(40)
        snap("01-pan-active")
        touch("touchStart", [(cx - 100, cy, 1), (cx + 100, cy, 2)])
        for d in (170, 140):                      # span SHRINKS -> sub-1x
            touch("touchMove", [(cx - d / 2, cy, 1), (cx + d / 2, cy, 2)])
            pg.wait_for_timeout(60)
        snap("02-pinch1-live-sub1x")
        touch("touchEnd", [(cx - 70, cy, 1)])     # lift B only; A stays down
        snap("03-after-pinch1-liftB", 250)
        touch("touchStart", [(cx - 100, cy, 1), (cx + 100, cy, 2)])
        snap("04-pinch2-start", 120)              # frozen here => no restart
        for d in (160, 200, 240):
            touch("touchMove", [(cx - d / 2, cy, 1), (cx + d / 2, cy, 2)])
            pg.wait_for_timeout(60)
            snap("05-pinch2-move")
        touch("touchEnd", [(cx - 115, cy, 1)])
        snap("06-after-liftB-again", 200)
        touch("touchEnd", [])
        snap("07-all-released", 500)
    else:
        touch("touchStart", [(cx - 100, cy, 1), (cx + 100, cy, 2)])
        for d in (170, 140):
            touch("touchMove", [(cx - d / 2, cy, 1), (cx + d / 2, cy, 2)])
            pg.wait_for_timeout(60)
        snap("02-pinch1-live-sub1x")
        touch("touchEnd", [])
        snap("03-all-released-after-pinch1", 400)  # hard clamp -> 1.0
        touch("touchStart", [(cx - 100, cy, 1), (cx + 100, cy, 2)])
        snap("04-pinch2-start", 120)
        for d in (160, 200, 240):
            touch("touchMove", [(cx - d / 2, cy, 1), (cx + d / 2, cy, 2)])
            pg.wait_for_timeout(60)
            snap("05-pinch2-move")
        touch("touchEnd", [])
        snap("06-all-released", 500)
    return steps


def main():
    port = sys.argv[1]
    label = sys.argv[2]
    outdir = sys.argv[3] if len(sys.argv) > 3 else "/tmp/rnw-twopinch"
    out = os.path.join(outdir, label)
    os.makedirs(out, exist_ok=True)

    results = {}
    with sync_playwright() as p:
        browser = launch(p)
        for variant in ("pan_held", "released"):
            ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                      device_scale_factor=2, is_mobile=True, has_touch=True)
            pg = ctx.new_page()
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded", timeout=180000)
            pg.wait_for_selector('[data-testid="zoom-viewer-image"]', timeout=180000)
            pg.wait_for_timeout(1200)
            cdp = ctx.new_cdp_session(pg)
            t0 = time.time()
            results[variant] = drive(pg, cdp, variant, t0)
            print(label, variant,
                  json.dumps([(s.get("tag"), s.get("scale")) for s in results[variant]]))
            ctx.close()
        browser.close()

    path = os.path.join(out, "twopinch.json")
    json.dump({"label": label, "port": port, "variants": results}, open(path, "w"), indent=1)
    print("WROTE", path)


if __name__ == "__main__":
    main()
