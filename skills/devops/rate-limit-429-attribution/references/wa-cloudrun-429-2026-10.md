# Worked case — WorldArchitect stable/dev campaign-list 429 (2026-10-24)

Project `worldarchitecture-ai`, Cloud Run `us-central1`, service `mvp-site-app-stable` then `mvp-site-app-dev`.
Symptom: campaign list showed "Connection Error / HTTP Error: 429" plus stale cached campaigns. Dev was
reported healthy at first and later proved affected too.

## What the evidence actually was

Request logs (`logName="projects/…/logs/run.googleapis.com%2Frequests"`), projected as
`timestamp, revision_name, status, requestUrl, remoteIp, referer, userAgent`:

- Stable, 22:45–23:16:15: 262 × 429, 724 × 200 across **all** endpoints.
  Per endpoint the numbers were completely different: `/api/campaigns` list 70 accepted / 91 rejected,
  detail 67/49, `/api/settings` 104/54, `/api/waitlist/status` 98/22, `/api/debug-tools/eligibility` 55/46.
  The all-endpoint totals said nothing about which bucket failed.
- Campaign-list per minute: `23:07 13/0`, `23:08 7/4`, then `23:09 0/14`, `23:10 0/23`, `23:11 0/11`,
  `23:12 0/18`, `23:13 0/11`, `23:14 0/5`, `23:15 0/5`. Accepted dropped to **zero** while attempts stayed
  at 5–23/min, i.e. far below a 20/min limit ⇒ the hourly bucket was exhausted, not a per-minute storm.
- Hour math: 29 accepted (22:07–22:45) + 70 accepted (22:45–23:09) = **99** against a `100 per hour` cap.
- Dev, 23:50–23:58: list 10 accepted / 21 × 429; 23:54–23:58: **0 accepted / 14 × 429**, everything else 200.
  A single revision (`…-o1f174cb8-6add392d`) and a single instance served every row; startup log showed
  `Booting worker with pid: 6` (one worker).

## The decisive dev evidence (unavailable on the stable pass)

Dev app logs carried Flask-Limiter's own decision line in `jsonPayload.message`:

```
2026-10-24T23:58:04.183628Z  ratelimit 100 per 1 hour (47.151.147.179) exceeded at endpoint: get_campaigns
```

21 such lines, all window `100 per 1 hour`, all endpoint `get_campaigns`, all one key; 14 of them inside
23:54–23:58 exactly matched the 14 rejected list requests. That converts "probably the IP bucket" into
key + window + endpoint evidence. Query both `textPayload:"ratelimit"` and `jsonPayload.message:"ratelimit"`
— the latter is where these lived.

## Corrections that had to be made in public

1. "One shared bucket for the whole page" — wrong: limits are declared per route, so each endpoint has its
   own counter even when the limit string is identical.
2. "87–161 req/min from one IP" — that was all-endpoint volume including static assets; the failing endpoint
   peaked at 23 attempts/min. Withdrawn as cause evidence.
3. "Recovery is not durable, the loop re-tripped prod" — the 10 × 429 at 23:22:18–22 were another operator's
   disclosed probe (`15× curl 401 → 10× curl 429 → 24× curl 200` on `/`, no referer, ~0.34 s spacing).
   Retracted; that interval proves nothing about natural recurrence.
4. "Dev is unaffected" — wrong, and the phone report was the correction. The dev list endpoint was refusing
   everything while other dev endpoints served normally.

## Still unresolved

- Dev accepted 98 list requests on one revision before the 429 wall (≈ the 100/hour cap), but individual 429s
  at 23:22 were interleaved with accepts at 23:25 on the same revision — a single strict hourly counter cannot
  produce that. The limiter line has no pid/worker/instance, and only one worker was booted, so counter
  multiplicity stays unproven. Report it as missing evidence rather than claiming either explanation.
- Cross-revision aggregation: a rolling hour spanning revisions showed 124 accepted because four revisions
  each had their own in-memory counters. Do not use that number against a per-revision cap.

## Environment notes

- `RATE_LIMIT_STORAGE_URI` unset on every stable/dev revision ⇒ `memory://`, per process, reset on rotation.
- `ProxyFix(app.wsgi_app, x_for=1, x_proto=1)`, limiter `key_func=client_ip` (rightmost XFF), so NAT groups
  share one bucket and one phone can be throttled by another client on the same egress.
- The deploy SA (`dev-runner@`) had `logging.viewer` but not `logging.logMetrics.create`; monitoring writes
  succeeded with `--account=<user account>` (no IAM change made).
