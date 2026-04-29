"""Live Slack replay tests for gateway Slack ingestion.

These tests are skipped by default because they call the real Slack Web API.
Run with RUN_SLACK_LIVE_REPLAY=1 and a configured Slack bot token.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from gateway.config import Platform, load_gateway_config
from gateway.platforms.slack import SlackAdapter


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SLACK_LIVE_REPLAY") != "1",
    reason="live Slack replay is opt-in",
)


LIVE_CHANNEL_ID = os.getenv("SLACK_LIVE_REPLAY_CHANNEL", "C0AH3RY3DK6")
LIVE_THREAD_TS = os.getenv("SLACK_LIVE_REPLAY_THREAD_TS", "1777436811.330699")
LIVE_MESSAGE_TS = os.getenv("SLACK_LIVE_REPLAY_MESSAGE_TS", "1777482231.526049")
LIVE_MESSAGE_TEXT = os.getenv("SLACK_LIVE_REPLAY_TEXT", "Status on the worker")
LIVE_USER_ID = os.getenv("SLACK_LIVE_REPLAY_USER", "U09GH5BR3QU")


@pytest.mark.asyncio
async def test_live_slack_thread_replay_fetches_real_thread_context():
    """Replay the real Slack event that exposed lost thread context.

    The replay forces an active local session to mirror the failure mode:
    before the fix, active-session state skipped Slack thread fetching and
    delivered only "Status on the worker" to the agent. The fixed behavior
    fetches the live Slack thread and prepends the original wa-1514 context.
    """
    try:
        from slack_sdk.web.async_client import AsyncWebClient
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"slack_sdk not installed: {exc}")

    config = load_gateway_config()
    slack_config = config.platforms.get(Platform.SLACK)
    if not slack_config or not slack_config.token:
        pytest.skip("Slack platform token is not configured")

    client = AsyncWebClient(token=slack_config.token.split(",")[0].strip())
    auth = await client.auth_test()
    team_id = auth["team_id"]
    bot_user_id = auth["user_id"]

    adapter = SlackAdapter(slack_config)
    adapter._app = SimpleNamespace(client=client)
    adapter._team_clients[team_id] = client
    adapter._team_bot_user_ids[team_id] = bot_user_id
    adapter._bot_user_id = bot_user_id
    adapter._channel_team[LIVE_CHANNEL_ID] = team_id
    adapter._has_active_session_for_thread = lambda **kwargs: True

    captured = {}

    async def capture_message(message_event):
        captured["text"] = message_event.text
        captured["source"] = message_event.source

    adapter.handle_message = capture_message

    await adapter._handle_slack_message(
        {
            "type": "message",
            "channel": LIVE_CHANNEL_ID,
            "channel_type": "channel",
            "team": team_id,
            "user": LIVE_USER_ID,
            "text": LIVE_MESSAGE_TEXT,
            "thread_ts": LIVE_THREAD_TS,
            "ts": LIVE_MESSAGE_TS,
        }
    )

    text = captured.get("text", "")
    assert text.startswith("[Thread context")
    assert "Make an AO worker to run simplify on mvp_site" in text
    assert "wa-1514" in text
    assert text.endswith(LIVE_MESSAGE_TEXT)
    assert captured["source"].thread_id == LIVE_THREAD_TS
