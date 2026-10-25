# WA prompt-text gates: size ratchet + contract hash (and net-negative edit math)

Use when editing anything under `mvp_site/prompts/` (especially `game_state_instruction.md`) for a
"the prompt says X, it should say Y" fix. A prompt text edit in this repo is a **two-gate change**;
landing only the prose leaves main/PR red.

## Gate 1 — size ratchet (chars, not bytes)

`mvp_site/tests/test_game_state_instruction_prompt.py::test_game_state_prompt_source_size_ratchet`

```python
MAX_GAME_STATE_PROMPT_CHARS = 98_388        # as of 2026-10-24
assert len(content) <= MAX_GAME_STATE_PROMPT_CHARS
```

- `len(content)` is **Python characters**. `wc -c` is **bytes**. Emoji-bearing prompt files diverge:
  observed `wc -c` 98,749 vs real `len()` 98,389 (≈360 bytes of 📚🚨🗡️). Always measure with Python:
  `python3 -c 'print(len(open(p,encoding="utf-8").read()))'`.
- The ratchet is razor-thin: a PR can miss by **exactly 1 char**. When it is already at/over the
  limit, the edit must be **net ≤ −1 char inside that file**, not "net zero".
- Companion: `mvp_site/tests/test_system_instruction_compression_e2e.py`
  (`BASELINE_GAME_STATE_CHARS = 129_825`, `TARGET_MAX_GAME_STATE_CHARS`, ≥9,800-char savings) and
  `test_compression_lever1.py`.

## Gate 2 — contract hash manifest

`test_game_state_prompt_contract_hash_synchronized` compares
`mvp_site/schemas/prompt_tool_contracts.json` → `contracts[]` entry with
`path == "mvp_site/prompts/game_state_instruction.md"` (`id: game_state_instruction_prompt`):

- `sha256` must equal `sha256_file(PROMPT_PATH)` (whole file, bytes).
- `version` is the **first 12 hex chars of that sha256** (e.g. `20c9b8b40606`).
- Not every prompt file is in the manifest — check first (`temporal_enforcement_instruction.md` is
  NOT; only `constants.py FILENAME_TEMPORAL_ENFORCEMENT` references it).

A prompt edit that changes the file without touching the manifest leaves both CI
(`Prompt / Tool Contract Hash Validation`) and the local test red.

## Ceiling vs ratchet (different things)

- Ceiling: `NATIVE_GEMINI_SYSTEM_INSTRUCTION_BUDGET_TOKENS = 135_000` (`constants.py:449`) ×4 =
  **540,000 chars**; overflow raises `MandatoryContextCapacityError(reason="system_instruction_exceeds_ceiling")`
  (`llm_service.py`). `game_state_instruction.md` is a **critical file** in `context_compaction.py`,
  so it is never truncated — every byte is billed.
- Ratchet: the much tighter 98,388-char source test above. Headroom against the ceiling does NOT
  authorize growth; the ratchet is the binding constraint.

## Net-negative consolidation recipe (proved)

When the file is at/over the ratchet and you must add a rule:

1. Find text that **duplicates another block in the same file** and delete it. Example used: the
   `### Travel/Rest Time Costs` bullet `- Combat: 6 seconds/round | Short Rest: 1 hour | Long Rest: 8 hours`
   restates three rows already in the Story-Advancing Actions table → deleting it frees 68 chars with
   zero semantic loss.
2. **Collapse** adjacent rows instead of adding a row. Two distance-blind rows
   (`| Travel | Calculate from distance/speed |` and `| Scene transition | +5-15 minutes |`) became one.
3. **Cite the owning section** rather than restating numbers: `distance ÷ speed (see Travel/Rest Time Costs)`.
4. Recompute the delta before writing anything; assert `len(new) <= RATCHET` in the build script.

## Wording rules for time/duration prompts (operator-reviewed)

- **Never key duration to an administrative label.** `"New city or region: hours-to-days"` forces hours
  onto a legitimately minutes-away neighbouring town or a boundary hop. Key to **actual distance**
  (`distance ÷ speed`) so short cross-boundary travel stays minutes and a long march takes days.
- **Do not duplicate physics constants into a second prompt file.** Restating `3 mph walk / 6 mph mounted`
  inside `temporal_enforcement_instruction.md` loses the existing game-system qualification
  ("D&D 5e defaults (adjust for other game systems)"), terrain halving, and mount/vehicle/magic context.
  Reference the owning section instead.
- Distinguish **ordered vs completed**: an order/dispatch advances the clock only as far as it has
  actually travelled; a reply adds the return leg; already-completed work costs only the audience.
- Concurrent lanes cost `max(lane)`, never the sum.

## Offline verification without a full suite run

```bash
# 1. exact gate math, deterministic, no pytest
python3 - <<'EOF'
import hashlib, json, pathlib
gs = pathlib.Path("mvp_site/prompts/game_state_instruction.md").read_text(encoding="utf-8")
print("chars", len(gs), "<=98838", len(gs) <= 98_388)
sha = hashlib.sha256(gs.encode()).hexdigest()
man = json.loads(pathlib.Path("mvp_site/schemas/prompt_tool_contracts.json").read_text())
e = [c for c in man["contracts"] if c.get("path","").endswith("game_state_instruction.md")][0]
print("manifest match", e["sha256"] == sha, "version", e["version"], sha[:12])
EOF

# 2. applicability, no mutation
git apply --check --verbose /tmp/wa-timing-patch/*.patch
```

If a run is needed, apply in place, run the prompt tests, then restore — this needs no extra worktree:

```bash
patch -p1 --silent < /tmp/xxx.patch
python3 -m pytest mvp_site/tests/test_game_state_instruction_prompt.py mvp_site/tests/test_prompts.py \
  mvp_site/tests/test_regression_string_time_formatting.py mvp_site/tests/test_initial_world_time_instruction.py \
  mvp_site/tests/test_system_instruction_compression_e2e.py -q
git checkout -- mvp_site/prompts/game_state_instruction.md mvp_site/prompts/temporal_enforcement_instruction.md \
                mvp_site/schemas/prompt_tool_contracts.json
git status --porcelain   # must be empty
```

`git worktree add <tmp>` inside this repo may be intercepted by the local wrapper that insists on
`diskm worktree-new /Users/jleechan/projects/worldarchitect.ai <branch> --name <name>`; the
apply→test→`git checkout --` loop above avoids that path entirely.

## Grep discipline (learned the hard way)

Grepping a prompt literal repo-wide (`grep -rF "Calculate from distance/speed" mvp_site/tests testing_mcp scripts`)
returned **8.5 MB** because captured Gemini request payloads live in `mvp_site/tests/test_end2end/fixtures/`
and `testing_mcp/fixtures/`. Restrict to `mvp_site/tests/test_*.py`, `mvp_site/agent_prompts.py`,
`mvp_site/constants.py`, `mvp_site/schemas/`. Fixture hits are **recordings, not assertions** — 6 fixture
hits say nothing about whether a string is a pinned contract.
