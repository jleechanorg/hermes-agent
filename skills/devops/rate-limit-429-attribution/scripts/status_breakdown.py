#!/usr/bin/env python3
"""Per-endpoint / per-window breakdown of Cloud Run request-log rows.

Input: TSV from
  gcloud logging read '<filter>' --limit N \
    --format='value(timestamp,resource.labels.revision_name,httpRequest.status,httpRequest.requestUrl,httpRequest.remoteIp,httpRequest.referer,httpRequest.userAgent)' > rows.tsv

Usage:
  python3 status_breakdown.py rows.tsv --endpoint /api/campaigns \
      --window 2026-10-24T23:54:00Z 2026-10-24T23:58:00Z \
      --csv /tmp/sanitized.csv

Prints: status totals, per-endpoint accepted(200)/rejected(429) with client classes,
a per-minute series for --endpoint, and writes sanitized rows with hashed IPs.
No network calls, no writes outside --csv.
"""
import argparse
import collections
import csv
import hashlib
import sys


def client_class(ua: str) -> str:
    u = (ua or "").lower()
    if "worldai/" in u or "cfnetwork/" in u:
        return "app"
    if "iphone" in u or "ipad" in u or "android" in u:
        return "mobile-browser"
    if u.startswith("curl"):
        return "curl"
    if any(k in u for k in ("python", "httpx", "aiohttp", "go-http-client")):
        return "script"
    if "mozilla" in u:
        return "desktop-browser"
    return "none" if not u.strip() else "other"


def endpoint_of(url: str) -> str:
    path = url.split("?")[0]
    parts = [p for p in path.split("/") if p]
    # redact long identifiers so campaign/user ids never reach the report
    return "/" + "/".join("<id>" if len(p) >= 16 and not p.startswith("api") else p for p in parts)


def load(path: str):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 7:
                continue
            ts, rev, status, url, ip, ref, ua = f[:7]
            if not status:
                continue  # non-request log entries
            rows.append({
                "ts": ts,
                "rev": rev,
                "status": status,
                "url": url,
                "ep": endpoint_of(url),
                "ip": ip,
                "ref": ref,
                "cc": client_class(ua),
            })
    rows.sort(key=lambda r: r["ts"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--endpoint", default=None, help="substring of the URL to expand per-minute")
    ap.add_argument("--window", nargs=2, metavar=("START", "END"), default=None)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    rows = load(args.tsv)
    if not rows:
        print("no request rows parsed")
        return 1
    print("request rows: %d | window: %s -> %s" % (len(rows), rows[0]["ts"], rows[-1]["ts"]))
    print("revisions:", dict(collections.Counter(r["rev"] for r in rows)))
    print("status totals:", dict(sorted(collections.Counter(r["status"] for r in rows).items())))

    agg = collections.defaultdict(lambda: {
        "ok": 0, "rej": 0,
        "ok_cc": collections.Counter(), "rej_cc": collections.Counter(),
    })
    for r in rows:
        a = agg[r["ep"]]
        if r["status"] == "200":
            a["ok"] += 1
            a["ok_cc"][r["cc"]] += 1
        elif r["status"] == "429":
            a["rej"] += 1
            a["rej_cc"][r["cc"]] += 1

    print("\nper endpoint (accepted=200 / rejected=429):")
    for ep, a in sorted(agg.items(), key=lambda kv: -(kv[1]["ok"] + kv[1]["rej"])):
        print(" %-52s 200=%4d 429=%4d accepted=%s rejected=%s"
              % (ep, a["ok"], a["rej"], dict(a["ok_cc"]), dict(a["rej_cc"])))

    if args.endpoint:
        print("\nper-minute series for URLs matching %r:" % args.endpoint)
        series = collections.defaultdict(lambda: {"ok": 0, "rej": 0, "who": collections.Counter()})
        for r in rows:
            if args.endpoint not in r["url"]:
                continue
            slot = series[r["ts"][11:16]]
            if r["status"] == "200":
                slot["ok"] += 1
            elif r["status"] == "429":
                slot["rej"] += 1
                slot["who"][r["cc"]] += 1
        for minute in sorted(series):
            s = series[minute]
            print(" %s accepted=%3d 429=%3d rejected_clients=%s"
                  % (minute, s["ok"], s["rej"], dict(s["who"])))

    if args.window:
        start, end = args.window
        sl = [r for r in rows if start <= r["ts"] < end]
        print("\nwindow %s..%s: rows=%d status=%s"
              % (start, end, len(sl),
                 dict(sorted(collections.Counter(r["status"] for r in sl).items()))))
        for ep in sorted({r["ep"] for r in sl}):
            c = collections.Counter(r["status"] for r in sl if r["ep"] == ep)
            print("  %-52s %s" % (ep, dict(sorted(c.items()))))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["timestamp_utc", "revision", "status", "endpoint", "client_class",
                        "referer_origin", "ip_key"])
            for r in rows:
                ref = r["ref"] or ""
                origin = ref.split("/")[2] if "//" in ref else ("-" if not ref else ref)
                w.writerow([r["ts"], r["rev"], r["status"], r["ep"], r["cc"], origin,
                            "IP-" + hashlib.sha256(r["ip"].encode()).hexdigest()[:8]])
        data = open(args.csv, "rb").read()
        print("\ncsv: %s rows=%d bytes=%d sha256=%s"
              % (args.csv, data.count(b"\n") - 1, len(data), hashlib.sha256(data).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
