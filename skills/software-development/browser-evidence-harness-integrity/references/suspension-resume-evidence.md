# Suspension / resume evidence — session detail (2026-10-25)

Evidence set for "portrait generation must survive the user tabbing away", built on
`worldai_frontend` PR #292 (client) + `worldarchitect.ai` PR #10866 (server operation record).
Two clips were produced and **both failed to prove what their filenames implied**. That is the
value of this reference: the harness defects, not the product story.

## What the clips were supposed to show

| clip | claim | reality |
|---|---|---|
| BEFORE v1 | page suspended mid-generation → generation lost | **no loss** — provider answered at `t+5.9 s`; the page was suspended at `t+8 s` and the transport cut at `t+9.2 s`, i.e. after the response had been handled. Panel reached "Preview ready". Published labelled as an honest non-reproduction. |
| BEFORE v2 | same, with the cut at `≤1 s` | showed `suspended + transport dead` (real `net::ERR_EMPTY_RESPONSE`) but **never the return frames** — see the log-path bug below |
| AFTER v1 | return reaches the same completed operation, one generation | valid for the recovery logic — but only ran with `ENVIRONMENT=preview` (URL delivery) + a pinned `image_provider_preference`, so it did not exercise the delivery mode real users get |

## Defect 1 — cut armed off a wall clock instead of the request

```
suspend at t+8.0s   cut at t+9.2s   provider_http_ms 5765.8   -> "Preview ready"
```

The harness used `setTimeout` cutpoints. Arm the cut from the observed request instead
(proxy `request` event or the server's `POST /api/...` line) and log both timestamps:

```
REQ t+0.0 POST /api/portrait/generate
CUT t+0.4 <SIGKILL proxy>      # must be strictly before the provider returns
```

## Defect 2 — wait-predicate pinned to a stale log path, recorder killed before close

```js
// v1 harness, still baked into harness-run-v2.mjs
const BACKEND_LOG = '/tmp/worldarchitect.ai/portrait-resume-evidence/backend.log';
const backendLogCount = (n) => fs.readFileSync(BACKEND_LOG,'utf8').split('\n').filter(l=>l.includes(n)).length;
```

The v2 run wrote `backend-v2-before.log`; the predicate kept reading the v1 file, never matched,
ran to the 300 s cap, and the wrapper killed `node` **before `ctx.close()`**. Result: a published
`portrait-resume-before-v2.mp4` that stops at the suspension, plus an un-finalised raw `.webm`
(327.04 s, no cues) and a missing `requests.json`.

Fix applied (both harness copies):

```js
const EVID_DIR = '/tmp/worldarchitect.ai/portrait-resume-evidence';
const BACKEND_LOG = (() => {
  const explicit = args.get('backend-log');
  if (explicit && fs.existsSync(explicit)) return explicit;
  const cands = fs.readdirSync(EVID_DIR)
    .filter((f) => /^backend.*\.log$/.test(f))
    .map((f) => path.join(EVID_DIR, f))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return cands[0] || path.join(EVID_DIR, 'backend.log');
})();
```

Two rules that follow, independent of this harness: the predicate must accept an explicit path, and
the recorder must close in a `finally` so a timeout still produces a labelled partial clip.

## Defect 3 — you cannot force `hidden` from automation on this host

| attempt | observed |
|---|---|
| second tab via `Target.activateTarget` | page still `visible` |
| `Browser.setWindowBounds → windowState: minimized` (read back as minimized) | still `visible` |
| Firefox 132 equivalent | still `visible` |
| CDP `Page.setWebLifecycleState: frozen` | JS kept running, in-flight fetch not aborted |

So the `hidden` transition in both clips is **synthetic**: `Document.prototype.visibilityState`
overridden + a real `visibilitychange` dispatched. Labelled in-video, in captions (cue 8) and in the
bundle README. The transport death is real and separately evidenced.

## What was real in the AFTER clip

```
00:19:16 portrait_assembled_prompt {"event":"generate_preview", ...}
00:19:22 werkzeug "POST /api/portrait/generate HTTP/1.1" 200 -
00:19:23 portrait_timing {"event":"generate_preview","provider":"xai","provider_http_ms":6639.9,...}
00:19:25 werkzeug "GET /api/portrait/operations/08ecebc4-878b-4387-ac8d-990727e18ec7 HTTP/1.1" 200 -
```

One `POST`, then only status `GET`s on return → the duplicate-work claim is supportable from server
lines alone (never from the UI).

## Cost accounting is part of the receipt

Paid generations: v1 after 1, v1 before 1, v2 before 1, after-default 1, planned v3 1 = **5**.
State the running tally to the operator; "at most N, then stop" in the brief is what keeps an
evidence lane from re-shooting until the clip accidentally tells the truth.

## Artifact verification actually performed

```bash
B=https://storage.googleapis.com/wa-test-evidence/portrait-resume-20261025
curl -s -o f.mp4 -w '%{http_code} %{size_download}\n' "$B/portrait-resume-before-v2.mp4"
shasum -a 256 f.mp4     # 355814578274b221… 607,686 B
```

Hashes matched the lane's report, and the v1 files were still present — but a matching hash says
nothing about frame coverage, which is why defect 2 shipped in the first place.
