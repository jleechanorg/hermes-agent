#!/usr/bin/env python3
"""Sanitize an evidence packet and rebuild a verifiable manifest.

Derived from the code that produced the PR160 v3 packet. Two invariants:

  1. Provenance tokens (served bundle name, asset fingerprints, full sha256, sha prefixes,
     Playwright artifact names) are MASKED before any identifier redaction, then restored.
     Skipping this turns `index-<hash>.js` into `index-campaign-E.js` and fabricates ids.
  2. Identifier redaction is applied ONLY to records that can carry account ids. Build logs
     carry asset hashes, not account ids — redacting them corrupts the build record.

Text files are rewritten; media is copied verbatim. Media whose captions contain identifiers
needs a re-encoded derivative (ffmpeg drawbox/drawtext) — see
references/packet-sanitization-and-derivation-repair.md §4. This script does not re-encode.

Usage:
    python3 sanitize_packet.py --src <raw-dir> --out <publish-dir> \
        [--id-prefix logs/ --id-prefix run- --id-prefix rig/] \
        [--plain path/without/ids.py]

Exit 0 when the manifest verifies and the leak scan is clean; exit 2 otherwise.
"""
import argparse
import hashlib
import os
import re
import shutil
import sys

TEXT_EXT = {".log", ".out", ".txt", ".md", ".json", ".py", ".js", ".csv"}

ID20 = re.compile(r"\b(?=[A-Za-z0-9]{20}\b)(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[a-z])"
                  r"(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]{20}\b")
ID32 = re.compile(r"\b[0-9a-f]{24,32}\b")
SLUG = re.compile(r"\b[a-z]+-[a-z]+-\d{4,}\b")
TITLE = re.compile(r"(\btitle\s+)([^\n]+)")

PROTECT = [
    re.compile(r"\.[0-9a-f]{32}\.[a-z0-9]{2,5}\b"),   # Name.<hash>.ttf|webp
    re.compile(r"index-[0-9a-f]{32}\.js"),            # served bundle
    re.compile(r"page@[0-9a-f]{32}"),                 # Playwright artifact name
    re.compile(r"\b[0-9a-f]{64}\b"),                  # full sha256
    re.compile(r"\b[0-9a-f]{8,16}\b"),                # sha prefixes
]
PH = "\x00P%d\x00"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def sha12(s):
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def mask(text):
    keep = []

    def sub(m):
        keep.append(m.group(0))
        return PH % (len(keep) - 1)

    for rx in PROTECT:
        text = rx.sub(sub, text)
    return text, keep


def unmask(text, keep):
    for i, tok in enumerate(keep):
        text = text.replace(PH % i, tok)
    return text


def collect_labels(texts):
    """Stable id -> campaign-<letter> map, discovered from id-carrying records only."""
    found, seen = [], set()
    for t in texts:
        masked, _ = mask(t)
        for rx in (ID20, ID32, SLUG):
            for m in rx.findall(masked):
                if m not in seen:
                    seen.add(m)
                    found.append(m)
    labels = {}
    for i, cid in enumerate(found):
        labels[cid] = "campaign-" + (chr(ord("A") + i) if i < 26 else str(i + 1))
    return labels


def redact(text, labels, ids=True):
    text, keep = mask(text)
    if ids:
        for cid, lab in sorted(labels.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(cid, lab)
        text = TITLE.sub(lambda m: m.group(1) + "<title-redacted>", text)
    home = os.path.expanduser("~")
    text = text.replace(home, "<home>")
    return unmask(text, keep)


def json_safe_literals(text):
    """A redacted python/json string literal must stay a string: 'campaign-A' is fine,
    but never leave a bare <placeholder> inside code. Keep this a warning-only check."""
    return re.findall(r"=\s*<[a-z-]+>", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="raw/private source directory")
    ap.add_argument("--out", required=True, help="sanitized publish directory")
    ap.add_argument("--id-prefix", action="append", default=None,
                    help="path prefix whose files may hold account identifiers (repeatable)")
    ap.add_argument("--plain", action="append", default=[], help="exact rel paths to treat as path-only")
    args = ap.parse_args()

    id_prefixes = args.id_prefix or ["logs/", "run-", "rig/", "capture"]

    def carries_ids(rel):
        if rel in args.plain:
            return False
        return any(rel.startswith(p) for p in id_prefixes)

    src_files, texts = {}, {}
    for root, _d, fs in os.walk(args.src):
        for fn in fs:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, args.src)
            src_files[rel] = p
            if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                texts[rel] = open(p, encoding="utf-8", errors="replace").read()

    labels = collect_labels([t for r, t in texts.items() if carries_ids(r)])

    os.makedirs(args.out, exist_ok=True)
    for rel, p in src_files.items():
        dst = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(dst) or args.out, exist_ok=True)
        if rel in texts:
            body = redact(texts[rel], labels, ids=carries_ids(rel))
            with open(dst, "w") as fh:
                fh.write(body)
            for lit in json_safe_literals(body):
                print("WARN non-literal redaction in %s: %s" % (rel, lit), file=sys.stderr)
        else:
            shutil.copy2(p, dst)

    entries = []
    for root, _d, fs in os.walk(args.out):
        for fn in fs:
            if fn == "SHA256SUMS.txt":
                continue
            p = os.path.join(root, fn)
            entries.append((os.path.relpath(p, args.out), sha256_file(p)))
    entries.sort()
    with open(os.path.join(args.out, "SHA256SUMS.txt"), "w") as fh:
        for rel, h in entries:
            fh.write("%s  %s\n" % (h, rel))

    bad = 0
    for rel, h in entries:
        if sha256_file(os.path.join(args.out, rel)) != h:
            print("MISMATCH", rel, file=sys.stderr)
            bad += 1
    leaks = []
    for cid in labels:
        for rel in src_files:
            p = os.path.join(args.out, rel)
            if rel in texts and cid in open(p, encoding="utf-8", errors="replace").read():
                leaks.append((cid, rel))
    print("files:", len(entries), "labels:", len(labels), "mismatches:", bad,
          "leaks:", len(leaks), "manifest_sha256:",
          sha256_file(os.path.join(args.out, "SHA256SUMS.txt")))
    for cid, rel in leaks:
        print("LEAK %s in %s" % (sha12(cid), rel), file=sys.stderr)
    return 0 if bad == 0 and not leaks else 2


if __name__ == "__main__":
    sys.exit(main())
