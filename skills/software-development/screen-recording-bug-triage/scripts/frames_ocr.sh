#!/usr/bin/env bash
# frames_ocr.sh — sweep every frame of a screen recording through OCR.
#
# Usage: frames_ocr.sh <video> <outdir> [fps] [scale_width]
#   fps default 6, scale_width default 1080 (upscale small phone captures).
#
# Outputs: <outdir>/g_%03d.png and <outdir>/ocr_all.txt with "=== frame ===" markers.
# Then grep ocr_all.txt for the anomaly markers:
#   grep -niE "e\.g\.|TODO|\{\{|undefined|null|lorem|%" <outdir>/ocr_all.txt
set -uo pipefail

VIDEO="${1:?usage: frames_ocr.sh <video> <outdir> [fps] [scale_width]}"
OUT="${2:?usage: frames_ocr.sh <video> <outdir> [fps] [scale_width]}"
FPS="${3:-6}"
WIDTH="${4:-1080}"

[ -f "$VIDEO" ] || { echo "no such video: $VIDEO" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg missing" >&2; exit 1; }
command -v tesseract >/dev/null || { echo "tesseract missing (brew install tesseract)" >&2; exit 1; }

mkdir -p "$OUT"
echo "== artifact =="
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,nb_frames -of default=noprint_wrappers=1 "$VIDEO"
echo "sha256: $(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$VIDEO")"

ffmpeg -v error -y -i "$VIDEO" -vf "fps=${FPS},scale=${WIDTH}:-1:flags=lanczos" "$OUT/g_%03d.png"
COUNT=$(ls "$OUT"/g_*.png 2>/dev/null | wc -l | tr -d ' ')
echo "frames: $COUNT (fps=${FPS}, width=${WIDTH})"

: > "$OUT/ocr_all.txt"
for f in "$OUT"/g_*.png; do
  echo "=== $(basename "$f")" >> "$OUT/ocr_all.txt"
  tesseract "$f" - 2>/dev/null >> "$OUT/ocr_all.txt"
done

echo "ocr: $OUT/ocr_all.txt"
echo "-- anomaly markers --"
grep -niE 'e\.g\.|TODO|\{\{|undefined|null|lorem|placeholder|%' "$OUT/ocr_all.txt" | head -40 || echo "(none)"
