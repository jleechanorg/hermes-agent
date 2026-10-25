# Owner/session custody receipts (who is executing, and how to reach them)

For briefs that demand "return the actual owner/session/worktree, an explicit custody
decision, and a next source-only action with original execution time" — and that warn
"GitHub author and a queued brief are not pickup".

## 1. Prove who owns a code lane (commit ↔ session ↔ process)

A branch and a commit author are **not** an owner. Establish all four:

```bash
# a. the lane's worktree and head
git -C <repo> worktree list | grep -F '<branch>'
gh pr view <n> --json number,state,headRefOid,headRefName,mergeable,updatedAt

# b. the session that produced it (pi stores one dir per cwd)
ls ~/.pi/agent/sessions/ | grep -F '<worktree-path-slug>'
#   → ~/.pi/agent/sessions/--Users-…-<worktree>--/<ts>_<session-id>.jsonl
#   last entry timestamp + file mtime = when the lane actually stopped

# c. whether anything is still executing
ps -eo pid,lstart,command | grep -E '<session-id>|pil|lunaroute' | grep -v grep

# d. codex lanes: ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<session-id>.jsonl
```

Report as: `worktree / branch @ sha / session-id / started / last entry / last commit /
live process: none`. A stopped session is a **stopped session**, not an executing
integrator; resuming it is a new paid run and needs its own authorization.

## 2. Find the agent-attached surface for a lane (cmux)

```bash
cmux current --json > /tmp/cmux_current.json      # projection: label, kind, resource_ref,
                                                  # project_hints, agents[] (kind, session_id,
                                                  # state, last_activity_at), pull_requests
cmux list-panes --workspace workspace:1000100013  # NB: needs the `workspace:` prefix;
cmux list-pane-surfaces --pane pane:1000100027    #     bare "1000100013" = "Workspace index not found"
```

`agents[]` is the reliable "is an agent attached here" signal; browser surfaces
(`kind: browser`, PR pages) carry no agent and cannot receive a brief. Map a lane to a
surface by `project_hints` **and** by which PR pages sit in the same workspace — then
confirm with the inbox (§3). In this projection `ref` is null; use the pane/surface
listings for the `surface:N` refs.

## 3. Deliver, and treat delivery as delivery only

```bash
cmux agent message surface:1000100032 --from hermes "<bounded brief>"
#   → "Queued message <uuid> for <label> (surface:N)"
cmux agent inbox --surface surface:1000100032 --state queued   # read the receipt back
```

`Queued` ≠ delivered ≠ read ≠ pickup ≠ execution. Report the uuid as a **delivery
receipt**, name the agent state and its `last_activity_at`, and say plainly that no
pickup receipt exists yet. Never upgrade a queued message into "the owner is on it".

If the exact subject has **no** agent-attached surface (only a browser surface), do not
mis-route a work order into an unrelated lane. Send a **routing check** instead — "if you
do not own <PR/sha>, reply with the surface/session that does and do not start work
outside your lane" — and report the missing route as an exact gap.

## 4. Custody decision when two PRs overlap

Two green PRs touching the same files cannot both land; one writer must own the files.
Record, in one place (PR comment + bead), all of:

- **single integration writer**: branch, head sha, worktree, session id, last activity,
  live-process status;
- **donor**: the other PR's exact head sha, branch, worktree, and the words "frozen
  source donor — no further edits; to be closed as superseded after absorption";
- **third writer: none**, with evidence (the failed dispatch's log line + exit code);
- **overlap proof**: `git diff --name-only origin/main...<shaA>` vs `...<shaB>` — the
  shared file list is why only one can land;
- **remaining-required vs not-required** changes, each tied to the writer's own findings
  file, so nobody re-litigates a gate that measurement says is not worth relaxing;
- **what the donor is worth absorbing** (usually plumbing) and what must not be
  transplanted (its predicate/reasoning), with the exact donor line numbers.

## 5. A dead dispatch leaves competing writer state — clean it before reporting

A dispatch that exits immediately (e.g. `backend unavailable`, exit 1) can still have
created a worktree **and** written a partial edit:

```bash
git -C <new-worktree> status --porcelain          # often shows M <file>
git -C <new-worktree> diff > <parent>/ABANDONED-<topic>-$(date -u +%Y%m%dT%H%M%SZ).patch
git -C <new-worktree> checkout -- <file>
```

Archive the diff, revert the tree, and report the patch path — otherwise the next lane
finds an unowned uncommitted edit and the "no third writer" claim becomes false.

## 6. Review comments are not test evidence

An independent source review (and your own line-number verification of it) proves only
what the source says. Say explicitly "no fixture/unit tests were executed for this
receipt" and quote `git show <sha>:<path>` line numbers for each finding instead.
