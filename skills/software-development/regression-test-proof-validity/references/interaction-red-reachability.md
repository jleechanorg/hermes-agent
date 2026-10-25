# Is the RED *state* reachable? (interaction/gesture fixes)

A regression claim needs three legs, not two: (1) the pre-fix code runs, (2) the **state the bug needs
is actually reachable through the same input path** the GREEN leg uses, (3) the post-fix code changes
the observed output. Leg 2 is the one that silently fails and produces a fabricated "no difference".

## Method — measure the rendered state per step

Drive the real gesture pipeline and sample the rendered transform, not the source flags:

```python
READ = """() => { const img = document.querySelector('[data-testid="<viewer-image>"]');
  const t = getComputedStyle(img.parentElement).transform; const m = t.match(/matrix\\(([^)]+)\\)/);
  const p = m[1].split(',').map(Number);
  return {scale:+p[0].toFixed(4), tx:+p[4].toFixed(2), ty:+p[5].toFixed(2)}; }"""
cdp.send("Input.dispatchTouchEvent", {"type": "touchStart"|"touchMove"|"touchEnd",
          "touchPoints": [{"x":x,"y":y,"id":i}, …]})
```

Rebuild the bug's *ordering* explicitly (e.g. pan starts first → second finger joins → pinch → lift one
finger → second pinch), sampling after each step plus a short trajectory (100/250/500 ms). Record:
initial → live-sub-1x → post-lift → second-gesture start → settle.

## Verified RNGH 2.28 web behaviour (2026-10-24) — check before designing a RED

- **Pan ends on ANY pointer-up.** `web/handlers/PanGestureHandler.js` `onPointerUp`:
  `if (state === ACTIVE) this.end(); else { resetProgress(); this.fail(); }`. Only
  `onPointerRemove` (pointercancel-class) can keep pan alive. So "pinch ended, pan still ACTIVE with the
  remaining finger" has **no web window** at the DOM-gesture level (an app-level `panActive` flag can
  still survive via callback ordering).
- **A pinch does not restart while a pointer stays down.** Re-adding a second finger after lifting it
  left the rendered scale frozen (0.9516 across every second-pinch step) on both arms.
- **Full release hard-clamps to the in-range value** (scale → 1.0). Any bug that needs an
  out-of-range *committed* base therefore disappears in a fully-released gesture sequence — exactly the
  ordering a naive script writes.
- **Two distinct bundles can still produce identical trajectories.** That is a legitimate negative
  result ("the change has no observable web delta"), reportable only if you also recorded per-arm
  bundle sha256 + size, so "identical" cannot be explained by one shared bundle.

## Reporting rules

- Identical before/after trajectories ⇒ say **"not reproduced / no observable delta on this platform"**.
  Never manufacture the state, never force component internals, never label it GREEN.
- If the required ordering cannot be expressed by the available input driver, record the **platform
  limitation** with the code cite and the sampled matrices, then name what *would* prove it (a driver
  with independent contact lifetimes, or the native platform). Keep harness-level captures as
  *supplementary*, never as acceptance.
- State the probe's own limits: video-less matrix runs, harness-mounted viewer (real component, fixture
  page), and the number of independently driven steps.
