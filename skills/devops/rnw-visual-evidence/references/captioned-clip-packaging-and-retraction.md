# Packaging captioned before/after clips from retained recordings — and retracting a bad pairing

Session: 2026-10-25, `worldai_frontend` PR277 (label deletion on a seeded campaign row), Linux capture
host, Playwright `record_video` at 394x852.

## Why this file exists

Two packets were delivered in one session. The first was **retracted** by the reviewer because the
aggregate videos and the JSON receipts were not from the same run. The second passed independent
review. The difference was entirely packaging discipline, not capture quality.

## Failure shape (the retracted packet)

| symptom | cause |
|---|---|
| aggregate `pr277-after-pair.webm` 1,940,695 B while `vid-after/*.webm` summed to 3,166,336 B | `ffmpeg -f concat` over a directory whose contents changed after the aggregate was built; concat also rewrites container boundaries, so even a stable set never matches byte-sum |
| receipt per-file `1,048,576` and `524,288` B | hashes taken **before** `ctx.close()`; those are exactly 1 MiB / 0.5 MiB chunk boundaries, not final files (final: 1,225,172 / 841,081 B) |
| video showed an unrelated campaign segment, receipts named two different campaigns | the aggregates came from the 04:51/04:53 run (`qnVTO…` both phases); the receipts were 05:06 (`qnVTO…`) and 05:22 (`YjQy…`) — different runs entirely |
| reviewer's 1 fps read: raw setup row still present in AFTER | consequence of the unmatched pairing; nothing to do with the fix |

Retraction that the reviewer accepted, done in this order:

1. **Do not touch the originals.** Re-hash them to prove they are unchanged
   (`sha256sum pr277-after-pair.webm` → `3a8b7f04…`).
2. Write `RETRACTION-pairing-20261025.md` **beside** them: what is retracted, the actual provenance of
   each artifact (run times, campaign ids, both phases), the chunk-boundary mechanism, and an explicit
   "not evidence of" list.
3. Say the retraction in the reply with the hashes, and let a *new* packet supersede it rather than
   relabelling anything.

## Working packet

- Choose ONE segment per phase and name it: `vid9-before/93789dca….webm` (63,690,842 B,
  `414809ca…`, 548.72 s) / `vid9-after/1b31bb28….webm` (63,607,520 B, `a4a464e3…`, 548.60 s).
- Declare the excluded segment and why: `vid9-after/13446eee….webm` (40,370,176 B, `26414a27…`) had no
  duration metadata and a near-blank tail frame — an earlier portion of the same run, not the window.
- Verify the tail really is the claim before clipping: extract the last frame and diff it against the
  screenshot you are claiming (`PIL` resize to 197x426, `ImageStat` mean-abs → `1.59` for both phases =
  same frame).
- Clip recipe (10 s, window readable, caption legible at 394 px):

```bash
printf "%s" "BEFORE 6575b8ae"                                > c1.txt
printf "%s" "opening window: CAMPAIGN SETUP visible"          > c2.txt
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
ffmpeg -y -sseof -6 -i vid9-before/93789dca….webm \
  -vf "scale=394:852,tpad=stop_mode=clone:stop_duration=4,\
drawbox=y=0:h=58:color=black@0.8:t=fill,\
drawtext=fontfile=$FONT:textfile=c1.txt:fontcolor=white:fontsize=14:x=10:y=9,\
drawtext=fontfile=$FONT:textfile=c2.txt:fontcolor=0xFFD700:fontsize=12:x=10:y=31" \
  -c:v libx264 -pix_fmt yuv420p -crf 26 -r 25 clip2-before.mp4
```

- One fact per caption line. A single long caption truncates ("BEFORE 6575b8ae — opening window —
  CAMPAIGN S…").
- `-sseof` seeking is not frame-accurate on VP8: a 14 s tail put mid-campaign content at t=10 s. Keep
  the real window short (≈6 s) and hold the final frame with `tpad`, then verify a late frame
  (`-ss 9.5 -frames:v 1`) shows both caption lines and the claimed UI state.
- Manifest fields that survived review: `generated_utc`, operator scope line, `mint_ledger_count` +
  `new_mints_this_packaging: 0`, per-phase `segment_used`/`bytes`/`sha256`/`duration_s`/`file_mtime_utc`/
  `run_started_utc`/`build`/`served_bundle`/`reference_frame`/`segment_window`/`excluded_segments`,
  clip rows with captions + sha256 + `hold_frame_similarity_to_reference_meanabs`, `identity_limitation`,
  `prior_pairing: RETRACTED … supersedes it`, and a one-line `scope` that denies repo-wide/merge meaning.

## Detector traps paid for in the same session

- `body.includes('Campaign setup')` returned `false` on the build whose frame plainly renders
  `CAMPAIGN SETUP`. Never publish a mixed-case text flag as absence; cite pixels and disclose the
  detector bug.
- `signed_in = "My Campaigns" in body` wrote `signed_in:false` while 11/11 `/api/` calls carried a
  bearer and account data rendered. Identity belongs to `getIdTokenResult()` claims, not page text.
- The app's own `No connection to server` banner is a socket-status string; it coexisted with
  successful API data. Label it "unverified socket-status string", not "API failure" and not "connected".
