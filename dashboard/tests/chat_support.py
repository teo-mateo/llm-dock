from chat.event_bus import EventBus


class FakeMcp:
    def get_all_tools(self, server_ids):
        return []

    def call_tool(self, *args, **kwargs):
        raise AssertionError("this test does not expect a tool call")

    def discover_bounded(self, server_id, timeout):
        return []


class UnusedRunManager:
    def __getattr__(self, name):
        raise AssertionError(f"this test does not expect run_manager.{name}")


def chat_parts(db, **overrides):
    parts = dict(
        db=db,
        mcp=FakeMcp(),
        run_manager=UnusedRunManager(),
        bus=EventBus(),
        services=lambda: [],
    )
    parts.update(overrides)
    return parts
