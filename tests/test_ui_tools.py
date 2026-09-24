"""Window/focus tools: caption parsing and input validation (no FL Studio needed)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.ui import register_ui_tools


class RecordingMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeConnection:
    def __init__(self):
        self.sent = []

    def send_command(self, action, params=None, timeout=2.0):
        self.sent.append((action, params))
        if action == "pianoroll.open":
            return {
                "success": True,
                "focused": True,
                "focused_caption": "Piano roll -",
                "channel": {"index": params.get("index"), "name": "808 Sub"},
            }
        return {"success": True}


@pytest.fixture
def env(monkeypatch):
    import fl_studio_mcp.utils.connection as connection

    conn = FakeConnection()
    monkeypatch.setattr(connection, "get_connection", lambda: conn)
    mcp = RecordingMCP()
    register_ui_tools(mcp)
    return mcp.tools, conn


def test_open_piano_roll_reports_target_channel(env):
    tools, conn = env

    result = tools["fl_open_piano_roll"](4)

    assert conn.sent == [("pianoroll.open", {"index": 4})]
    assert result["channel"] == {"index": 4, "name": "808 Sub"}
    assert result["focused"] is True


def test_open_piano_roll_without_channel_keeps_target(env):
    tools, conn = env

    tools["fl_open_piano_roll"]()

    assert conn.sent == [("pianoroll.open", {})]


def test_open_piano_roll_rejects_negative_channel(env):
    tools, conn = env

    assert "error" in tools["fl_open_piano_roll"](-1)
    assert conn.sent == []


def test_window_tools_reject_unknown_window(env):
    tools, conn = env

    assert "error" in tools["fl_show_window"]("mixr")
    assert "error" in tools["fl_focus_window"]("timeline")
    assert conn.sent == []
