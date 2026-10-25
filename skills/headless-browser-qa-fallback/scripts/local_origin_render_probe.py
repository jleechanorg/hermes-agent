#!/usr/bin/env python3
"""Render-probe a loopback origin and emit per-route JSON + PNG evidence.

Use when the evidence target lives on 127.0.0.1 (forwarded port to a Linux artifact
server, Expo static export, local preview) and the claim is "this build RENDERS as X".

Design notes
------------
* Renders with local headless Chromium, so a private/loopback origin is fine.
* Resolves a cached ms-playwright headless shell automatically when the installed
  Playwright package expects a different browser revision (a very common mismatch:
  package wants chromium_headless_shell-1208, cache holds -1228). Pass
  --executable-path to override.
* Prints JSON to stdout and writes one PNG per route; a route counts as rendered only
  when the mounted DOM has content. Exit code is non-zero when any route fails to
  render or the page raised a pageerror (a truthy receipt, not just a log).

Usage
-----
  python3 local_origin_render_probe.py --url http://127.0.0.1:19878 --routes / /old
  python3 local_origin_render_probe.py --url http://127.0.0.1:8123 \
      --routes / --root-selector '#root' --expect-text 'Continue with Google'
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def _cached_headless_shell() -> str | None:
    """Newest chromium_headless_shell-* binary in the ms-playwright cache."""
    roots = [
        os.path.expanduser("~/Library/Caches/ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    best: tuple[int, str] | None = None
    for root in roots:
        for path in glob.glob(os.path.join(root, "chromium_headless_shell-*", "**", "chrome-headless-shell*"), recursive=True):
            if not os.path.isfile(path) or os.path.isdir(path):
                continue
            m = re.search(r"chromium_headless_shell-(\d+)", path)
            rev = int(m.group(1)) if m else 0
            if best is None or rev > best[0]:
                best = (rev, path)
    return best[1] if best else None


PROBE_JS = """(sel) => {
  const root = document.querySelector(sel);
  const inter = [...document.querySelectorAll('button,[role=button],a,input,textarea,select')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map(e => (e.innerText || e.getAttribute('aria-label') || e.value || '').trim())
    .filter(Boolean).slice(0, 20);
  return {
    title: document.title,
    url: location.href,
    rootFound: !!root,
    rootChildren: root ? root.childElementCount : -1,
    rootInnerLen: root ? root.innerHTML.length : -1,
    textLen: (document.body.innerText || '').length,
    textHead: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 500),
    interactive: inter,
    scriptSrcs: [...document.scripts].map(s => s.src).filter(Boolean),
    imgCount: document.images.length,
    bodyBg: getComputedStyle(document.body).backgroundColor,
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="origin, e.g. http://127.0.0.1:19878")
    ap.add_argument("--routes", nargs="+", default=["/"])
    ap.add_argument("--out", default=None, help="evidence dir (default: mktemp dir under /tmp)")
    ap.add_argument("--root-selector", default="#root")
    ap.add_argument("--expect-text", default=None, help="substring that must appear in body text")
    ap.add_argument("--viewport", default="390x844")
    ap.add_argument("--settle-ms", type=int, default=6000)
    ap.add_argument("--executable-path", default=None)
    args = ap.parse_args()

    w, h = (int(x) for x in args.viewport.lower().split("x", 1))
    out = Path(args.out or f"/tmp/local-origin-probe-{time.strftime('%Y%m%d-%H%M%S')}")
    out.mkdir(parents=True, exist_ok=True)

    exe = args.executable_path or _cached_headless_shell()
    result: dict = {"origin": args.url, "viewport": args.viewport,
                    "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "executable_path": exe, "routes": {}}
    failures: list[str] = []

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if exe:
            launch_kwargs["executable_path"] = exe
        browser = p.chromium.launch(**launch_kwargs)
        for route in args.routes:
            name = route.strip("/").replace("/", "_") or "root"
            ctx = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            console: list[dict] = []
            page_errors: list[str] = []
            failed: list[dict] = []
            page.on("console", lambda m: console.append({"type": m.type, "text": m.text[:200]}))
            page.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
            page.on("requestfailed", lambda r: failed.append({"url": r.url[:160],
                                                             "err": str(r.failure)[:120]}))
            resp = None
            try:
                resp = page.goto(args.url.rstrip("/") + route, wait_until="load", timeout=45000)
                page.wait_for_timeout(args.settle_ms)
                state = page.evaluate(PROBE_JS, args.root_selector)
            except Exception as exc:  # noqa: BLE001 - report, never crash the sweep
                state = {"error": str(exc)[:300]}
            shot = out / f"{name}.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception as exc:  # noqa: BLE001
                shot = None
                state.setdefault("screenshot_error", str(exc)[:200])
            status = resp.status if resp else None
            rendered = bool(state.get("rootInnerLen", -1) and state["rootInnerLen"] > 0) \
                or state.get("textLen", 0) > 200
            result["routes"][route] = {
                "http_status": status,
                "rendered": rendered,
                "state": state,
                "console": console[:12],
                "page_errors": page_errors[:6],
                "request_failed": failed[:12],
                "screenshot": str(shot) if shot else None,
            }
            if not rendered:
                failures.append(f"{route}: no mounted DOM (status={status}, root={args.root_selector})")
            if page_errors:
                failures.append(f"{route}: {len(page_errors)} pageerror(s)")
            if args.expect_text and args.expect_text not in (state.get("textHead") or ""):
                failures.append(f"{route}: expected text {args.expect_text!r} absent from rendered body")
            ctx.close()
        browser.close()

    verdict = "PASS" if not failures else "FAIL"
    result["verdict"] = verdict
    result["failures"] = failures
    (out / "probe.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    print(f"\n[{verdict}] evidence dir: {out}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
