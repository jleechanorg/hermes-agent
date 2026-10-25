# Worked stack — HTTP 429 coverage (log metric + storm/starvation policies + dashboard)

Built after a Cloud Run service silently rate-limited its own campaign-list endpoint for ~30 minutes with
no policy covering it. Project shape: `worldarchitecture-ai`, services `mvp-site-app-stable` / `mvp-site-app-dev`.

## 1. Gap inventory (state this, with counts)

```bash
gcloud alpha monitoring policies list --format='value(displayName,enabled)'      # 55 policies, none 4xx
gcloud logging metrics list --format='value(name)'                              # 14 metrics, none 429
gcloud monitoring dashboards list --format='value(displayName)'                 # 1 dashboard, no status/429 panel
gcloud alpha monitoring channels list --format='value(displayName,type)'        # email only
```

Availability burn-rate SLO policies count 5xx, so a 4xx rejection incident produces **zero** alerts.

## 2. Log-based metric (per service, plus a status-labelled variant)

```yaml
# gcloud logging metrics create wa_cloud_run_http_429 --config-from-file=metric.yaml
filter: |-
  logName="projects/<project>/logs/run.googleapis.com%2Frequests"
  resource.type="cloud_run_revision"
  (resource.labels.service_name="mvp-site-app-stable" OR resource.labels.service_name="mvp-site-app-dev")
  httpRequest.status=429
metricDescriptor:
  metricKind: DELTA
  valueType: INT64
  unit: "1"
  labels:
  - {key: service_name, valueType: STRING}
labelExtractors:
  service_name: EXTRACT(resource.labels.service_name)
```

Second metric for endpoint-scoped charts/alerts: same scope plus `httpRequest.requestUrl:"/api/campaigns"`,
labels `service_name` + `status` (`EXTRACT(httpRequest.status)`). `revision_name` remains a resource label, so
revision drills need no extra extractor.

## 3. Two policies per service (`--policy-from-file`)

Storm (fires on a sustained burst):

```json
{"displayName":"Sustained HTTP 429 storm - <svc>","combiner":"OR","enabled":true,
 "alertStrategy":{"autoClose":"1800s"},
 "conditions":[{"displayName":">=40 HTTP 429 in rolling 10 minutes on <svc>","conditionThreshold":{
   "filter":"metric.type=\"logging.googleapis.com/user/wa_cloud_run_http_429\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"<svc>\"",
   "comparison":"COMPARISON_GT","thresholdValue":39,"duration":"60s","trigger":{"count":1},
   "aggregations":[{"alignmentPeriod":"600s","perSeriesAligner":"ALIGN_DELTA","crossSeriesReducer":"REDUCE_SUM","groupByFields":["resource.labels.service_name"]}],
   "evaluationMissingData":"EVALUATION_MISSING_DATA_INACTIVE"}}]}
```

Starvation (fires on the quiet shape): same shape with `thresholdValue: 9`, `duration: "300s"`, filter adding
`AND metric.label."status"="429"` on the status-labelled metric. Note: `evaluationMissingData` may only be set
when `duration` is non-zero — the API rejects `duration: "0s"` + `EVALUATION_MISSING_DATA_INACTIVE`.

Attach existing channels only:

```bash
gcloud alpha monitoring policies update <policy-id> \
  --add-notification-channels=projects/<project>/notificationChannels/<channel-id>
```

## 4. Dashboard (create new, don't clobber another owner's)

Charts that actually answered the incident: campaign API requests/s by HTTP status (group by
`resource.label.service_name` + `metric.label.status`), 429/s, p95 latency (metric `run.googleapis.com/request_latencies`,
**`REDUCE_MEAN`** with `ALIGN_PERCENTILE_95`), and request volume grouped by
`resource.label.revision_name` as deploy context. Filter form that validates:

```
resource.type="cloud_run_revision" resource.label."service_name"=monitoring.regex.full_match("mvp-site-app-(stable|dev)") metric.type="logging.googleapis.com/user/wa_campaign_api_requests"
```

## 5. Readback receipt (what a reviewer accepts)

```bash
gcloud monitoring dashboards describe <id> --format=json > dashboard.json
gcloud alpha monitoring policies describe <id> --format=json > policy_<id>.json
gcloud logging metrics describe <name> --format=json > metric_<name>.json
shasum -a 256 *.json > MANIFEST.sha256
```

Cite per object: `creationRecord.mutateTime` + `mutatedBy`, `mutationRecord.mutateTime`, metric
`createTime`/`updateTime`, dashboard via audit log
(`logName:"cloudaudit.googleapis.com%2Factivity" AND protoPayload.methodName:"dashboards"` → the create event whose
`response.name` matches). Print thresholds, `duration`, `aggregations`, `notificationChannels`, `unit`.

## 6. Judgement calls that mattered

- Threshold 40/10min was picked from 6 days of the signal (median bucket 10, incident buckets 232–736).
- Email `verificationStatus` blank ⇒ delivery unproven; declined to induce a production 429 to prove it, and said so.
- Slack was a stated gap (no monitoring channel existed), not a "handled" item.
