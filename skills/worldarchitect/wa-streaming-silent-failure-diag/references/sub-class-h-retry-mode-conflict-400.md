# Sub-class H — Retry returns HTTP 400 `mode_conflict` on a turn that already committed

Verified 2026-10-24. Campaign `ZRj2cblbfGr5C19xO3wW` ("Rome: Gaia Julia"), client `WorldAI/1054 CFNetwork/Darwin`
(the shipped iOS app, not the retired `packages/mobile` RNW package), service `mvp-site-app-stable`
(production), revision `mvp-site-app-stable-od461c066-6ad7f18e`, commit `4b0fb1d787fb`.

## User-visible symptom

Screenshot of an ordinary **Act** turn in Scene 599 with a red box:

```
Stream HTTP 400
Connection lost. Please check your settings.
```

User words: *"Check gcp logs I retried a fe times then eventually got this. I think retry should just reload
refetch the campaign?"* — the user's read is correct: the turn was already saved and Retry must not regenerate.

The client copy is the iOS app's generic 4xx banner (`packages/mobile/src/services/mvpSiteClient.ts:2486`
builds `Stream HTTP ${response.status}`; `GameScreen.tsx` maps it to "Connection lost. Please check your
settings."). It is **not** evidence of a lost connection and **not** a settings problem.

## Timeline (all re-derivable)

| ts (UTC) | what |
|---|---|
| 08:54:02.829 | POST `/api/campaigns/<cid>/interaction/stream` → **200**, 45.84 s, 395,629 B |
| 08:54:47.527 | receipt `rid_mvm5wpm7_c4jtpohe318iq4mage64` created, `mode='dialog_heavy'`, `state_persisted=True`, `turn_number=391` |
| 08:54:48.540 | `Persisted atomic turn … 1 user chunks (['turn_rid_mvm5wpm7_…_user']), 1 ai chunks` |
| 08:55:01.828 | POST same rid → **400**, 0.105 s, 1,247 B |
| 08:55:03.675 | POST same rid → **400**, 0.102 s |
| 08:55:04.993 | POST same rid → **400**, 0.112 s |
| 08:56:39.592 | POST → 200, 21.29 s — **new** receipt `rid_mvm602ky_…`, `mode='god'`, input "is this too easy?" |
| 08:58:20.384 | POST → 200, 20.33 s — **new** receipt `rid_mvm628cp_…`, `mode='god'`, input "level 18 arcane co-leader…" |
| 09:00:54.468 | receipt `rid_mvm64ijb_…`, `mode='god'`, `state_persisted=True` |

Sibling WARNING ~100 ms after each 400 (same `campaign_id=` filter):

```
admit_turn_request: idempotency key collision with conflicting mode
(existing_mode=dialog_heavy, requested_mode=character, key=rid_mvm5wpm7_c4jtpohe318iq4mage64)
```

Read: the ordinary 'character'-mode Act turn was routed to `DialogHeavyAgent`; the receipt recorded the
**post-routing agent mode**; the 3 Retrys re-POSTed the same request id with `mode=character` and were
rejected at admission. Nothing was generated and nothing was lost on the retry leg. The two later 200s are
**new** God-mode questions, not duplicates of the Consolidate action.

## Mechanism (deployed `4b0fb1d787fb`, 2026-10-20)

1. `mvp_site/llm_parser.py:4287` — `persist_turn_atomic(… mode=agent_mode_used or mode, …)`, **no
   `receipt_mode=` argument** on this revision.
2. `mvp_site/firestore_service.py:_stage_atomic_turn_receipt` — receipt payload `"mode": request.mode`
   (so the receipt stores the agent mode; `receipt_mode` exists as a *parameter* on this revision but the
   write site never consults it).
3. `mvp_site/turn_idempotency.py:admit_turn_request` — compares `receipt["mode"]` against
   `resolve_effective_turn_mode(user_input, mode)`, whose allowed set is
   `{character, god, think, combat, info, faction, character_creation, level_up, dialog, spicy}` and which
   defaults to `character`. It can never return `dialog_heavy`, `story`, `rewards`, or `campaign_upgrade`
   → mismatch → `AdmissionStatus.MODE_CONFLICT` → `status_code=400` (fail-closed).

Consequence: **REPLAY is unreachable** for any turn whose committed agent mode is outside the turn-mode
vocabulary. Retrying such a turn is a deterministic 400, forever, for that request id.

## Fix (already merged, not deployed)

`a7953160e765` — *"fix: preserve admitted mode in turn receipts"*

- streaming persist call gains `receipt_mode=mode` (the admitted **turn** mode);
- `_stage_atomic_turn_receipt` writes `"mode": request.receipt_mode if request.receipt_mode is not None else request.mode`;
- `persist_turn_atomic(..., receipt_mode=…)` threads it to the write plan.

With it, the same-id retry matches the receipt, admission returns `REPLAY`, and the client receives the
already-saved turn instead of a 400. **Deploying `origin/main` (or cherry-picking `a7953160`) to `-stable`
is the remedy**; no client change can make a same-id retry succeed before that ships.

Client-side follow-up (not the root cause): on 4xx, look up the request disposition / refetch campaign
history before resending — the 3× resend loop cannot help.

Rarity on `-stable`, 7-day sweep: **5** rejections — 3 × `dialog_heavy`→`character`, 2 × `rewards`→`character`.

## Verification recipe

```bash
export GOOGLE_CLOUD_PROJECT=worldarchitecture-ai; unset PYTHONPATH

# 1) The 400s and their latency/size signature (latency ~0.1s ⇒ admission rejection, no LLM work)
gcloud logging read 'resource.type="cloud_run_revision"
  AND resource.labels.service_name="mvp-site-app-stable"
  AND httpRequest.status=400' --project=worldarchitecture-ai --limit=25 --freshness=6h \
  --format='value(timestamp,httpRequest.status,httpRequest.latency,httpRequest.userAgent,httpRequest.responseSize)'

# 2) The sibling WARNING with the exact mode pair (~100 ms after each 400)
gcloud logging read 'resource.type="cloud_run_revision"
  AND resource.labels.service_name="mvp-site-app-stable"
  AND timestamp>="2026-10-24T08:54:00Z" AND timestamp<="2026-10-24T08:56:00Z"
  AND severity>=WARNING' --project=worldarchitecture-ai --limit=60 --freshness=6h \
  --format='value(timestamp,jsonPayload.message)'

# 3) Frequency / affected mode pairs over 7d
gcloud logging read 'resource.type="cloud_run_revision"
  AND jsonPayload.message:"idempotency key collision with conflicting mode"' \
  --project=worldarchitecture-ai --limit=2000 --freshness=7d \
  --format='value(timestamp,resource.labels.service_name,jsonPayload.message)'
```

Commit-vs-not proof (Firestore, read-only; GAC + `./vpython` from the project root):

```python
from google.cloud import firestore
db = firestore.Client(project="worldarchitecture-ai")
camp = (db.collection("users").document(UID)
          .collection("campaigns").document(CID))
for doc in camp.collection("turn_receipts").order_by(
        "created_at", direction=firestore.Query.DESCENDING).limit(6).stream():
    d = doc.to_dict() or {}
    print(doc.id, d.get("mode"), d.get("state_persisted"), d.get("turn_number"),
          d.get("created_at"), d.get("user_entry_ids"))
for doc in camp.collection("story").order_by(
        "timestamp", direction=firestore.Query.DESCENDING).limit(8).stream():
    d = doc.to_dict() or {}
    print(doc.id, d.get("timestamp"), str(d.get("text") or "")[:180])
```

Deployed-vs-main check (the step that turns "already fixed" into "fixed but not shipped"):

```bash
sha=$(gcloud logging read 'resource.type="cloud_run_revision"
      AND resource.labels.service_name="mvp-site-app-stable"' --project=worldarchitecture-ai \
      --limit=1 --freshness=1h --format='value(labels."commit-sha-full")')
git show "$sha:mvp_site/llm_parser.py" | grep -n "receipt_mode=" ; echo "exit=$?  # no match ⇒ pre-fix"
git log --oneline -S'"mode": request.receipt_mode' origin/main -- mvp_site/firestore_service.py
git merge-base --is-ancestor a7953160 "$sha" && echo deployed || echo "NOT deployed"
```

## Pitfalls

- **A 400 is not "connection lost" and is not proof the turn failed.** `latency ≈ 0.1 s` + `~1.2 KB` body
  means rejection at admission, before any LLM work. Then read `turn_receipts/<rid>`: `state_persisted=True`
  proves the earlier attempt committed.
- **Never resubmit to "prove" the loss.** Pre-fix a same-id retry can only 400 again; post-fix it replays the
  saved turn. Diagnosis is three read-only reads (access log, sibling WARNING, receipt).
- **Do not infer duplicates from the retry count.** Distinct `rid_…` prefixes in `turn_receipts` are distinct
  committed turns; read the `story` subcollection user entries to see what each contained before claiming a
  duplicate.
- **`campaigns/<cid>` has NO `story_history` array.** `doc.to_dict().get("story_history")` returns absent/`[]`
  and reads as "no entries". Entries live in subcollections: `story`, `story_snapshots`, `game_states`,
  `turn_receipts`, `scene_illustrations`, `reward_events`, `world_sim_timeline`.
- **`receipt_mode` existing in the signature does not mean it is used.** On `4b0fb1d` the parameter exists but
  the payload still writes `request.mode`; grep the *write site*, not the parameter list.
- **The screenshot clock places the attempt; the log proves the outcome.** Screenshot said 1:55 → `08:55Z`;
  bind the window from the displayed clock, then cite timestamp + endpoint + status + latency + `userAgent`.

## Related

- Bead `rev-en0xiv` (worldarchitect.ai) — filed from this diagnosis with the full evidence chain.
- Sub-class F (mobile client stream loss) is the *upstream* trigger in this class of report: the server
  completes the turn, the app declares the loss, the user taps Retry. Read F first, then H for the retry leg.
