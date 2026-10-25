# Unmatched artifact pairs: how to detect, label and retract them (verified 2026-10-25)

A packet can look complete — video, JSON receipts, hashes, provenance — and still be **two packets**.
This case: two `ffmpeg -f concat` aggregate clips were published together with per-phase JSON receipts.
The reviewer's 1 fps read caught what the filenames hid: the AFTER clip opened with an unrelated
campaign segment, and the receipts described different captures.

## Detection checklist (run before publishing, and when a reviewer disputes a packet)

1. **Same-run test.** For each artifact, write down `captured_utc` / build / campaign / origin. If the
   receipt's campaign or timestamp differs from the session that produced the video, the pair is
   unmatched — full stop. Here: aggregates came from the `04:51Z/04:53Z` run (both phases campaign
   `qnVTO…`), receipts were `05:06Z` (`qnVTO…`) and `05:22Z` (`YjQy…`).
2. **Sum-of-parts test.** For a concatenated video, compare `sum(per-context bytes)` with the aggregate
   size and `ffprobe` durations. `ffmpeg concat -c copy` rewrites container framing, so exact equality is
   not expected — but a gap of megabytes means the source set changed after aggregation (observed:
   3,166,336 B of parts vs a 1,940,695 B aggregate).
3. **Chunk-boundary tell.** Per-file sizes of exactly `1,048,576` / `524,288` bytes are Playwright
   `record_video` snapshots taken **before** `ctx.close()`. Later sizes were `1,225,172` / `841,081` for
   the same files. Re-hash after close; treat any power-of-two size as a red flag.
4. **Content sanity.** Frame-read the first second: an unrelated campaign title, a different scroll
   position, or a raw-vs-hidden mismatch means the clip is not the run the receipt describes.

## What to do when it is unmatched

- **Retract by name, preserve bytes.** Write a `RETRACTION-<pairing>-<date>.md` beside the originals that
  states: pairing RETRACTED, which artifacts came from which run, the mechanism (pre-close hashing,
  aggregation over a changed set), and an explicit "not evidence of: X, Y, Z". Never rehash, rename,
  re-encode or relabel the originals to make them fit — a byte change destroys the ability to audit the
  mistake.
- **Quote the unchanged hashes** in the retraction so a reader can confirm the originals were not touched.
- **Re-derive rather than argue.** Produce a fresh coherent run (per-file hashes computed post-close, the
  concat command and list recorded, aggregate sha256 + durations) instead of re-explaining the old one.
- Keep the corrected receipts and clips as **one** packet: if the clip changed, the receipt changes with it.

## Observation-time scoping (applies to identity and auth claims too)

A fresh SDK identity read establishes the identity **at that instant**, and nothing about earlier
artifacts. Say it that way: "identity observed `2026-10-25T06:30:17Z`: uid matches dedicated, provider
`custom`; it does not bind the historical clips." Likewise a `signed_in` boolean derived from rendered
text is a heuristic, not an identity observation — replace it with real SDK claims rather than defending
the flag.
