"""Server-side validation of the playlist and marker tools (no FL Studio needed)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.playlist import _track_error, register_playlist_tools
from fl_studio_mcp.utils.validation import rgb_error


class NoConnection:
    """Any command reaching FL Studio is a test failure."""

    def send_command(self, action, params=None, timeout=2.0):
        raise AssertionError(f"unexpected command {action}")


class Recorder:
    def __init__(self, response=None):
        self.sent = []
        self.response = response or {"success": True}

    def send_command(self, action, params=None, timeout=2.0):
        self.sent.append((action, params))
        return dict(self.response)


class RecordingMCP:
    """Minimal stand-in for FastMCP: collects the functions passed to @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _register(monkeypatch, conn):
    import fl_studio_mcp.utils.connection as connection

    monkeypatch.setattr(connection, "get_connection", lambda: conn)
    mcp = RecordingMCP()
    register_playlist_tools(mcp)
    return mcp.tools


@pytest.fixture
def offline_tools(monkeypatch):
    return _register(monkeypatch, NoConnection())


@pytest.mark.parametrize("track", [0, -1, True, "3"])
def test_track_error_rejects_non_positive_and_non_int(track):
    assert _track_error(track) is not None


def test_track_error_accepts_one_based_indices():
    assert _track_error(1) is None
    assert _track_error(500) is None


def test_playlist_tools_reject_bad_track_before_talking_to_fl(offline_tools):
    assert offline_tools["fl_set_playlist_track_name"](0, "Drums").startswith("Error")
    assert offline_tools["fl_mute_playlist_track"](-3).startswith("Error")
    assert offline_tools["fl_solo_playlist_track"](0).startswith("Error")
    assert offline_tools["fl_set_playlist_track_color"](0, 255, 0, 0).startswith("Error")


def test_add_marker_rejects_negative_time_before_talking_to_fl(offline_tools):
    assert offline_tools["fl_add_marker"]("Drop", -1.0).startswith("Error")
    assert offline_tools["fl_add_marker"]("Drop", True).startswith("Error")


def test_jump_to_marker_rejects_unknown_direction(offline_tools):
    assert offline_tools["fl_jump_to_marker"]("sideways").startswith("Error")


def test_add_marker_at_playhead_sends_none_time(monkeypatch):
    conn = Recorder({"success": True, "time_beats": 32.0})
    tools = _register(monkeypatch, conn)

    result = tools["fl_add_marker"]("Drop")

    assert conn.sent == [
        ("arrangement.addMarker", {"name": "Drop", "time_beats": None}),
    ]
    assert "Drop" in result


def test_mute_passes_explicit_state(monkeypatch):
    conn = Recorder({"success": True, "name": "Drums", "is_muted": True})
    tools = _register(monkeypatch, conn)

    result = tools["fl_mute_playlist_track"](3, muted=True)

    assert conn.sent == [("playlist.muteTrack", {"track": 3, "muted": True})]
    assert "muted" in result


@pytest.mark.parametrize("rgb", [(256, 0, 0), (0, -1, 0), (0, 0, True), (0, 1.5, 0), ("255", 0, 0)])
def test_rgb_error_rejects_out_of_range_and_non_int(rgb):
    assert rgb_error(*rgb) is not None


def test_rgb_error_accepts_byte_range():
    assert rgb_error(0, 128, 255) is None


def test_color_tools_reject_bad_rgb_before_talking_to_fl(offline_tools, monkeypatch):
    import fl_studio_mcp.utils.connection as connection
    from fl_studio_mcp.tools.channels import register_channel_tools
    from fl_studio_mcp.tools.mixer import register_mixer_tools

    monkeypatch.setattr(connection, "get_connection", lambda: NoConnection())
    mcp = RecordingMCP()
    register_channel_tools(mcp)
    register_mixer_tools(mcp)

    assert offline_tools["fl_set_playlist_track_color"](1, 300, 0, 0).startswith("Error")
    assert mcp.tools["fl_set_channel_color"](0, 0, 0, 256).startswith("Error")
    assert mcp.tools["fl_set_track_color"](1, -1, 0, 0).startswith("Error")
