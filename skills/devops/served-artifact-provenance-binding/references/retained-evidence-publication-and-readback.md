# Publishing a retained evidence bundle and proving it landed

Worked 2026-10-25 (PR #283, `worldai_frontend`). A capture bundle existed only on a *different host*;
publication had been denied earlier; the PR body still claimed draft + "upload awaits approval".
This is the recipe that closed it, end to end, without recapturing anything.

## 1. Recover the bundle before considering a rebuild

The bundle path in a PR body is a **task-owned** path, not necessarily yours:

- `/tmp/worldai_frontend/evidence/.../publish-283-<sha>-v2/` did not exist on the Mac at all, and the
  GCS prefix returned *no objects*.
- It did exist on the Linux lane host: same path under `/home/jleechan/...`, 86 files / 10.8 MB.
- Check the other hosts **before** saying "evidence is lost" or rebuilding: absence on one host is not
  absence. Do not recapture; recover.

Transfer + integrity:

```bash
scp -q -r "host:/tmp/.../bundle/." "$LOCAL/"
cd "$LOCAL" && sha256sum -c *.sha256 | grep -c ': OK$'   # 43/43 shipped sidecars
```

The bundle shipped its own `.sha256` sidecars — verify against them, don't invent hashes.

## 2. Allowlist scan before any upload

```bash
grep -rIl -E "xox[baprs]-|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|BEGIN [A-Z ]*PRIVATE KEY" "$B"
find "$B" -type f \( -iname "*.env*" -o -iname "*token*" -o -iname "*.pem" -o -iname "*.p12" \) | head
find "$B" -type f | sed 's/.*\.//' | sort | uniq -c   # expect png/mp4/json/log/md/sha256 only
```

Publish the **bundle**, never the worktree, the export directory, an app bundle, raw cloud logs, the
private supplied input, or any user policy file. Name what you excluded in the PR body.

## 3. Upload once, through the already-approved route

```bash
gcloud storage cp -r "$B"/* "gs://<bucket>/agent-evidence/<repo>/<prefix>/"
```

- Record the wall-clock window (`02:52:53Z → 02:53:01Z`) as part of the receipt.
- If a prior attempt was **denied**, first re-prove the target is still unexecuted
  (`gcloud storage ls "<prefix>/**"` → "matched no objects"), then retry exactly once under the new
  grant. Never switch uploader/account/transport to get past a denial.

## 4. Remote readback is the claim — not the upload exit code

```bash
gcloud storage ls -r "$DST/**" | wc -l          # 86 objects
gcloud storage du -s "$DST"                     # 10,823,815 B == local du -sb
gcloud storage ls -L "$DST/<file>" | grep -E "Hash \(MD5\)|Content-Type|Size"
```

GCS gives MD5 + CRC32C, not sha256. Cross-check by converting the local digest:

```python
base64.b64encode(hashlib.md5(open(f,'rb').read()).digest()).decode() == remote_md5_base64
```

Then prove end-to-end bytes by downloading one object anonymously and re-hashing:

```bash
curl -sS -o /tmp/rt.mp4 "<public-url>" && shasum -a 256 /tmp/rt.mp4   # must equal local sha256
```

## 5. Viewability, per embedded URL

```bash
curl -sS -m 25 -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" "$URL"
```

Every URL that appears in the PR body gets its own 200 + expected content type. A bucket you can list
is not automatically anonymously readable; test the exact object URLs you embed.

## 6. What GitHub will and will not render

- **MP4 does not inline-play** from a third-party host. Link the file and supply a poster image:
  `[Desktop comparison MP4](<mp4>) ([poster](<png>))`, and say in the body that the link opens the file.
- PNG/JPEG with an anonymously reachable URL renders inline.
- Do not claim "embedded video playback on the PR" — claim "linked, HTTP 200, poster rendered".

## 7. Label media by what it actually is

A "comparison video" is usually a **captioned two-state animation**, not an interaction recording.
Prove which before writing the word "recording":

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,r_frame_rate,duration -of default=noprint_wrappers=1 "$f"
ffmpeg -v error -i "$f" -f framemd5 - | grep -v '^#' | awk -F, '{print $6}' | sort -u | wc -l
```

- 55 frames / **53 unique** and 54 / **50 unique** ⇒ animated, not a frozen still — but still only two
  UI states.
- Confirm content from extracted frames (`ffmpeg -ss <t> -frames:v 1`), and state the absence of
  cursor/hover/typing/scroll artifacts.
- Write: "captioned side-by-side **static comparison animations**, not interaction recordings, and not
  continuous player playback."

## 8. Applicability after the head moves — delta, then say it explicitly

The capture stays bound to its own SHA forever. Applicability to a newer head is a **content** test:

```bash
for f in src/screens/LandingScreen.tsx src/components/TopBar.tsx; do
  a=$(gh api "repos/$R/contents/$f?ref=<capture-sha>" -H "Accept: application/vnd.github.raw" | shasum -a 256)
  b=$(gh api "repos/$R/contents/$f?ref=<current-head>" -H "Accept: application/vnd.github.raw" | shasum -a 256)
  [ "${a%% *}" = "${b%% *}" ] && echo "IDENTICAL $f" || echo "DIFFERENT $f"
done
gh api "repos/$R/compare/<capture-sha>...<head>" --jq '.files[]|"\(.status) +\(.additions)/-\(.deletions) \(.filename)"'
```

If the changed paths are CI/docs only and the UI files are byte-identical, the pixel claim survives —
and you still **must not** relabel the capture SHA. Words that survived review: "capture SHA not
relabelled to `<new>`; current-head applicability rests only on the separately inspected UI-unchanged
delta."

## 9. Editing a PR body another writer has already touched

1. Re-read the body (`gh pr view --json body`) immediately before editing — it changed twice mid-session
   in this case, and the old text already contained a *different* capture paragraph to preserve.
2. Replace with **unique-anchor asserts**, not blind string replace:
   `assert src.count(old) == 1` per paragraph; fail closed on 0 or 2.
3. Correct only the stale claims (stage, draft/non-draft, "upload awaits approval" → publication
   receipt). Preserve pins, timestamps, line-delta tables and proof limits verbatim.
4. Read back: body length, head unchanged, `draft` flag, and a count of every embedded URL.

## 10. Publication receipt shape

Object prefix · upload UTC window · object count and total bytes (remote) vs local · per-artifact
size + sha256 · MD5 readback match · one anonymous re-download sha256 · per-URL HTTP status/content
type · explicit "not reviewed / not claimed" list · explicit statement that the earlier denial never
executed and that no alternate uploader was used.
