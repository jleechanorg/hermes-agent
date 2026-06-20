"""Regression test for cross-channel Slack misroute (2026-06-19).

Incident timeline (UTC):
    11:20:58  Inbound from C0AH3RY3DK6 (WorldArchitect channel).
    11:22:27  Orphan reply `1781868147.039389` posted to C0AJQ5M0A0Y
              (home channel) — 5 seconds BEFORE the correct reply.
    11:22:32  Correct reply posted to C0AH3RY3DK6.

Root cause class: the gateway's outbound path sent to a chat_id that
was NOT derived from the inbound that triggered the response.

This test pins down the new OutboundGuard behavior so that:
  1. A chat_id pinned by `enter()` survives verify_send() calls.
  2. A verify_send with a DIFFERENT chat_id is recorded as a violation.
  3. A verify_send with the SAME chat_id passes.
  4. enter()/reset() round-trip restores the previous pinned chat_id.
  5. The contextvar is task-local — concurrent asyncio tasks do not
     contaminate each other.
  6. allowed_extra_destinations opts a destination out of the check.
  7. When no chat_id is pinned (non-handler-triggered send), verify_send
     passes regardless of the destination.
  8. A misroute simulation matching the exact incident pattern
     (pin A, send to B, send to A) records exactly one violation.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Add the repo root to sys.path so `gateway.outbound_guard` is importable
# from any working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gateway.outbound_guard import OutboundGuard  # noqa: E402


C_WORLDARCH = "C0AH3RY3DK6"
C_HOME = "C0AJQ5M0A0Y"


def test_enter_then_verify_same_chat_id_passes():
    guard = OutboundGuard()
    token = guard.enter(C_WORLDARCH)
    try:
        assert guard.active_chat_id == C_WORLDARCH
        assert guard.verify_send(C_WORLDARCH) is True
        assert guard.violations == []
    finally:
        guard.reset(token)


def test_verify_send_to_wrong_chat_id_records_violation():
    guard = OutboundGuard()
    token = guard.enter(C_WORLDARCH)
    try:
        # The exact incident pattern: pinned C_WORLDARCH, sent to C_HOME.
        assert guard.verify_send(C_HOME, operation="chat.postMessage") is False
        assert len(guard.violations) == 1
        v = guard.violations[0]
        assert v["active_inbound_chat_id"] == C_WORLDARCH
        assert v["outbound_chat_id"] == C_HOME
        assert v["operation"] == "chat.postMessage"
    finally:
        guard.reset(token)


def test_reset_restores_previous_pinned_chat_id():
    guard = OutboundGuard()
    token_outer = guard.enter(C_WORLDARCH)
    token_inner = guard.enter(C_HOME)
    try:
        assert guard.active_chat_id == C_HOME
    finally:
        guard.reset(token_inner)
    assert guard.active_chat_id == C_WORLDARCH
    guard.reset(token_outer)
    assert guard.active_chat_id is None


def test_no_pinned_chat_id_means_unrestricted_send():
    """Startup notifications and shutdown pings happen before/after any
    handler is active — they must NOT be blocked."""
    guard = OutboundGuard()
    # No enter() call — no pinned chat_id.
    assert guard.active_chat_id is None
    assert guard.verify_send(C_HOME) is True
    assert guard.verify_send(C_WORLDARCH) is True
    assert guard.violations == []


def test_allowed_extra_destinations_opt_out():
    """Call sites like the home-channel startup notification may send
    to a destination different from the active inbound. They opt out
    by passing `allowed_extra_destinations`."""
    guard = OutboundGuard()
    token = guard.enter(C_WORLDARCH)
    try:
        # Without opt-out: violation.
        assert guard.verify_send(C_HOME) is False
        assert len(guard.violations) == 1

        # With opt-out: passes.
        assert (
            guard.verify_send(
                C_HOME, allowed_extra_destinations=[C_HOME]
            )
            is True
        )
        # Still exactly the one violation from the un-opted send.
        assert len(guard.violations) == 1
    finally:
        guard.reset(token)


def test_clear_violations_resets_list():
    guard = OutboundGuard()
    token = guard.enter(C_WORLDARCH)
    try:
        guard.verify_send(C_HOME)
        guard.verify_send(C_HOME)
        assert len(guard.violations) == 2
        guard.clear_violations()
        assert guard.violations == []
    finally:
        guard.reset(token)


def test_incident_repro_exact_pattern():
    """Pin A, send to B, send to A — exactly one violation recorded."""
    guard = OutboundGuard()
    token = guard.enter(C_WORLDARCH)
    try:
        # Misroute (the orphan): pinned A but sent to B.
        assert guard.verify_send(C_HOME) is False
        # Correct: pinned A and sent to A.
        assert guard.verify_send(C_WORLDARCH) is True

        assert len(guard.violations) == 1
        v = guard.violations[0]
        assert v["active_inbound_chat_id"] == C_WORLDARCH
        assert v["outbound_chat_id"] == C_HOME
    finally:
        guard.reset(token)


@pytest.mark.asyncio
async def test_contextvar_is_task_local():
    """Two concurrent tasks each pin a different chat_id — neither
    sees the other's pinned value. This proves the regression guard
    holds under the gateway's concurrent-inbound workload."""

    async def pin_and_check(chat_id: str, expected_other: str, results: dict):
        guard = OutboundGuard()
        token = guard.enter(chat_id)
        try:
            # Yield to let the other task run its enter().
            await asyncio.sleep(0.01)
            # Our pinned chat_id must still be ours, not the other's.
            results[chat_id] = guard.active_chat_id
            # Verify_send against our own chat_id passes.
            results[f"{chat_id}_own_pass"] = guard.verify_send(chat_id)
            # Verify_send against the other chat_id fails (and we record it).
            results[f"{chat_id}_other_fail"] = guard.verify_send(expected_other)
        finally:
            guard.reset(token)

    results: dict = {}
    await asyncio.gather(
        pin_and_check(C_WORLDARCH, C_HOME, results),
        pin_and_check(C_HOME, C_WORLDARCH, results),
    )

    assert results[C_WORLDARCH] == C_WORLDARCH
    assert results[C_HOME] == C_HOME
    assert results["C0AH3RY3DK6_own_pass"] is True
    assert results["C0AJQ5M0A0Y_own_pass"] is True
    assert results["C0AH3RY3DK6_other_fail"] is False
    assert results["C0AJQ5M0A0Y_other_fail"] is False