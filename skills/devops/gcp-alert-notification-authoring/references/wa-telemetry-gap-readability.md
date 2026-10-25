# Worked case — WA "Telemetry Gap Detected" P1 notification (2026-10-24)

Session: user forwarded a phone screenshot of a GCP alert email, said "fix this it's not very clear", and a second participant added the acceptance bar (plain-language DEV headline, real count not a rate conversion, impact-unknown wording, Pacific time, firing/recovered state, investigation link, no second writer, don't present the screenshot as still-firing).

## What was actually live

- Project `worldarchitecture-ai`, policy `projects/worldarchitecture-ai/alertPolicies/916760069701027746` — `[P1] Serious User Incident - Telemetry Gap Detected`, condition `Telemetry Incompleteness (starts without terminal outcomes > 0 over 15m)`, `severity: None`, `userLabels {severity: p1, component: telemetry}`, channel `notificationChannels/691298353009533813` (email only). Repo copy matched byte-for-byte (`monitoring/serious_user_incidents/policies/policy_telemetry_health.yaml`).
- Metric `logging.googleapis.com/user/serious_user_telemetry_gap_count` = log-based **DELTA / INT64**, filter `jsonPayload.event_type="serious_user_journey_phase" AND jsonPayload.issue_code="STREAM_NEVER_TERMINAL"`, label extractors `environment`, `incident_family`.
- Aggregation in the policy: `alignmentPeriod: 900s`, `perSeriesAligner: ALIGN_RATE`, `crossSeriesReducer: REDUCE_SUM`, `thresholdValue: 0`, `duration: 900s`.

## The decimal, decoded (no guessing)

| Window end (UTC) | ALIGN_RATE value | ALIGN_DELTA value |
|---|---|---|
| 04:15 | 0.0011111111111111111 | 1 |
| 04:30 | 0.0022222222222222222 | 2 |
| 05:15 | 0.0011111111111111111 | 1 |
| 05:30 | 0.0011111111111111111 | 1 |
| 06:05 | 0.0011111111111111111 | 1 |
| 06:50 | — | 2 |

`0.0011111 × 900 = 1` exactly. The rate view of a DELTA counter was the entire source of "tiny decimal looks like a fraction of a user".

Raw findings in Cloud Logging (`--freshness=6h`): `environment=dev`, `bounded_context.deadline_exceeded=True`, `stage=received`, `outcome=failed`, revisions `mvp-site-app-dev-*`. One event per distinct affected journey per reconciliation cycle (`mvp_site/incident_gap_reconciliation.py`, `DEFAULT_JOURNEY_DEADLINE_SECONDS = 300`, `root_cause_route=UNDER_INSTRUMENTED`, no causal evidence by construction).

## Firing history (why the screenshot was not "still firing")

`gog gmail thread show 1a16c5e78b9d9aa9` — message 1 FIRE at `Fri, 23 Oct 2026 22:24:52 -0700` (= 05:24:52Z) with value `0.0011111`; message 2 RESOLVED at `22:39:43 -0700` (= 05:39:43Z), `duration: 14 mins 50 secs`, value `0`. Recurring 1–3×/day since at least Oct 22 with the same subject. Because `duration: 900s` needs value > 0 across consecutive 900s windows, isolated single-window findings (05:55, 06:45) do not re-page.

## What shipped

Branch `fix/telemetry-gap-alert-readability` off `origin/main` in a fresh worktree; one commit; PR https://github.com/jleechanorg/worldarchitect.ai/pull/10836 (non-prod +40/−3, prod +0/−0). Changes in one file plus one test:

1. condition `displayName` → `DEV: some started requests have no recorded completion (>0 in 15m)` (this is the subject line).
2. `ALIGN_RATE` → `ALIGN_DELTA` (trigger semantics untouched: same filter, threshold `>0`, `900s` alignment, `900s` duration, `REDUCE_SUM`).
3. `severity: ERROR` (was unset → "No severity"; P0 family keeps CRITICAL). Verified the enum exists in the v3 discovery doc before using it.
4. `documentation.content` rewritten as markdown: DEV headline, "missing completion evidence, not a confirmed failed turn", affected count = gap findings over the 900s window and *not* failed users/turns (a stuck journey can be re-reported), `User impact: UNVERIFIED`, UTC→Pacific offset rule, `[ALERT …]` vs `[RESOLVED …]` state, Logs Explorer query, and a Technical details line with metric/condition/threshold.

Test added in `monitoring/serious_user_incidents/tests/test_deploy_plan.py`: asserts the `DEV: ` headline prefix, `ALIGN_DELTA`, `UNVERIFIED` + `gap findings` + `STREAM_NEVER_TERMINAL` in the doc, and `severity == ERROR` with `userLabels.severity == p1`. Existing test `test_p1_gap_policy_pages_only_the_dev_environment` already pinned the `environment = "dev"` filter — do not loosen it.

Verification actually run (by the parent session, not the worker's self-report):
`python3 -m pytest monitoring/serious_user_incidents/tests/test_deploy_plan.py -q` → `65 passed, 7 subtests passed in 91.63s`.

## Not done, deliberately

- Live policy not applied (`deploy.sh --apply --notification-channel=projects/worldarchitecture-ai/notificationChannels/691298353009533813` pending repo `MERGE APPROVED`). Until then the old confusing email keeps arriving.
- Trigger tuning (should one 900s window page at all?) kept out of the readability PR.
- The named writer/lane "Alerts218" referenced by the other participant did not exist on this host: `ao session ls` → "AO daemon is not running", cmux `alerts` workspace held only `worktree_p0_metrics`, and no branch/bead/worktree/cron matched. Reported that absence with the sweep evidence instead of fabricating a handoff or starting a second writer.
