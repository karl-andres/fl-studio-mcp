"""Server-side validation of the pattern and undo tools (no FL Studio needed)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.history import UNDO_FLAG_NAMES, register_history_tools
from fl_studio_mcp.tools.patterns import _index_error, register_pattern_tools


class NoConnection:
    """Any command reaching FL Studio is a test failure."""

    def send_command(self, action, params=None, timeout=2.0):
        raise AssertionError(f"unexpected command {action}")


class RecordingMCP:
    """Minimal stand-in for FastMCP: collects the functions passed to @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def tools(monkeypatch):
    import fl_studio_mcp.utils.connection as connection

    monkeypatch.setattr(connection, "get_connection", lambda: NoConnection())
    mcp = RecordingMCP()
    register_pattern_tools(mcp)
    register_history_tools(mcp)
    return mcp.tools


@pytest.mark.parametrize("index", [0, -1, True, "3"])
def test_index_error_rejects_non_positive_and_non_int(index):
    assert _index_error(index) is not None


def test_index_error_accepts_one_based_indices():
    assert _index_error(1) is None
    assert _index_error(42) is None


def test_pattern_tools_reject_bad_index_before_talking_to_fl(tools):
    assert tools["fl_select_pattern"](0).startswith("Error")
    assert tools["fl_rename_pattern"](-2, "Verse").startswith("Error")
    assert tools["fl_clone_pattern"](0).startswith("Error")


def test_save_undo_point_rejects_unknown_flags(tools):
    result = tools["fl_save_undo_point"](flags=["pr", "bogus"])

    assert "bogus" in result["error"]
    for name in UNDO_FLAG_NAMES:
        assert name in result["error"]


def test_save_undo_point_flags_default_only_when_omitted(monkeypatch):
    import fl_studio_mcp.utils.connection as connection

    sent = []

    class Recorder:
        def send_command(self, action, params=None, timeout=2.0):
            sent.append((action, params))
            return {"success": True, "saved": True}

    monkeypatch.setattr(connection, "get_connection", lambda: Recorder())
    mcp = RecordingMCP()
    register_history_tools(mcp)
    save = mcp.tools["fl_save_undo_point"]

    save()
    save(flags=[])
    save(flags="PR")

    assert sent[0][1]["flags"] == ["pr", "playlist", "knob", "ss_looping"]
    assert sent[1][1]["flags"] == [], "explicit empty list means flag mask 0"
    assert sent[2][1]["flags"] == ["pr"]
