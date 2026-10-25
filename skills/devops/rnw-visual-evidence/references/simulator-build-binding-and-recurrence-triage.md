# Simulator build binding, recurrence triage, and the jest structural lane

Worked case: `worldai_frontend` PR 248 (God Mode turn layout). A user reported the same iOS defect
twice ("still happening, Scene 364", then "again, Scene 433") while a draft PR claimed a measured
BEFORE/AFTER. The session's job was owner/handoff coordination plus independent audit without touching
the reserved device. Everything below is read-only and reusable.

## 1. Bind an already-installed build to a source head — without booting anything

`simctl listapps` needs the device **Booted** (`SimError code=405 "Unable to lookup in current state:
Shutdown"`), so it is useless for an idle device and booting is a mutation when another operator owns
the lane. Read the device's container off disk instead:

```bash
D=~/Library/Developer/CoreSimulator/Devices
for u in <UDID> …; do
  plutil -p $D/$u/device.plist | grep -E '"name"|"runtime"|"state"'   # state 1=Shutdown 3=Booted
  for app in $D/$u/data/Containers/Bundle/Application/*/*.app; do
    plutil -extract CFBundleIdentifier raw "$app/Info.plist"
    plutil -extract CFBundleVersion raw "$app/Info.plist"
    js="$app/main.jsbundle"
    [ -f "$js" ] && shasum -a 256 "$js" && stat -f%z "$js" && stat -f%Sm "$js"
  done
done
```

Then bind by **hash equality** against the evidence packet's `ARTIFACT_BINDING.txt`
(`<sha256>  <path>/main.jsbundle` + the source head it was built from). Verified: a device-tile scan
returned `edae7c0e…4514c` for the installed bundle, byte-identical to the AFTER bundle bound to the PR
head — that single comparison answered "which source does the device run" with no launch.

Two facts this produces for free:

- **An app directory with no `main.jsbundle` is a Debug shell** (Metro-dependent) and can never be a
  standalone pixel source; don't propose it as a capture target.
- A `mtime` earlier than the PR commit is **not** proof the build lacks the fix — a worker typically
  builds the AFTER tree, then commits. Only the hash-to-binding match decides it.

Idleness, same pass: `xcrun simctl list devices booted`, `pgrep -x Simulator` (exit 1 = no GUI),
`lsof -nP -iTCP -sTCP:LISTEN | grep -Ei 'metro|8081'`.

## 2. Before crediting a "still happening" report, check whether the fix is even on `main`

```bash
git fetch origin --quiet
git rev-parse --short origin/main origin/<pr-branch>
git grep -c "<new-symbol-introduced-by-the-fix>" origin/main -- <paths>   # no output ⇒ absent
gh pr view <n> --json state,isDraft,mergeable,mergeStateStatus,headRefOid
```

If the new symbol is absent from `origin/main`, **every shipped build still has the defect** and the
recurrence is expected, not a failure of the open PR. Say both SHAs and say plainly that the incident is
*unmerged*, not "completed, awaiting review". This check costs three commands and prevents arguing
evidence quality against a build that never contained the change.

## 3. "Am I still writing it?" — scope the writer check to the worktree

`ps -Ao pid,command | grep -Ei 'pil |pi --provider'` returned two live workers that belonged to a
**different** task (`…/next-scene-header-20261023`). A bare count is not an answer. Resolve the cwd /
worktree of each PID (or read the full argv) and only then claim "no competing writer". Same rule as
owner receipts: process identity must include the working directory, not just the binary name.

## 4. jest + react-test-renderer structural lane (explicitly labelled as non-pixel)

When pixels are blocked, pin invariants that decide whether the symptom *can* originate in the
component — and label the file as structural. Three traps cost real time here:

- `ReactTestInstance` has **no `.toJSON()`** (only the renderer does). Walk the instance instead:
  `const textOfInstance = n => (n?.children ?? []).map(c => typeof c === 'string' ? c : textOfInstance(c)).join('')`.
- `expect(a.parent).toBe(b.parent)` throws
  `TypeError: Method Map.prototype.entries called on incompatible receiver [object Map]`
  (react-test-renderer instances carry patched Maps). Compare **document order** from a common ancestor
  instead: `const ordered = ancestor.findAll(n => typeof n.type === 'string'); ordered.indexOf(a) < ordered.indexOf(b)`.
- Rendered markdown keeps raw decoration in the text node (`**Final movement** — …`), so assert on the
  trailing prose, not on a decorated literal.

Invariants worth pinning for an overlap complaint (all cheap, all survived review):

1. card and the next block are **flow siblings** in one column, no `position: 'absolute' | 'fixed'`
   anywhere in the boundary subtree (so the overlap must be measurement / a different parent);
2. the exact style numbers that form the gap (`marginBottom 6` + `marginVertical 15` = 21 pt);
3. the story column is `alignItems: 'stretch'` (definite width, no content circularity);
4. the sentinel/marker string is absent on the **persisted-history** path, not only the live stream;
5. the whole body reaches the card node, including its last line (containment of content).

## 5. Estimate the real card height from the style chain, then compare with the fixture that was measured

```
content_w = viewport − 2*containerPadding − 2*bubblePadding
text_w    = content_w − 2*cardBorder − 2*cardPadding
advance   ≈ fontSize * 0.602            # monospace
cpl        = floor(text_w / advance)
wrapped    = Σ max(1, ceil(len(line)/cpl))   # blank lines count 1
card_h     ≈ wrapped*lineHeight + padTop/bottom + borders + label block
```

At 393 pt with `paddingHorizontal 25`, bubble `4`, card `border 1 / padding 8`, body `16/24`:
`text_w = 317 pt`, `cpl = 32`. Real entries, same campaign:

| scene | body | wrapped | est. card | vs 852 pt viewport |
|---|---|---|---|---|
| 364 | 4,125 chars / 33 lines (nested lists indent 4, `---`, `###`) | 148 | ≈3,586 pt | ≈4.2 |
| 433 | 2,640 chars / 16 lines (nested lists indent 3) | 92 | ≈2,242 pt | ≈2.6 |

The PR's native proof used a **24-line** fixture. Always state the ratio — "the fixture is ~2.5× shorter
than the reported entry" is a substantive review finding, and it also kills any claim that a synthetic
99-line body represents the report (say the correction out loud when you swap in real data).

## 6. Read-only production entry export for a fixture

`firebase_admin` + `credentials.Certificate(...)`, then stream the story collection sorted by timestamp
and select by `user_scene_number`; normalise datetimes with `isoformat()` before serialising. Fields that
matter for layout forensics: `text`, `narrative`, `god_mode_response`, `planning_block{context,thinking,
choices}`, `entities_mentioned`, `user_scene_number`, `mode`, plus the **next doc's `mode`** (a following
`god` turn is a candidate for the "next purple summary"). Cheap shape signals to record: deepest list
indent, presence of `---`, choice count.

Keep exported production bodies in a local scratch path (`/tmp/<task>/`), never in a public evidence
bucket, and never re-publish display fields you were not asked to publish.
