# Prompt-floor cliff: a critical prompt's growth truncates a floored contract

Worked case, 2026-10-24 (worldarchitect.ai PR #10833, issue #10725). Two CI shards failed for a reason
that looked unrelated to the diff.

## Failure signature

```
FAILED mvp_site/tests/test_agy_instruction_delivery_contract.py::test_valid_repeat
  - AssertionError: Exact mandatory faction contract was not delivered
```

The composed instruction ended mid-contract:

```
# File: faction_minigame_instruction.md
## Mandatory intel resolution contract
… Stamp executed operations with target and expiry turn (`current_t

[...SECTION TRUNCATED FOR BUDGET - FILE CONTENT SHORTENED...]
```

The assertion (in `testing_mcp/faction/test_agy_instruction_delivery_real.py`, replayed by the offline
test) is:

```python
mandatory_contract = faction_source.split("## Mandatory intel resolution contract", 1)[1] \
                                 .split("## Canonical end-turn state contract", 1)[0].strip()
assert mandatory_contract in instructions, "Exact mandatory faction contract was not delivered"
```

i.e. the contract must survive **byte-exact**; a cut 60 chars early fails it.

## Mechanism (`mvp_site/context_compaction.py`)

- Critical files (`master_directive.md`, `game_state_instruction.md`, …) are kept **in full**, even
  when the request is over budget.
- Non-critical files with a protected floor (`NARRATIVE_FILES`, `FACTION_FILES`,
  `GOD_MODE_FILES` → `_FLOOR_SPECS`) get `_protected_floor_reservations`.
- When `desired_floor_total > remaining_budget`, that function **scales every floor down
  proportionally** and logs:
  `EMERGENCY_COMPACT: protected floors (8,212 chars desired) exceeded remaining_budget (3,101 chars); scaled to 3,100 chars`
- So bytes added to a *critical* prompt come out of a *floored* file's body. Growth is not
  free even when the file you edited is itself untruncated.

Measured on this case:

| tree | whole instruction | remaining budget | faction_minigame segment kept | contract needs |
|---|---|---|---|---|
| `origin/main` | 369,791 | 3,325 | 1,661 | 1,497 |
| PR head | 370,051 (+101 bytes of prompt) | 3,101 | 1,549 | 1,497 |

Pre-PR margin ≈ 62 chars; +101 bytes of prompt cost ~112 chars of the floored share. Note the
1,497 threshold is the *assembled* offset (the loader prefixes `# Faction Management Mini-Game`),
not the raw file offset (1,456) — measure on the assembled text, not the .md.

## Probe (no CI needed)

```bash
cd <worktree-at-the-PR-head>
PYTHONPATH=. python3 - <<'PY'
from mvp_site.agents import FactionManagementAgent
from mvp_site.context_compaction import _compact_system_instruction, _split_system_instruction
state = {"custom_campaign_state": {"faction_minigame": {"enabled": True}},
         "army_data": {"total_strength": 100}, "player_character_data": {"level": 6}}
whole = FactionManagementAgent(game_state=state).build_system_instructions()
b = _compact_system_instruction(whole, max_tokens=70_000)
print("whole", len(whole), "compacted", len(b))
for s in _split_system_instruction(b)[1]:
    print(f"{len(s):7d}  {s.split(chr(10),1)[0]}  {'TRUNCATED' if 'SECTION TRUNCATED' in s else ''}")
PY
```

Run it at `origin/main` and at the PR head; the delta explains the failure and gives the margin.

## Rejected fix (do not repeat)

"Floors are documented as hard minimums, so preserve them in full when the budget can't fund them."
That patch (in `_protected_floor_reservations`) fails **19** tests:

- `test_witness_continuity_compaction_10516::test_real_policy_floors_compete_and_scale_without_truncating_witness`
  → `assert 20000 < 20000` (it expects the narrative floor to be scaled below 20,000).
- the delivery harness's own precondition `assert "SECTION TRUNCATED FOR BUDGET" in budgeted`
  (the stress case requires that *something* is truncated).
- `test_context_budgeting` overflow-reclaim cases.

Scaling is the pinned, intended behavior. A content PR must not change compaction.

## Accepted fix

Tighten the prompt text that grew, to **net-negative versus pre-PR bytes**:

| block (3 lines around the spells example) | chars |
|---|---|
| `origin/main` | 700 |
| PR head | 803 |
| after tightening | **558** (−142 vs main) |

Then the faction segment kept 1,672 chars (> 1,497) and the contract is delivered; all four
compaction/budget suites plus the delivery suite pass unchanged. Verification:

```bash
./run_tests.sh mvp_site/tests/test_agy_instruction_delivery_contract.py \
  mvp_site/tests/test_context_budgeting.py mvp_site/tests/test_god_mode_prompt_budget.py \
  mvp_site/tests/test_witness_continuity_compaction_10516.py -q
```

## Transferable lesson

When an exact-contract *delivery* test fails after a prompt edit, treat it as a budget-cliff alarm:
- measure the assembled-segment length vs. the contract end at both base and head;
- fix by shrinking the addition below pre-PR size — never by loosening the delivery assertion and
  never by relaxing the compaction scaling that other pins assert.
