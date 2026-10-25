---
name: screen-recording-bug-triage
description: Use when a user posts a screen recording of a UI bug.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [video, ui-bug, ocr, triage, evidence]
    related_skills: [rnw-visual-evidence, vision-extract-large-image, worldai-ios-app]
---

# Screen-recording UI bug triage

A phone/screen recording is dense evidence but a poor transcript. Never guess from a
thumbnail, and never ask the user to describe what is on screen — the artifact is
inspectable. Produce a **string ledger** (exact visible text → source location) before
any code work, then hand that ledger to exactly one writer.

## When to use
- User attaches a video (`video_*.mp4` under `~/.hermes/cache/videos/`) of an app/web UI
  misbehaving: "weird placeholder text", "this shows garbage", "delete this".
- A flow that only reproduces at runtime (campaign creation, onboarding, streamed
  responses) where unit tests cannot show the rendered copy.

## Steps

1. **Receipt the artifact.** Record full path, `ffprobe` duration/resolution/frames, and
   the full `sha256`. Quote that hash when coordinating with other agents; a peer may
   cite a truncated hash and you must confirm it byte-for-byte.

2. **Frame sweep + OCR (all frames, not samples).**
   `bash scripts/frames_ocr.sh <video> <outdir> [fps]` (in this skill) does:
   `ffmpeg -vf "fps=N,scale=1080:-1:flags=lanczos"` → `tesseract <frame> -` per frame →
   one `ocr_all.txt` with `=== frame ===` markers.
   Sweep at fps=6 for a ~10s clip; that is cheap and catches transient states.
   Then grep the OCR for evidence markers: `e\.g\.|TODO|\{\{|undefined|null|lorem|%`.

3. **Read the interesting frames with vision at 2× scale.** Upscale the specific frames
   (`ffmpeg -i f.png -vf "scale=1440:-1:flags=lanczos"`), then `vision_analyze` with a
   targeted question ("transcribe the card under the X header verbatim"). OCR mangles
   small UI text and *mirrors/inverts* flipped panels — only vision distinguishes "weird
   text" from "text rendered upside down".

4. **Build the string ledger.** For each suspicious string, record: literal text, the UI
   role (label / hint / placeholder / streamed body), the timestamp in the clip, and
   whether it is user-typed, template copy, or server data.

5. **Bind each string to source — in both repos.**
   - Client first: `git show origin/main:src/...` or `git grep -n "<literal>" origin/main -- src`.
     Read `origin/main`, not your dirty worktree (it is often far behind).
   - If the literal is absent from the client, grep the backend/API repo
     (`mvp_site/...`). Server-composed strings (e.g. pipe-delimited prompts) are only
     *displayed* by the client; the fix may be render-side, not generation-side.
   - Check how a label got attached (e.g. a player-row mode resolver rendering a seeded
     row as `GOD`) — the label often misleads about which subsystem produced the text.

6. **Check whether the ugly thing is deliberate before "fixing" it.**
   `br list | grep -iE "<feature>|seed|summary"` and read the bead/PR that introduced it.
   Deliberate contracts (layout stability, height reservation, dedupe rows) must survive:
   hide the *text*, keep the *contract*. Say this explicitly in the brief or the worker
   will regress a previously fixed jump/blank-band bug.

7. **Separate the report into independent defects.** One recording usually contains 2–4:
   raw internal string, an orientation/transform bug, unformatted streaming markdown,
   stale loading copy. Name each with its own anchor and let one writer handle them as
   scoped commits — do not let a "delete this text" request silently become a refactor.

8. **Hand off to a single writer with the ledger.** Fresh worktree from `origin/main`,
   bead id, exact literals to disappear, the contract to preserve, RED-first tests, and
   the before/after evidence requirement. Keep the user's clip as BEFORE evidence and
   publish the full sha256 with it.

## Pitfalls
- Sampling 2 frames misses the 0.5s transition where the raw string appears; sweep all.
- OCR of an inverted panel yields reordered gibberish — do not report it as a different
  bug from the visual flip; verify orientation with vision first.
- `git grep origin/main` prints `warning: refname 'origin/main' is ambiguous` when a
  local branch shares the name; the results are still valid — confirm the SHA with
  `git rev-parse origin/main` and quote it.
- A placeholder string that looks "truncated weirdly" is usually just field-width
  clipping, not a copy bug. Do not delete legitimate example copy.
- Don't claim the deployed build matches local head; record the clip as *unbound*
  evidence unless the app build/commit is proven.

## Verification
- Ledger has one row per visible anomaly, each with literal text and a file:line anchor
  (or an explicit "no client source — server-composed" note).
- Every "keep" contract is named with its bead/PR before implementation starts.
- Final report cites the clip sha256, RED artifact, PR URL + head SHA, and after-evidence
  paths; no claim of "fixed" without them.

## Support files
- `scripts/frames_ocr.sh` — frame extraction + per-frame OCR into one sweep file.
- `references/creation-flow-seed-row-case.md` — worked example: WA iOS creation seed row
  rendered verbatim as a `GOD` row, plus orientation and streaming-markdown defects.
