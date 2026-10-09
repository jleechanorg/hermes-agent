# immediate_ack plugin

Posts a short text acknowledgement ("On it…" by default) to the same
Slack channel/thread when the Hermes gateway starts processing a
user-originated message. Replaces the ack with a status marker (✅ on
success, ❌ on failure/cancellation) when the session ends.

## Why

The Slack adapter already auto-swaps the 👀 reaction to ✅/❌ at end of
turn via `BasePlatformAdapter.on_processing_complete`, but it does NOT
post a visible *text* acknowledgement. Operators watching a quiet
channel want a textual signal so the user knows the bot received their
message before the long LLM turn completes.

This plugin adds the text layer as an isolated hook — no edits to
`gateway/platforms/slack.py` or any other core file.

## Layout

```
~/.hermes/plugins/immediate_ack/
├── __init__.py     # register() + pre_gateway_dispatch + on_session_end handlers
├── plugin.yaml     # manifest: hooks, metadata
└── README.md       # this file
```

## Config

Gated by two keys under `platforms.slack.extra` in `~/.hermes/config.yaml`:

```yaml
platforms:
  slack:
    extra:
      immediate_ack: true              # default: false
      immediate_ack_text: "On it…"     # default: "On it…"
```

Both keys are read at runtime on every incoming message. No restart
required to toggle (plugin re-reads on each invocation).

## Loading (opt-in)

Plugins are opt-in. To load this plugin, add `immediate_ack` to
`plugins.enabled` in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - rtk
    - immediate_ack   # <-- add this
```

The default `~/.hermes/config.yaml` ships with `plugins.enabled: ["rtk"]`
only. Without the entry above the plugin's manifest is parsed but its
`register(ctx)` is never called.

## Hook usage

| Hook | Payload received | Action |
|------|------------------|--------|
| `pre_gateway_dispatch` | `event: MessageEvent`, `gateway: GatewayRunner`, `session_store` | Post ack text to event.source.chat_id, reply_to = source.message_id. Track ack in plugin state keyed by event.message_id. |
| `on_session_end` | `session_id: str`, optional `outcome` | Pop tracked ack for the session; post ✅/❌ to same channel/thread. |

The plugin returns `None` from `pre_gateway_dispatch` (allow normal
dispatch) in all cases — it never gates the dispatch loop on its own
internal state.

## Failure handling

Every entry point is wrapped in `try/except Exception` with `logger.debug`
on failure. The plugin must never crash the gateway dispatch loop or
session-end path. If anything goes wrong (config unreadable, adapter
missing, Slack API error), the plugin silently no-ops.

## Design deviation from initial subagent attempt

A previous implementation attempted to:

- Use `on_processing_complete` as a plugin hook — but per
  `hermes_cli/plugins.py:128-168` `VALID_HOOKS`, that name is NOT in the
  set (it is an adapter method, not a plugin hook). The plugin loader
  would log a warning and discard the registration.
- Use a background watcher thread polling Slack for the bot's reply
  — fragile (no proper async integration; reaches into private
  `_get_client` API; poll-based race conditions).
- Use env vars (`HERMES_IMMEDIATE_ACK`) instead of the
  `platforms.slack.extra.immediate_ack` config flag the task specified.

This rewrite fixes all three: it uses only VALID_HOOKS members, async
hooks with no background thread, and reads the documented config path.

## Reference citations (from upstream hermes-agent)

- Plugin discovery and `VALID_HOOKS`: `hermes_cli/plugins.py:128-168`
- `register_hook` API: `hermes_cli/plugins.py:603-618`
- `pre_gateway_dispatch` invocation site: `gateway/run.py:5649-5688`
- `on_session_end` invocation: `run_agent.py:15246-15260`, `cli.py:12905-12913`
- Slack adapter `_reacting_message_ids` set: `gateway/platforms/slack.py:359`
- Slack `send(chat_id, content, reply_to, metadata)`: `gateway/platforms/slack.py:775-781`
- Slack `on_processing_complete` (existing reaction flow): `gateway/platforms/slack.py:1385-1400`
- `Platform.SLACK` enum: `gateway/config.py:82`
- `GatewayRunner.adapters`: `gateway/run.py:1169`
- `MessageEvent` dataclass: `gateway/platforms/base.py:915-953`
- `SessionSource` fields: `gateway/session.py:71-93`