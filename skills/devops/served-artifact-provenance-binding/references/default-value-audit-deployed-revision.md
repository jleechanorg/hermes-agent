# "The default is still wrong" — audit the deployed resolver, not main

Class of report: *"Scene illustrations is still Off by default and I made a new account"*, *"new users
still get the old setting"*, *"the toggle defaults the wrong way"*. The code on `origin/main` is
usually already correct; the served code is not. Answering from main produces a confident wrong
verdict, and peer agents doing a "source audit" of main will all agree with each other and with the
wrong answer.

## Worked example (2026-10-24, WorldAI iOS app)

Report: two separate accounts (one brand new) show **Scene illustrations: Off** in the app's
Settings → Display.

What peers concluded from source alone: "current frontend and backend default a missing preference
to After; no account-creation write sets Off" — true of `origin/main`, irrelevant to the running app.

What was actually served:

```bash
# 1. Which backend does the app talk to?
grep -rn "mvp-site-app-stable" src/constants.ts        # RELEASE_BACKEND_URL = .../mvp-site-app-stable-...
# 2. What commit is that service running?
gcloud run services describe mvp-site-app-stable --region us-central1 \
  --project worldarchitecture-ai --format='value(spec.template.spec.containers[0].image)'
#   -> gcr.io/worldarchitecture-ai/mvp-site-app:stable-4b0fb1d      (commit 4b0fb1d, 2026-10-20)
gcloud run revisions list --service mvp-site-app-stable --region us-central1 \
  --project worldarchitecture-ai --limit 2 --format='value(metadata.name,metadata.creationTimestamp)'
# 3. What does THAT commit do with a missing preference?
git show 4b0fb1d:mvp_site/scene_illustration_policy.py | sed -n '83,93p'
#   def resolve_scene_illustrations_mode(...)  """... (default off). ..."""
#       return constants.SCENE_ILLUSTRATIONS_MODE_OFF      # <- served default
git show origin/main:mvp_site/scene_illustration_policy.py | sed -n '92,110p'
#       return constants.SCENE_ILLUSTRATIONS_MODE_AFTER_SCENE
# 4. Is the fix commit even an ancestor of the deployed one?
git merge-base --is-ancestor 8bcf88db77 4b0fb1d && echo HAS || echo PREDATES   # -> PREDATES
```

The `GET /api/settings` shape followed from the same SHA: for a user with no settings doc, defaults
are built without any `scene_illustrations_*` key, then `normalize_scene_illustrations_settings()`
writes `scene_illustrations_mode = resolve(...)` into the payload — so at `4b0fb1d` every
preference-less account is *served* `"off"`. No storage read, no account mutation, no auth-store
inspection needed: source-at-SHA is deterministic for this class.

Root cause = deploy lag (prod last deployed 2026-10-20 15:46 PT; fix merged 2026-10-21 01:17 PT),
not a client bug, not a per-account write.

## Per-env matrix — always print it before proposing a promotion

```bash
for s in mvp-site-app-stable mvp-site-app-staging mvp-site-app-dev; do
  echo -n "$s: "
  gcloud run services describe $s --region us-central1 --project <p> \
    --format='value(spec.template.spec.containers[0].image)'
done
# containment without a local fetch of the tag's commit:
gh api repos/<o>/<r>/compare/<fix-sha>...<env-sha> \
  --jq '.status+" ahead="+(.ahead_by|tostring)+" behind="+(.behind_by|tostring)'
gh api repos/<o>/<r>/compare/<env-sha>...main --jq '.status'      # identical == safe promote source
```

Result that changed the recommendation:

| env | tag | vs main | carries fix |
|---|---|---|---|
| stable/prod | `stable-4b0fb1d` | 840 behind | no |
| dev | `dev-68aaa40` | **identical** | yes |
| staging | `staging-7698934` (Aug 31) | diverged, ~2980 behind | no |

`deploy-production.yml` here is `workflow_dispatch` only and its `deploy_source` input **defaults to
`staging`** — following that default would have shipped two-month-old code. Recommend
`deploy_source=main` (or the env that compares `identical`), never the default blindly.

## Rules that generalize

1. Bug reports about a *default* are environment reports until the served SHA says otherwise.
2. Bind three legs: client endpoint constant → service image tag → commit, then read source at that
   commit. Missing any leg leaves the claim "unverified".
3. Two independent identities reproducing it ⇒ environment, not account state. Stop hypothesising a
   stored-vs-missing preference split; it cannot be the cause of a cross-account default.
4. Never "diagnose" a default by toggling/saving it — that destroys the missing-vs-explicitly-set
   distinction you still need after the deploy (post-deploy, missing ⇒ new default, explicit ⇒ Off).
5. An old client build is not the explanation when the server is authoritative: the client renders
   whatever `mode` the response carries, so a stale backend dominates a stale app.
6. Close the loop with the deploy approval boundary spelled out (prod deploy is a human gate) and a
   one-line verification: new revision + `GET /api/settings` on a preference-less account returns
   the new default.
