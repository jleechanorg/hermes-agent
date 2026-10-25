# Capture-harness verdict fail-open (WA #10725 raw-SSE driver)

Worked case, 2026-10-24. An independent reviewer blocked a draft PR with:
*"the raw capture runner returns signature/agreement booleans but no enforced passed/errors
verdict"* — and asked for it closed **without weakening assertions**.

## Why booleans are not a verdict

The driver (`testing_mcp/schema/test_spells_ordinary_turn_raw_sse_es.py`) built a receipt and
returned one scenario dict:

```python
return [{
    "scenario": "ordinary_spell_turn_raw_sse",
    "campaign_id": campaign_id,
    "frame_count": len(frames),
    "frame_sha256_round_trip_ok": receipt["frame_sha256_round_trip_ok"],
    "signature_ok": signature_ok,
    "persisted_endpoint_agree": receipt["spells"]["persisted_endpoint_agree"],
    "receipt": str(receipt_path),
}]
```

The shared runner normalizes every result before counting passes
(`testing_mcp/lib/base_test.py`, `_run_single`):

```python
if "passed" not in result:
    result["passed"] = len(result.get("errors", [])) == 0
```

So a **bad signature, an empty repertoire, or a persisted≠endpoint disagreement could never fail
the capture**: no `errors`, no `passed` → normalized to `passed = True`. The receipt *described*
the defect and the run still went green. Grep that found it:

```bash
grep -n '"passed" not in result' testing_mcp/lib/base_test.py   # the normalization branch
grep -n 'passed' testing_mcp/schema/test_spells_ordinary_turn_raw_sse_es.py  # zero hits = fail-open
```

The repo rule the reviewer cited: *"Every `run_scenarios()` result must include `passed`, `errors`,
and `campaign_id` and fail loudly — no silent excepts, no partial-success pass."*

## Repair shape (what actually landed, 2f3b8670a0)

1. **Pure decision function**, no harness/provider imports, offline-testable:
   `testing_mcp/schema/spells_capture_contract.py::evaluate_capture_packet(packet) -> list[str]`
   returning defects (empty list = accepted). It enforces:
   - transport `error` / `error_type` present → defect
   - any `event_type == "error"` frame → defect
   - no `chunk` frame, or no `done` frame → defect
   - each frame's base64 decodes, and its sha256 **and** length match the recorded values
   - signature carries its required fields (schema_version, algorithm, digest, request_id,
     response_length) and the digest matches the payload
   - `persisted_known == endpoint_known` and both cantrip lists agree
   - every persisted entry has an integer `level` and a non-empty `description`
2. **Driver enforces, does not report**:
   ```python
   contract_failures = evaluate_capture_packet(packet)
   receipt["contract_failures"] = contract_failures
   receipt["contract_accepted"] = not contract_failures
   ...
   if contract_failures:
       raise AssertionError("raw-SSE capture contract failed:\n- " + "\n- ".join(contract_failures))
   if not signature_ok:
       raise AssertionError("streaming signature validation failed: " + "; ".join(signature_errors))
   ```
3. **Offline pinning in the fast suite** (`mvp_site/tests/test_spells_capture_contract.py`, 13 tests):
   one accepted good packet plus one negative control per defect class. Cheap suite, no provider
   turn spent, so the expensive capture path cannot regress silently.
4. Keep the receipt fields (`signature_ok`, `persisted_endpoint_agree`, …) — they are *evidence*;
   the verdict is additional, never a replacement.

## Transferable rules

- Decision (pure function) ≠ enforcement (driver raises). Doing both in the driver makes the
  verdict untestable without spending a provider turn; doing neither makes it prose.
- A capture harness that spends money/time per run must be **pinned offline** so its gate is
  testable in seconds.
- Report the un-replayed artifact honestly: the reviewer asked for the existing raw handback
  (`ca62f620`) to be re-scored; no copy existed on the verifying host, so the correct report was
  "enforced in code + proven on synthetic packets; the named real packet was not present locally and
  no new provider turn was run" — not a re-run and not a claim.
- Same class appears in any `run_scenarios()`-style harness: if the result dict can be assembled
  without a verdict, the runner's normalization will make it pass.
