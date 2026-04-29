"""Slack read tools: conversations_history and conversations_replies.

These tools give the agent on-demand access to Slack channel history and
thread replies when the gateway's automatic thread-context pre-fetch is
insufficient (e.g. after context compaction wiped the session history).

Requires the Hermes gateway to be running with a Slack platform configured.
In CLI context (no gateway), falls back to OPENCLAW_SLACK_BOT_TOKEN or
SLACK_USER_TOKEN from the environment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


def _error(message: str) -> dict:
    return {"error": message}


CONVERSATIONS_HISTORY_SCHEMA = {
    "name": "conversations_history",
    "description": (
        "Fetch recent messages from a Slack channel.\n\n"
        "Use this when you need to understand what was discussed in a channel "
        "before your current conversation window, or to get context on a channel "
        "that isn't in your recent session history.\n\n"
        "Returns up to 'limit' messages (oldest to newest). Set inclusive=True "
        "to include the oldest message as well."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Slack channel ID, for example C09GRLXF9GR."
            },
            "oldest": {
                "type": "string",
                "description": "Start of time range (Unix timestamp string). Fetch messages newer than this ts. Optional."
            },
            "latest": {
                "type": "string",
                "description": "End of time range (Unix timestamp string). Fetch messages older than this ts. Optional."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return (1-200). Default 50.",
                "default": 50
            },
            "inclusive": {
                "type": "boolean",
                "description": "Include the oldest/latest message in the result. Default false.",
                "default": False
            },
        },
        "required": ["channel"]
    }
}

CONVERSATIONS_REPLIES_SCHEMA = {
    "name": "conversations_replies",
    "description": (
        "Fetch all replies in a Slack thread.\n\n"
        "Use this when you need to read the full context of a thread that you "
        "were mentioned in, or to catch up on a thread that was cleared from "
        "your session history after context compaction.\n\n"
        "Returns the thread parent message plus all replies, sorted by ts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Slack channel ID where the thread lives (e.g. C09GRLXF9GR)."
            },
            "thread_ts": {
                "type": "string",
                "description": "The parent message's ts (timestamp) that identifies the thread. E.g. '1776162880.250059'."
            },
            "oldest": {
                "type": "string",
                "description": "Start of time range (Unix timestamp string). Optional."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return (1-200). Default 50.",
                "default": 50
            },
            "inclusive": {
                "type": "boolean",
                "description": "Include the thread_ts message itself. Default false.",
                "default": False
            },
        },
        "required": ["channel", "thread_ts"]
    }
}


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


def _get_slack_token() -> str | None:
    """Resolve Slack bot/user token from gateway config or environment."""
    # Try gateway config first (gateway context)
    try:
        from gateway.config import load_gateway_config, Platform
        config = load_gateway_config()
        pconfig = config.platform_config(Platform.SLACK)
        if pconfig and pconfig.token:
            return pconfig.token
    except Exception:
        pass

    # Fall back to environment tokens
    for key in ("OPENCLAW_SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_USER_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


async def _slack_api_call(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Make a Slack Web API call. Returns parsed JSON response."""
    token = _get_slack_token()
    if not token:
        return {"ok": False, "error": "No Slack token available. Set OPENCLAW_SLACK_BOT_TOKEN, SLACK_BOT_TOKEN, or SLACK_USER_TOKEN."}

    try:
        import aiohttp
    except ImportError:
        return {"ok": False, "error": "aiohttp not installed."}

    clean_params = {k: v for k, v in params.items() if v is not None}
    url = f"https://slack.com/api/{method}?"
    import urllib.parse
    url += urllib.parse.urlencode(clean_params)

    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return data
                    err = data.get("error", "unknown_error")
                    # Rate limited: retry with backoff.
                    if err == "ratelimited" and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return data
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "max_retries"}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def conversations_history_tool(args: dict) -> str:
    """Handler for conversations_history tool."""
    channel = (args.get("channel") or "").strip()
    if not channel:
        return json.dumps(_error("'channel' is required"))

    params: dict[str, Any] = {
        "channel": channel,
        "limit": min(int(args.get("limit") or 50), 200),
        "inclusive": bool(args.get("inclusive", False)),
    }
    oldest = (args.get("oldest") or "").strip()
    if oldest:
        params["oldest"] = oldest
    latest = (args.get("latest") or "").strip()
    if latest:
        params["latest"] = latest

    result = await _slack_api_call("conversations.history", params)
    if not result.get("ok"):
        return json.dumps(_error(f"conversations.history failed: {result.get('error', 'unknown')}"))

    messages = list(reversed(result.get("messages", [])))
    if not messages:
        return json.dumps({"ok": True, "messages": [], "count": 0})

    # Format for readability
    formatted = []
    for msg in messages:
        user = msg.get("user", "?")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        # Strip bot mention tags for cleaner output
        text = text.replace(f"<@{os.environ.get('SLACK_BOT_USER_ID', '')}>", "").strip()
        subtype = msg.get("subtype", "")
        if subtype in ("channel_join", "channel_leave"):
            continue
        formatted.append(f"[{ts}] {user}: {text}")

    return json.dumps({
        "ok": True,
        "count": len(formatted),
        "messages": formatted,
        "has_more": result.get("has_more", False),
        "next_cursor": result.get("response_metadata", {}).get("next_cursor"),
    })


async def conversations_replies_tool(args: dict) -> str:
    """Handler for conversations_replies tool."""
    channel = (args.get("channel") or "").strip()
    thread_ts = (args.get("thread_ts") or "").strip()
    if not channel:
        return json.dumps(_error("'channel' is required"))
    if not thread_ts:
        return json.dumps(_error("'thread_ts' is required"))

    params: dict[str, Any] = {
        "channel": channel,
        "ts": thread_ts,
        "limit": min(int(args.get("limit") or 50), 200),
        "inclusive": bool(args.get("inclusive", False)),
    }
    oldest = (args.get("oldest") or "").strip()
    if oldest:
        params["oldest"] = oldest

    result = await _slack_api_call("conversations.replies", params)
    if not result.get("ok"):
        return json.dumps(_error(f"conversations.replies failed: {result.get('error', 'unknown')}"))

    messages = result.get("messages", [])
    if not messages:
        return json.dumps({"ok": True, "messages": [], "count": 0, "thread_ts": thread_ts})

    formatted = []
    for i, msg in enumerate(messages):
        user = msg.get("user", "?")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        is_parent = (i == 0)
        prefix = "[parent] " if is_parent else f"[reply {i}] "
        formatted.append(f"{prefix}[{ts}] {user}: {text}")

    return json.dumps({
        "ok": True,
        "count": len(formatted),
        "messages": formatted,
        "thread_ts": thread_ts,
        "has_more": result.get("has_more", False),
        "next_cursor": result.get("response_metadata", {}).get("next_cursor"),
    })


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _check_fn() -> bool:
    """Available when a Slack token is resolvable from gateway config or env."""
    return _get_slack_token() is not None


from tools.registry import registry

registry.register(
    name="conversations_history",
    toolset="messaging",
    schema=CONVERSATIONS_HISTORY_SCHEMA,
    handler=conversations_history_tool,
    check_fn=_check_fn,
    is_async=True,
    emoji="",
    description="Fetch recent messages from a Slack channel.",
)

registry.register(
    name="conversations_replies",
    toolset="messaging",
    schema=CONVERSATIONS_REPLIES_SCHEMA,
    handler=conversations_replies_tool,
    check_fn=_check_fn,
    is_async=True,
    emoji="",
    description="Fetch all replies in a Slack thread.",
)
