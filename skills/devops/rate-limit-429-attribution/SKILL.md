---
name: rate-limit-429-attribution
description: Use when 429s hit prod; bind revision, endpoint, key.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [rate-limiting, 429, cloud-run, observability, incident-forensics]
    related_skills: [gcp-alert-notification-authoring, served-artifact-provenance-binding, receipt-provenance-discipline, monitor-predicate-red-green]
---

# 429 attribution forensics

## When to Use

Any report of `HTTP 429`, "rate limited", "Too Many Requests", or a UI that silently falls back to cached/offline data because a read was refused. Also use it to answer "is this fleet-wide or one client?", "was that rejection window our probe or a real client?", and "did the rollback actually fix it?".

The deliverable is an attribution, not a story: **service + full revision + instance + exact endpoint + window + accepted/rejected counts + the limiter's own key evidence + what is still unproven.**

## 1. Bind provenance before counting anything

- Service and **full** revision name: `gcloud run services describe <svc> --format='value(status.traffic)'`, `gcloud run revisions list --service <svc> --limit 5`.
- Revision names from a config generation share a prefix (`…-od461c066-6add4156` vs `…-od461c066-6ad7f18e` are **different revisions**). A grep or metric keyed on the prefix conflates a bad deploy with the later rollback. Always use the full name.
- Per-row provenance: Cloud Run request logs carry `resource.labels.revision_name` and `labels.instanceId`; project them into every query so revision and instance are on the row, not inferred later.
- Check startup logs for process multiplicity: `jsonPayload.message:"Booting worker"`. One instance can still run several worker processes, and in-process limiter storage is per **process**.

## 2. Count per exact endpoint and per window — aggregates cannot establish a per-endpoint cause

- Route limits are usually declared per route, so each endpoint has its **own** bucket. Summing across endpoints ("N req/min from one IP", "724 accepted") proves nothing about the endpoint that failed.
- Publish a table: endpoint × window → accepted (200) / rejected (429), plus the client class of each.
- **Do not aggregate accepted counts across revisions.** Counters live in process memory unless a shared store is configured (`RATE_LIMIT_STORAGE_URI`), so each revision start and each process restart zeroes them. A rolling hour that spans a rollout can show more accepted requests than the configured hourly cap and still be consistent with the cap.
- Cross-check both limits when the route configures two (`"100 per hour, 20 per minute"`): rejections that continue while attempts stay far below the per-minute limit mean the **hourly** bucket is exhausted, not a per-minute storm. Expect to see both strings in the limiter log across an incident (`100 per 1 hour` for the wall, `20 per 1 minute` for the bursts) — report each count separately.
- Cumulative accepted **above** the nominal hourly cap over a span longer than an hour does **not** prove multiple counters; a sliding window explains it. Only per-process state (worker boot lines) or an explicit shared store can settle counter multiplicity.

## 2b. Mapping an alert's reported value onto request rows

An alert that fires on a rolling window (e.g. `10m` rolling, held `5m`) reports the count for **its** window, which is not the window ending at the notification time. In one incident the email said value `22` while the 10-minute window ending at receipt held only `17` — the five earliest events had aged out. Rules:

- Compute several candidate windows and report the arithmetic; do **not** claim an exact evaluation interval or alert-open time without the metric interval.
- Keep the notification's own incident start authoritative and say the alignment is **Unknown**.
- Never "fix" the mismatch by shifting the receipt time.

## 3. Prefer the limiter's own log line over inference

Flask-Limiter (and equivalents) log the decision with the key and window:

```
ratelimit 100 per 1 hour (<key>) exceeded at endpoint: get_campaigns
```

Often in `jsonPayload.message` (not `textPayload`), so query both fields:

```bash
gcloud logging read 'resource.type="cloud_run_revision"
  AND resource.labels.service_name="<svc>"
  AND timestamp>="<start>" AND timestamp<"<end>"
  AND jsonPayload.message:"ratelimit"' --limit 300 \
  --format='value(timestamp,jsonPayload.message)'
```

That line yields key, window and endpoint directly. Keep it distinct from the request `remoteIp`: the edge view and the limiter key can differ (proxy trust chain, `ProxyFix(x_for=N)`), and only the limiter line tells you what the counter was keyed on. If the log carries no pid/worker/instance, say so — you cannot prove counter multiplicity from it.

## 4. Separate every operator's probes from ordinary traffic

Classify rows by user agent, referer origin, and cadence before attributing anything:

- `curl` / `python-requests` / no referer / ~0.3 s fixed spacing ⇒ scripted probe or retry loop.
- `Mozilla/…` with a page referer ⇒ browser; app UAs (`WorldAI/x CFNetwork/…`) ⇒ shipped mobile client; a phone on the same NAT is a **victim** of an exhausted per-IP bucket, not the driver.
- A probe burst often has a signature (e.g. `15×401 → 10×429 → 24×200`) and an exact request count. When a reported "recurrence" window overlaps another operator's disclosed probe, **retract the recurrence claim** and state that the interval proves nothing either way.

## 5. A rollout is not a fix

Fresh processes mean fresh in-memory counters. Zero 429s immediately after a rollback is expected by construction. Certifying recovery requires passive logs over at least one full limiter window from instance start, with the count stated against the configured cap; otherwise report "unproven".

## 6. Never generate load to prove a limiter or an alert

Diagnose from existing request/app logs. If a burst truly cannot be avoided, aim it at a non-production service and disclose every request you sent (count, endpoint, window) — a production probe contaminates the very window under investigation and forces others to re-attribute your traffic.

## 7. Evidence output standard

- Sanitized rows as CSV: `timestamp_utc, revision, status, endpoint, client_class, traffic_class, referer_origin, remote_ip_key, limiter_key, remote_ip_equals_limiter_key, limiter_window, limiter_endpoint` with each IP replaced by `IP-<sha256 prefix>` and campaign/user ids redacted. Keep `remoteIp` and the limiter key in **separate** columns even when they match on every row — the match is a finding, not a shortcut. Print rows, bytes and `sha256`.
- Normalize `httpRequest.requestUrl` with a URL parser first: Cloud Run stores an **absolute** URL, so comparing it to `/api/campaigns` silently buckets every row into "other".
- Never truncate `labels.instanceId` for display/grouping — two different containers can share an 8-char prefix, which fakes a single-instance claim.
- Quote the exact `gcloud logging read` filter text used, so the reader can re-run it.
- State window boundaries explicitly (`23:54:00–23:58:00Z`) and the timezone rule.
- End with a **precise missing-evidence list** (e.g. "limiter log line has no pid, so per-worker vs single counter is unresolved"), never a generalized "could be anything".

## Recipes

- Breakdown script: `scripts/status_breakdown.py` consumes the TSV produced by
  `gcloud logging read … --format='value(timestamp,httpRequest.status,httpRequest.requestUrl,httpRequest.remoteIp,httpRequest.referer,httpRequest.userAgent)'`
  and prints per-endpoint accepted/rejected, a per-minute series for one endpoint, UA classes, and writes the sanitized CSV.
- Permissions: reading needs `logging.viewer` (usually fine for a deploy SA); creating log metrics needs `logging.logMetrics.create`. If the SA is denied, re-run the same command with `--account=<user account>` rather than escalating IAM.

## Pitfalls

- Reporting a single per-minute spike from all-endpoint totals as "the bucket that failed".
- Using a revision prefix, or attributing a rollback revision's numbers to the new one.
- Calling a limiter key from `remoteIp` when the limiter's own line was available.
- Treating `429` as a server error: availability SLOs typically count 5xx, so burn-rate/uptime alerts stay silent during a 4xx rejection incident.
- Forgetting that an in-memory limiter makes limit behaviour non-deterministic across instances/workers; two identical-looking requests can differ.
- Publishing raw IPs or campaign contents in the write-up.

## References

- `references/wa-cloudrun-429-2026-10.md` — worked incident: exact log formats, counts, the retraction, and what stayed unresolved.
