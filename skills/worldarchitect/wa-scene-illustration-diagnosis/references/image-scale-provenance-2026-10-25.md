# Oversized figure in a prod scene image — full asset→doc→payload chain (2026-10-25)

Worked request: player posted an iOS screenshot labelled **"Rome: Gaia Julia, Scene 614"** asking why one
figure on the near boat was gigantic. Two more images (inline vs zoomed) of the same frame were supplied.
Outcome: **generated-image composition defect**, not app scaling, and **not** a missing scale instruction.

## Facts proven (sanitized)

| Item | Value |
|---|---|
| blob | `campaign_scene_illustrations/<uid>/<cid>/612-aa5718a91c.png` |
| bytes / type | 1,535,452 · PNG · 1280×720 (16:9, `resolution=1K`) |
| sha256 | `a9a4105ab74e8734f6a7357193efaf236a525699d7b1515102130397bc40b0aa` |
| Firestore | `users/<uid>/campaigns/<cid>/scene_illustrations/612` → `status=ready`, `sha256` = same, `model=x-ai/grok-imagine-image-2.0`, `cost_usd=0.05` |
| times | `requested_at 2026-10-25T00:11:12.788Z` → `ready_at 00:11:56.711Z`; BQ `ingested_at 00:11:56`; `timing_ms.total 10621` |
| caption | `"Imperial Highland Castra & Sovereign Triumph (Synergistic) - Leave Centurion Vettius …"` |
| story binding | story usn **612** (`ts 00:11:43Z`) carries `scene_illustration{usn 612, status ready}`; usn 613/614 → `scene_illustration=null` |
| BQ row | `event_type/agent` = portrait image generation, `extra.portrait_source='scene_illustration'`, `scene_illustrations_mode=after_scene`, `every_n=3` |
| prompt bytes | `request_json_source_bytes=6498`, `request_json_source_sha256=d4dd7474…` |
| deploy binding | `extra.git_commit=8e5b2ed002c0074b43534b5b5b03efda84b15aa0`, ancestor of `origin/main`; `scene_image.md` identical at that sha and at `origin/main` |
| provider pin | `{only:["xai"], sort:"latency", allow_fallbacks:false}`, `aspect_ratio=16:9`, `quality=low`, `n=1` |
| references | exactly 1 `input_references` entry = player portrait `avatar.png`, identity-only role |

Three-way hash match (doc / BQ extra / fresh download) is what makes "the screenshot shows *this* asset"
defensible. Screenshot pixels themselves cannot be hash-matched — the claim was "composition matches",
stated as such.

## Prompt analysis

- All **8/8** placeholder-free paragraphs of `mvp_site/prompts/scene_image.md`@`8e5b2ed0` appeared verbatim in
  the stored prompt → faithful render of the deployed template.
- Scale grep: **zero** hits for `giant|colossal|towering|massive|larger than life|oversized|proportion`. One
  `scale` hit, in the lighting paragraph (`scene_image.md:5`), scoped to the player character.
- `scene_image.md:7` — "do not invent changes" — was violated: the oversized figure's waving pose exists nowhere
  in the turn's GM text.
- `scene_image.md:9` — "paint the one where most of its action and dialogue happen" — had **no dominant location**:
  the turn's GM text runs mountain-gate salute → Tigris causeway with a bronze-trumpet flotilla → palace hall with
  satraps submitting. The provider collaged all three, each scaled against its own local anchor.

## Numbering discrepancy (left open)

Asset keyed `user_scene_number=612`, story entry usn 612 holds it, usn 613/614 empty — yet the photographed
client view is labelled "Scene 614". Offset +2, mechanism unread (no iOS client code inspected). Reported as an
observed mapping with "unresolved", not as a bug claim.

## Dead ends / traps hit on the way

- `collection_group("campaigns").where("name","==",…)` → `FailedPrecondition … COLLECTION_GROUP_ASC index`.
- `campaigns` field is `title`, not `name`; equality on `name` returns 0 and reads as "not found".
- `limit(300)` on a heavy account's `campaigns` subcollection truncated (300 returned, match absent).
- `~/worldarchitect.ai/.venv` lacks `google.cloud.bigquery`; used `bq` CLI. Dry-run first — the bounded
  10-day `LIKE` scan still processed ~4.97 GB.
- Local checkout was 1,662 commits behind and lacked `mvp_site/prompts/scene_image.md` entirely; every template
  read went through `git show origin/main:<path>` instead of the working tree.

## Reporting shape the user accepted

Verdict first (generated-image defect vs display), then provenance table, prompt/reference-role evidence,
labelled hypothesis for the collage, explicit "unresolved" for the scene-number offset, boundaries kept
("no generation, no turn, no config/auth change"), then Proof with exact commands + key output.
