---
name: gcp-alert-notification-authoring
description: Fix unclear GCP alert emails at the policy source.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [gcp, cloud-monitoring, alerting, observability, notifications]
    related_skills: [gcp-alert-historical-delivery-check, monitor-predicate-red-green]
---

# GCP alert notification authoring

## When to Use

Use when the user forwards an alert email/screenshot and says it "is not clear", the severity looks wrong ("No severity" beside a P1 title), the reported value is an opaque decimal, or the body claims more than the evidence supports. The deliverable is **the policy's own notification text**, not an explanation of it in chat.

## 1. Locate the canonical owner — never write the message twice

- Find the policy YAML in the repo (`grep -rl "<metric name>" .`, `grep -rln "Telemetry Gap" .`). For `jleechanorg/worldarchitect.ai` it is `monitoring/serious_user_incidents/policies/*.yaml`; there is no Terraform for these policies.
- Read the **live** policy and diff it against the file before assuming they match:
  `gcloud auth print-access-token` then `GET https://monitoring.googleapis.com/v3/projects/{project}/alertPolicies?pageSize=400`.
  Compare `displayName`, `conditions[].conditionThreshold.aggregations`, `documentation.content`, `severity`, `userLabels`, `notificationChannels`.
- `deploy.sh` upserts **by policy `displayName`**. Renaming the policy creates a duplicate policy; rename the *condition* instead.
- One writer: edit the single owner file and ship one PR. Do not start a parallel "message" file or a second agent lane for the same policy.

## 2. Message anatomy (what the reader actually sees)

| Rendered field | Source |
|---|---|
| Email subject | **condition `displayName`** (`[ALERT - <severity>] <condition displayName> on <project> <resource> labels {...}`) |
| Severity badge / `"No severity"` | `AlertPolicy.severity` (`CRITICAL|ERROR|WARNING`); unset prints "No severity" **even when `userLabels.severity: p1` exists** |
| Body paragraph | `documentation.content` (markdown, rendered verbatim) |
| `value of X` | the condition's aggregation result — the thing users misread as a user count |
| links | auto-generated (incident, logs); a hand-written Logs Explorer query string in the doc is the reliable direct pointer |

Verify enum/field support from the discovery doc instead of guessing:
`curl -s "https://monitoring.googleapis.com/\$discovery/rest?version=v3"` → `schemas.AlertPolicy.properties`.

## 3. Fixing an opaque decimal

A value like `0.0011111` is almost always `ALIGN_RATE` on a DELTA/INT64 counter: `1 / 900s`. Confirm from the metric descriptor (`gcloud logging metrics describe <name>` → `metricKind: DELTA`, `valueType: INT64`) and from the arithmetic (`0.0022222` for 2 events).

- Switch that aggregation to `ALIGN_DELTA`, keeping `alignmentPeriod`, `thresholdValue`, `duration`, filter and reducer identical. Same firing decision, integer count in the notification.
- Prove equivalence by querying the same window twice and showing both results:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOKEN" --get \
  "https://monitoring.googleapis.com/v3/projects/$PROJECT/timeSeries" \
  --data-urlencode 'filter=metric.type="logging.googleapis.com/user/<metric>"' \
  --data-urlencode 'interval.startTime=<ISO>' --data-urlencode 'interval.endTime=<ISO>' \
  --data-urlencode 'aggregation.alignmentPeriod=900s' \
  --data-urlencode 'aggregation.perSeriesAligner=ALIGN_RATE' --data-urlencode 'aggregation.crossSeriesReducer=REDUCE_SUM'
# repeat with ALIGN_DELTA -> int64Value 1, 2 ...
```

## 4. Documentation content: what it cannot do

`documentation.content` does **not** support a live value/count variable. Supported substitutions (from `cloud.google.com/monitoring/alerts/doc-variables`): `${policy.name}`, `${condition.name}`, `${metric.type}`, `${metric.display_name}`, `${metric.label.X}`, `${metric_or_resource.labels.X}`, `${resource.type}`, `${resource.label.X}`, `${resource.project}`.

Consequences:
- Get the count into the message through the aligner (§3), not the doc text.
- Prefer literal text over template variables you cannot render-test; a hardcoded value pinned by the policy filter (e.g. `environment="dev"`) is safer than a substitution.
- Compute nothing temporal in the doc. Say the start time is UTC and give the Pacific offset rule instead of pretending to render local time.

## 5. Impact honesty (the part reviewers care about)

Every alert body should answer: what happened, how many, over what window, is user impact **known or unverified**, when (which timezone), firing or recovered, where to look next.

- If the emitter records `root_cause_route=UNDER_INSTRUMENTED` (or the finding is "no completion observed"), write **no recorded completion** and **impact UNVERIFIED**. Never upgrade a telemetry gap into "failed users" or "critical journey failed".
- State what the number counts. A DELTA counter keyed per distinct journey still re-emits for a journey that stays stuck, so it is *findings in the window*, not unique users.
- Say the state semantics explicitly: subject prefix `[ALERT ...]` = firing, `[RESOLVED ...]` = recovered, duration on the recovery message. This lets a static body stay truthful across both emails.
- Keep the raw metric name, condition name and threshold under a "Technical details" line.

## 6. Verification and deployment

- Repo tests: policy YAML assertions live in `monitoring/serious_user_incidents/tests/test_deploy_plan.py`. Add a focused assertion for every readability invariant you claim (condition headline prefix, aligner, `severity`, doc keywords) and run the file, not the world:
  `python3 -m pytest monitoring/serious_user_incidents/tests/test_deploy_plan.py -q`
- **YAML edited ≠ notification changed.** Until `./monitoring/serious_user_incidents/deploy.sh --apply --notification-channel=projects/{p}/notificationChannels/{id}` runs, the old message keeps arriving. `deploy.sh` passes the whole parsed YAML dict to `gcloud monitoring policies create|update --policy-from-file`, so new top-level fields such as `severity` reach the API unchanged — no script change needed.
- Applying is a prod-project mutation: gate it behind the repo's merge approval and report the exact command; do not silently apply while claiming "fixed".
- Cross-check the rendered reality in Gmail (`gog gmail search "from:alerting-noreply@google.com after:<date>"`, then `gog gmail thread show <id>`) — FIRE and RESOLVED are two messages in one thread; quote the real fire/recover timestamps.

## 7. Authoring a *new* alert stack (no policy exists yet)

Same ownership discipline as §1, plus rules learned from building coverage after a silent 429 incident:

- **Prove the gap first.** Inventory what exists (`gcloud alpha monitoring policies list`, `gcloud logging metrics list`, `gcloud monitoring dashboards list`, `gcloud alpha monitoring channels list`) and state the absence with counts, e.g. "55 policies / 14 log metrics, none matching `httpRequest.status=429`". "No alert fired" is not evidence that none exists.
- **Calibrate from a real corpus, not a guess.** Pull N days of the would-be signal and print the bucket distribution (median and maxima). Pick a threshold between baseline and observed incident scale, and put that provenance into `documentation.content`.
- **One signal is rarely enough.** Pair a *storm* threshold (large counts, short duration) with a *starvation* threshold (small counts held for minutes). Hourly-cap exhaustion produces 429s at 5–20/min, which a storm-only threshold misses entirely; starvation is the shape users experience as an empty list.
- **Chart units must match the aggregation.** `ALIGN_PERCENTILE_95` with `crossSeriesReducer: REDUCE_SUM` sums per-series p95s and silently mislabels the chart; use `REDUCE_MEAN` or drop the cross-series reducer, and label the axis.
- **Revision labels for free.** Log-based metrics expose `revision_name` as a *resource* label, so revision-scoped queries/charts work without adding a metric label; service-scoped policy filters then cover future revisions with no re-pin.
- **Attach only channels that already exist.** Follow the repo's `monitoring/<stack>/deploy.sh` convention (dry-run default, upsert by displayName, `--add-notification-channels` to an existing channel). Never create a channel or webhook/OAuth credential to make an alert "complete"; if the only channel is email, report the Slack path as a gap needing an owner decision.
- **Readback receipts, hashed.** Save `describe --format=json` for every created object, print `sha256` + byte size, and cite API-reported `creationRecord.mutateTime` / `mutationRecord.mutateTime` (policies), `createTime`/`updateTime` (log metrics), and the audit-log `CreateDashboard` timestamp (dashboards expose none of their own). Include exact filters and units so a reviewer can verify env separation and labels.
- **Delivery is unproven until a real notification lands.** Blank email `verificationStatus` plus "we didn't want to generate traffic" means report `delivery unproven`; a correct-looking readback is not delivery.

## Pitfalls

- Paraphrasing the alert in chat instead of editing the policy — the confusion returns on the next fire.
- Assuming the policy `displayName` drives the subject. It does not; the condition name does.
- Treating the decimal as a fractional user count, or reporting "~0 users" from it.
- Editing the live policy by hand in the console: it drifts from the repo and the next `--apply` reverts it.
- Declaring an incident still firing because a screenshot showed "Alert firing" — check the email thread and the metric; those occurrences usually recover within minutes.
- Renaming the policy `displayName` (duplicate policy) or dropping the dev/preview `environment` filter while "cleaning up" the message.
- Binding work to a named lane/writer you cannot find: sweep AO/cmux/worktrees/branches/beads first and report the absence with evidence instead of inventing a handoff.

## References

- `references/wa-telemetry-gap-readability.md` — worked WA case: exact policy, metric semantics, before/after wording, PR shape, verification output.
- `references/rate-limit-alert-stack.md` — worked stack-from-zero case: log metric YAML, storm + starvation policy JSON, dashboard chart filters, hashed readback receipt.

Related (user-owned, do not edit): `gcp-alert-historical-delivery-check` covers *historical fire/recovery delivery* verification for an incident ID; this skill covers *authoring* the notification that gets delivered.
