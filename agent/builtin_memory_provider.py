"""Minimal built-in memory provider compatibility module."""

from agent.memory_provider import MemoryProvider


class BuiltinMemoryProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "builtin"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        return None

    def get_tool_schemas(self) -> list:
        return []

    def handle_tool_call(self, tool_name, args, **kwargs):
        return ""

__all__ = ["BuiltinMemoryProvider"]
