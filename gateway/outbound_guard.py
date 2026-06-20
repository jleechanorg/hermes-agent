"""Outbound chat_id guard — prevents cross-channel Slack misroute.

Production incident (2026-06-19 11:20:58–11:22:32 UTC):
    Inbound from C0AH3RY3DK6 (WorldArchitect) at 11:20:58.
    Orphan reply `1781868147.039389` posted to C0AJQ5M0A0Y at 11:22:27
    (5 seconds BEFORE the correct reply at 11:22:32 to C0AH3RY3DK6).
    No thread_ts on the orphan because the inbound had no parent in C0AJQ5M0A0Y.

Root cause class: the gateway's outbound path used a chat_id that was
NOT derived from the inbound that triggered the response. The chat_id
came from a stale cache, the home channel, or a previous handler's
session source.

This module provides `OutboundGuard`, a thread-/task-local context manager
that pins the active inbound chat_id for the lifetime of a handler.
Any call to `verify_send(chat_id)` either confirms the chat_id matches
the active inbound, or — if it doesn't — records a guard violation
that the regression test fails on.

The guard is opt-in: call sites that already pass the correct `source.chat_id`
are unaffected. Call sites that previously sent to the wrong channel
now produce an explicit, observable failure instead of a silent misroute.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OutboundGuard:
    """Tracks the active inbound chat_id and verifies outbound send alignment.

    Each `_handle_message_with_agent` invocation should call
    `self._outbound_guard.enter(chat_id=source.chat_id)` to pin the
    inbound. Any call to `verify_send(chat_id, ...)` while a chat_id
    is pinned either confirms alignment (returns True) or records a
    violation (returns False, emits a WARNING log, appends to `violations`).

    The guard is task-local via `contextvars` so concurrent inbounds in
    different asyncio tasks do not interfere with each other.
    """

    _active_chat_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
        "outbound_guard_active_chat_id", default=None
    )
    violations: List[dict] = field(default_factory=list)

    def enter(self, chat_id: Optional[str]):
        """Pin `chat_id` as the active inbound for the current task.

        Returns a `ResetToken` (ContextVar token) — call `reset(token)`
        in a `finally` block to restore the previous pinned chat_id.
        """
        return self._active_chat_id.set(chat_id)

    def reset(self, token) -> None:
        """Restore the previous pinned chat_id (use in `finally`)."""
        self._active_chat_id.reset(token)

    @property
    def active_chat_id(self) -> Optional[str]:
        """The currently-pinned inbound chat_id, or None if no handler is active."""
        return self._active_chat_id.get()

    def verify_send(
        self,
        chat_id: Optional[str],
        *,
        operation: str = "adapter.send",
        allowed_extra_destinations: Optional[List[str]] = None,
    ) -> bool:
        """Verify that `chat_id` matches the active inbound chat_id.

        Returns True if the send is aligned (or no inbound is pinned —
        which means this is a non-handler-triggered send like a startup
        notification or a shutdown ping, both of which are allowed to
        target the home channel).

        Returns False if a chat_id is pinned AND the send's chat_id
        does not match. The mismatch is recorded in `self.violations`
        and logged at WARNING level.

        `allowed_extra_destinations` lets specific call sites (like
        the home-channel startup notification) opt out of the check
        even when a handler is active.
        """
        pinned = self._active_chat_id.get()
        if pinned is None:
            return True
        if chat_id is None:
            return True
        if str(chat_id) == str(pinned):
            return True
        if allowed_extra_destinations and str(chat_id) in {
            str(c) for c in allowed_extra_destinations
        }:
            return True
        violation = {
            "operation": operation,
            "active_inbound_chat_id": pinned,
            "outbound_chat_id": chat_id,
        }
        self.violations.append(violation)
        logger.warning(
            "Outbound chat_id misalignment detected: operation=%s "
            "active_inbound=%s outbound=%s — refusing to send to wrong channel",
            operation, pinned, chat_id,
        )
        return False

    def clear_violations(self) -> None:
        """Reset the violation list (used by tests to assert a clean run)."""
        self.violations.clear()


__all__ = ["OutboundGuard"]
