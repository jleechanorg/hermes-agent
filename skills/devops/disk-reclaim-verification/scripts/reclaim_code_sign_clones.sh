#!/bin/bash
# Reclaim leaked macOS "code_sign_clone" temp copies.
#
# Why: when a launched .app fails to finish Gatekeeper verification (headless
# Chrome killed mid-launch, overlapping launches), macOS leaves a full ~1.4 GiB
# copy of the app bundle under
#   /private/var/folders/<xx>/<hash>/X/<bundle-id>.code_sign_clone/code_sign_clone.XXXXXX
# NOTE the X component: $TMPDIR / `getconf DARWIN_USER_TEMP_DIR` points at the
# sibling T directory, so walking $TMPDIR finds none of them.
# These are volatile verification scratch copies, regenerated on demand; they
# are not user data.
#
# Usage:
#   reclaim_code_sign_clones.sh                     # dry-run (default): report only
#   reclaim_code_sign_clones.sh --delete            # actually remove stale clones
#   reclaim_code_sign_clones.sh --delete --min-age-min 60
#
# Safety: only removes entries under .../X/*.code_sign_clone/ whose basename
# starts with "code_sign_clone." and whose mtime is older than --min-age-min.
# Dry run verified 2026-10-24: 155 dirs / 218.2 GiB, 14 s.

set -uo pipefail

DELETE=0
MIN_AGE_MIN=30
while [ $# -gt 0 ]; do
  case "$1" in
    --delete) DELETE=1; shift ;;
    --min-age-min) MIN_AGE_MIN="${2:?--min-age-min needs a value}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null || true)"
ROOT="${ROOT%/}"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "cannot resolve DARWIN_USER_TEMP_DIR" >&2
  exit 1
fi

# getconf returns /var/folders/... (symlink to /private/var/folders/...).
# Resolve BEFORE validating, or the guard rejects the real path.
ROOT_RESOLVED="$(cd -P "$ROOT" 2>/dev/null && pwd -P)"
case "$ROOT_RESOLVED" in
  /private/var/folders/*/T) ;;
  *) echo "unexpected temp root: $ROOT_RESOLVED" >&2; exit 1 ;;
esac

PARENT="$(dirname "$ROOT_RESOLVED")/X"
if [ ! -d "$PARENT" ]; then
  echo "no X dir at $PARENT — nothing to do"
  exit 0
fi

total_bytes=0
total_dirs=0
removed_bytes=0
removed_dirs=0

for clone_root in "$PARENT"/*.code_sign_clone; do
  [ -d "$clone_root" ] || continue
  echo "== $clone_root"
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    case "$(basename "$d")" in
      code_sign_clone.*) ;;
      *) continue ;;
    esac
    case "$d" in
      "$clone_root"/code_sign_clone.*) ;;
      *) echo "refusing unexpected path: $d" >&2; continue ;;
    esac
    sz=$(du -sk "$d" 2>/dev/null | awk '{print $1}')
    sz=${sz:-0}
    total_bytes=$((total_bytes + sz)); total_dirs=$((total_dirs + 1))
    if [ "$DELETE" -eq 1 ]; then
      if rm -rf -- "${d:?}" 2>/dev/null; then
        removed_bytes=$((removed_bytes + sz)); removed_dirs=$((removed_dirs + 1))
      else
        echo "  FAILED: $d" >&2
      fi
    fi
  done < <(find "$clone_root" -maxdepth 1 -mindepth 1 -type d -mmin +"$MIN_AGE_MIN" 2>/dev/null)
done

gib() { awk -v k="$1" 'BEGIN{printf "%.1f", k/1048576}'; }
echo "-----------------------------------------------"
echo "stale clones (older than ${MIN_AGE_MIN}m): $total_dirs dirs, $(gib "$total_bytes") GiB"
if [ "$DELETE" -eq 1 ]; then
  echo "removed: $removed_dirs dirs, $(gib "$removed_bytes") GiB"
  echo "now sample df over several minutes before claiming the space (release is deferred):"
  df -h /System/Volumes/Data | tail -1
else
  echo "dry-run only — pass --delete to remove"
fi
