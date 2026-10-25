# App Store review status — read-only verification through an existing signed-in browser

Verified 2026-10-24 on `WorldArchitect AI` (ASC app id `6823043214`) with **no ASC API key**, no
`asc` CLI, no credential entry: the only asset used was an already-signed-in Aside profile
(`aside --account u0 repl`, `jleechan@gmail.com`). Use this lane when the ask is "what is the *current*
App Store submission/review state" and the answer must be a fresh read rather than a replay of the
last thing anyone reported.

`/iris/v1/*` calls below are **same-origin GETs executed inside the authenticated page** — they
inherit the browser session, they do not need a key, and they are read-only. Never POST/PATCH here
and never print cookies or tokens.

## Route ladder (SPA text first, API second)

```js
// Aside REPL — attach to the ASC tab that is already open
const ts = await listBrowserTabs();                    // needs await
const tab = ts.find(t => /appstoreconnect\.apple\.com/.test(t.url));
const p = await attachBrowserTab(tab.targetId);
await p.goto(`https://appstoreconnect.apple.com/apps/<APP_ID>/distribution/ios/version/inflight`);
await sleep(9000);                                     // Angular needs ~6-10s
console.log(await p.evaluate(() => document.body.innerText));
```

| Page | Gives |
|---|---|
| `/apps/<id>/distribution/ios/version/inflight` | version title, status badge, attached `BUILD / VERSION` row, review-info presence |
| `/apps/<id>/appstore/reviewsubmissions` | submission history table (date, versions, submitted by, status) + "messages with Apple" area |
| click a submission row → `/distribution/reviewsubmissions/details/<submission-id>` | **Submission ID**, exact `Date Submitted`, item `1.0.0 (43)`, review status |
| `/apps/<id>/testflight/ios` | build train list (`Testing` / `Ready to Submit`, expiry, groups) — paginated, has "See More" |

Report the submission-detail page as the primary receipt: it carries the submission UUID and the
submitter identity, which the version page does not.

## Authoritative API reads (same-origin, `iris`)

```js
const r = await p.evaluate(async () => {
  const res = await fetch('/iris/v1/apps/<APP_ID>/appStoreVersions?limit=10&include=build',
                          {headers:{Accept:'application/json'}});
  return {status: res.status, j: await res.json()};
});
```

- `data[].attributes` → `appStoreState` (`WAITING_FOR_REVIEW`, `READY_FOR_SALE`, …), `releaseType`
  (`MANUAL` vs `AFTER_APPROVAL`), `createdDate`, `versionString`, `platform`.
- `relationships.build.data.id` → then `/iris/v1/builds/<build_id>` for `version` (build number),
  `processingState`, `qcState`, `uploadedDate`, `expirationDate`, `expired`,
  `buildAudienceType`, `usesNonExemptEncryption`, `deviceFamilies`, `minOsVersion`.
- `/iris/v1/builds/<build_id>/preReleaseVersion` → the **train** (`{"version":"1.0.0"}`).
- `/iris/v1/apps/<APP_ID>/reviewSubmissions?limit=5` → `{state, submittedDate, platform}` per
  submission; `WAITING_FOR_REVIEW` on the newest one is the current review verdict.

**Version string ≠ pre-release train string.** An App Store version whose `versionString` is `1.0`
can carry a build grouped under preReleaseVersion `1.0.0` — so a TestFlight list showing
`Version 1.0.0 / Build 1054, 1053, …` next to a version page reading `Build 43` is **not** a
contradiction. Resolve it with `preReleaseVersion` before writing anything that sounds like
"the submitted build is stale", and if the point matters, state both numbers explicitly: review is on
`build 43` while newer same-train builds exist unsubmitted.

## Screenshots: read the sets, not the page text

The current version page renders **no screenshots section at all** — `document.body.innerText` has
zero matches for `screenshot`, `document.images.length === 0`, and `/…/version/inflight/screenshots`
serves the same metadata page. That absence is a **UI/route fact, not a missing-asset fact**.

```js
// localizations -> appScreenshotSets, then count each set
const loc = await fetch('/iris/v1/appStoreVersions/<version_id>/appStoreVersionLocalizations'
                      + '?limit=20&include=appScreenshotSets', {headers:{Accept:'application/json'}});
// then per set id:
// /iris/v1/appScreenshotSets/<set_id>/appScreenshots?limit=20  -> data[].attributes.fileName
```

Display types seen: `APP_IPHONE_61` (6.1" iPhone), `APP_IPAD_PRO_3GEN_129` (this **is** the
12.9"/13" iPad slot — the one that was historically reported missing). Report **set + frame count +
filenames** ("iPad 13": 2 frames, both `ipad43-ready.png`") rather than "screenshots complete".
A populated set proves presence only; it does not prove per-size minimums or creative quality.

## What this lane cannot prove — say so instead of implying it

- **Embedded DEV/embedded-backend configuration.** ASC exposes no runtime-config field. A hold like
  "the binary carries a DEV config" can only be settled against the artifact / EAS profile / built
  bundle (`strings` the bundle), never from ASC. Report it as *unverified by this read*.
- **Apple Developer support cases.** `developer.apple.com/contact/recent-cases` can render
  nav + footer only (no case rows) inside an agent session; that is a page-read gap, not "no case".
  More important: **a support acknowledgment is not review clearance** — never let a case thread
  stand in for an ASC review state.
- **Anything not yet echoed by ASC after a submission** (ingestion lag; see SKILL.md §5b).

## Discipline checks before replying

1. **Re-read; never replay.** A prior state ("Prepare for Submission / build N-1 / missing iPad
   shots") is history. Quote only what this session's read returned, with the observation timestamp.
2. **`WAITING_FOR_REVIEW` + empty message area = no messages.** Say "no review messages, no
   rejection, no Developer Action Needed *as of <time>*" — do not claim Apple is silent forever.
3. **Distinguish three facts:** submission exists (`reviewSubmissions`), build is attached and
   `VALID` (`appStoreVersions.relationships.build`), and the app is *live* (`appStoreState`
   terminal + `releaseType`). `MANUAL` release means approval will not auto-publish.
4. **Holds get closed only by evidence.** "Previously missing iPad slot now has 2 frames" is a
   closure claim for the slot; "DEV config hold" stays open with the reason it is unreadable here.
5. **Read-only means read-only.** No submit / remove-from-review / cancel / release-setting change,
   even to "fix" what you find — report and let the operator decide.

## Evidence shape that satisfied the ask

Screenshots of the two pages (submission detail + version page) with `sha256`, the raw
`innerText` dumps, and a `RECEIPT.md` holding: app id, version id, build id, submission id,
`appStoreState`, `releaseType`, submitted timestamp, submitter, screenshot set counts, and an
explicit "not verifiable from ASC" list. Captions were verified against the pixels with
`vision_analyze` before publishing.
