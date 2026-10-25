# Two-phase style proof on the standalone RN/Expo frontend (`worldai_frontend`)

The same "it used to be purple" report can land on **two different surfaces**:
`mvp_site/frontend_v1` (legacy web, jsdom-able — see the main SKILL.md recipe) and the standalone
Expo/React-Native app in `jleechanorg/worldai_frontend`. A legacy-web measurement does **not** close
the RN/iOS question. Check the named surface before generalising.

## 0. Bind to the true tip — a "verified main" is not the tip

```bash
git fetch -q origin main
git rev-parse refs/remotes/origin/main                 # local ref
gh api repos/<owner>/<repo>/git/ref/heads/main --jq '.object.sha'   # authoritative
```

When someone names a SHA as "verified delivery main", prove its relation instead of accepting it:

```bash
git merge-base --is-ancestor <claimed> refs/remotes/origin/main && echo ancestor
git rev-list --count <claimed>..refs/remotes/origin/main     # distance
git log -1 --format='%H %ad %s' <claimed>
git tag --contains <claimed> | head -3                       # e.g. ios-build-number/NNN
```

A claimed baseline can be a recent delivery **tag** that main is already 2 commits ahead of — accurate
as a delivery receipt, wrong as "current main". State both numbers; keep an earlier measurement as
historical rather than re-labelling it.

Big-repo worktrees: `git worktree add --detach ~/.worktrees/<repo>/<lane> <sha>` can exceed a 600 s
foreground timeout on 900+ file checkouts — run it with `background=true`, then
`ln -sfn <main-checkout>/node_modules <worktree>/node_modules` instead of installing. Remove the
worktree (`git worktree remove --force`) when done.

## 1. Read the phase contract before believing a regression

```bash
grep -n "<field>" src/state/gameStore.ts      # where is it assigned?
grep -n "<field>" src/components/<Bubble>.tsx # where is it read?
```

If the field is written only in `APPLY_DONE` and never in `APPLY_CHUNK`, the styled block **cannot
exist during streaming** — the asymmetry is the wire contract (often documented in a test:
"done-only turn, no preceding chunk"), not a color regression. Look for the mode carrier next: if
`mode?: 'character'|'think'|'god'` is documented as "only meaningful for role: 'player'", the GM
message cannot know it is a God turn, so styling the stream phase needs a new carrier — a source
change, to be routed to the incumbent writer, never a unilateral branch.

## 2. Measure with react-test-renderer (real component, no rate limit, no capture)

```tsx
import TestRenderer, { act } from 'react-test-renderer';
import { ThemeContext } from '../src/context/ThemeContext';
import { themes, DEFAULT_THEME } from '../src/theme/themes';

function render(message: GameMessage, theme: ITheme) {
  let r!: TestRenderer.ReactTestRenderer;
  act(() => {
    r = TestRenderer.create(
      <ThemeContext.Provider value={{ theme, themeName: DEFAULT_THEME, setTheme: async () => {},
        bgTheme: 'none', setBgTheme: () => {}, colorScheme: 'dark' }}>
        <MessageBubble message={message} theme={theme} />
      </ThemeContext.Provider>,
    );
  });
  return r;
}
```

- Without the `ThemeContext.Provider` wrapper the tree renders empty (zero testIDs) — that is a
  harness mistake, not a product result.
- Walk `renderer.toJSON()` through **`props.children`** (React's `.children` is not the JSON shape),
  then flatten `props.style` arrays; read `borderColor`, `backgroundColor` and the first `Text`'s
  `color`.
- Report absolute values per phase and per theme, e.g.
  `STREAMING dark block=false` / `COMPLETED dark border=#a855f7 bg=rgba(168,85,247,0.12)` /
  `COMPLETED light border=#0d6efd`. Theme-dependent tint means "purple" is only true for the theme
  whose token is purple; the light theme being blue is theme-appropriate.
- Jest refuses a probe path outside `rootDir` ("No tests found … /tmp/x.test.tsx"). Copy the probe to
  `tests/zz_<name>.test.tsx`, run `npx jest tests/zz_*.test.tsx --ci`, then delete it and confirm
  `git status` shows no leftover file. Do not leave the probe as an untracked writer.

## 3. History check

```bash
git log --oneline --all -S"<blockName>" -- src/components/<Bubble>.tsx
git log --oneline --all -S"alpha(theme.tintColor, 0.12)" -- src/components/<Bubble>.tsx
```

If the block was introduced already using `theme.tintColor` and later commits only touch size/dedupe,
no purple literal was ever removed — say that outright.

## 4. Dedup against the incumbent PR (hunk-level, not title-level)

```bash
gh pr view <N> --json headRefOid,isDraft,mergeable,mergeStateStatus,baseRefOid
gh pr diff <N> | grep -E '^[+-].*(tintColor|backgroundColor|<field>)'
```

A God-turn PR that only fixes placeholder sentinels and bubble width is **not** a colour fix; the
repair still belongs to that writer's admission slot. Also compare the relevant files main-vs-head
(`git diff <old-tip> refs/remotes/origin/main -- <4 files>`) and characterise the delta
("+5 lines turnSummary only", "refactor extracting the narrative variable") instead of re-reading
whole files.

## Pitfalls

- A green "both phases equal" test proves parity, not correctness — it can be green while nothing is
  purple.
- The shared checkout may be modified by a concurrent lane mid-session (index can gain hundreds of
  staged files). Never stage/commit there; do all work in a detached worktree and disclose the
  foreign changes.
- Avoid inline `$(...)` inside a one-line `echo` in the agent terminal — it can trip the command
  parser blocklist. Split into separate commands or write a script file.
