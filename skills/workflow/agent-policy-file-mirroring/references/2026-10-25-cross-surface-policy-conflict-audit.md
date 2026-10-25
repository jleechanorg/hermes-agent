# 2026-10-25 — cross-surface policy conflict audit (read-only)

Session class: a "are these guidelines consistent?" audit spanning **user-level policy
+ shared skills + two repo adapters**, with a follow-up scope change mid-audit
(single shared contract instead of self-contained per-repo copies). No edits were
made in the audit itself.

## Surfaces inventoried (all hashed, all read-only)

Two repos at exact published heads via `gh api contents?ref=<sha>`:

| Repo | Head | Files read |
|---|---|---|
| jleechanorg/worldarchitect.ai | `d51ae6b7…` | `AGENTS.md` (40,118 B), `CLAUDE.md` (symlink → AGENTS.md), `.github/pull_request_template.md` (11,012 B), repo-local `.claude/skills/pr-workflow-manager.md` (5,019 B), plan + design under `docs/superpowers/` |
| jleechanorg/worldai_frontend | `7d8b8cd9…` | `AGENTS.md` (7,618 B), `CLAUDE.md` (4,271 B, a real separate file), PR template (3,034 B), `.claude/skills/evidence-standards.md` (9,966 B), plan/design pointers |

Installed owners under `~/.claude/skills/<name>/SKILL.md`: draft-first-pr,
pr-workflow-manager, ready, advice, web-advice, evidence-standards, evidence-review,
pr-green-definition, code-standards — all present; full hashes in the session receipt.

## Provenance result that changed the conclusion

Parent supplied a commit (`ca4b9772ace8f5bcae7edd76e173bcbe02a2bc1b`, PR #561) and
claimed a version of `pr-workflow-manager` with specific defects. Instead of trusting
that, hash-compare three ways:

```bash
gh api "repos/jleechanorg/jleechan-skills/contents/.claude/skills/pr-workflow-manager/SKILL.md?ref=ca4b9772" \
  -H "Accept: application/vnd.github.raw" | shasum -a 256
shasum -a 256 ~/.claude/skills/pr-workflow-manager/SKILL.md
shasum -a 256 ~/projects/jleechan-skills/.claude/skills/pr-workflow-manager/SKILL.md
```

All three `ef7b3fa3…` — the criticized version **was** the installed one, so the
defects were real and live. The same check on `draft-first-pr` (`3d24ce27…`) held too.
This is the step that turns "parent says" into evidence.

## The grep pitfall (cost one wrong finding)

Reported "no hard-reset text" after searching `hard reset`. The file actually says:

- `:105` `3. **Reset to the correct branch**: git reset --hard origin/<actual-branch-name>`
- `:116` `git reset --hard origin/claude/byok-settings-feature-0WgQP`
- `:74` squash recipe → `git push --force-with-lease`
- `:60` advertises `git push --force-with-lease safety`

Prose search missed all of it. Token search (`reset --hard|--force`) found it instantly.
**Correct the finding out loud when the user catches it; do not quietly re-state it.**

## Conflict classes that generalized

1. **Self-contained copies vs one normative owner.** A dated design doc declared itself
   the single normative owner while capping the shared router at ≤12 lines and forbidding
   copied rules — which forbids exactly what a later "make it self-contained" request asks
   for. Reassign the ownership sentence before editing anything else.
2. **Strict same-head verdict language vs reasoned delta tolerance.** One skill said
   verdicts are "verified at the same current HEAD SHA" and "none carry forward", and
   ~40 lines later said a delta that leaves claims intact needs no fresh run. Promoting
   that file to a single contract propagates the ambiguity; add one precedence clause,
   don't add a gate.
3. **A same-named installed skill vs repo-local skill** (`pr-workflow-manager`): legacy
   installed version had no "draft" mention at all and a `gh pr create` without `--draft`
   in four places; the repo-local one had `--draft`. Resolve by path.
4. **Interface entrypoints that don't exist.** A `/pr-workflow` command was assumed; no
   such command exists in any commands dir, and the public 404 was a path mismatch
   (`.claude/skills/pr-workflow-manager/SKILL.md` is the real path). Check the four roots
   (`~/.claude`, `~/.codex`, `~/.agents`, `~/.hermes`) and the symlink targets before
   concluding absence.

## User-level authority, verified

- Authoritative path: `/Users/jleechan/.codex/AGENTS.md`, regular file (not a symlink),
  60,992 B, sha256 `cb889f79…`; it self-declares as canonical and is imported by
  `~/.claude/CLAUDE.md:6` via `@~/.codex/AGENTS.md`.
- `~/AGENTS.md` and `~/.claude/AGENTS.md` are **absent**, and the policy itself says
  "Do not create or rely on `~/AGENTS.md`" — so "user-level AGENTS" unambiguously means
  the `.codex` file.
- `~/.codex` is **not** a git checkout; no tracked binding for the deployed file.
- Only tracked global-policy copy: `jleechan-skills:md_files/AGENTS.shared.md`,
  47,543 B, sha256 `14661ff7…`, last commit `453ff2fa` (2026-10-17), unchanged at
  `ca4b9772`. It is 13,449 B smaller than deployed and **contradicts it on merge
  authority**: tracked says "never merge without explicit approval"; deployed says
  "≤150 production delta lines may merge without human approval once /advice approves".
- Section delta at audit time: 8 sections only in deployed (destructive-path guard,
  size-tiered merge safety, native build authority, etc.), 2 only in tracked
  (explicit-approval merge safety, downstream repo pointers).

## Attachments in the thread

`policy-audit-receipt.json` (7,007 B) carries every path/hash/size plus the read window;
also delivered `run-receipt.json` + `manifest.json` for a separate single-review run.
Receipt shape worth reusing: `{schema, audit_utc, subject{repo,head,base}, method,
repo_files[], installed_skills[], global_rules[], notes[]}`.
