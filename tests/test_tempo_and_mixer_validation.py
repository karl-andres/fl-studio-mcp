"""Server-side validation of the tempo and mixer routing tools (no FL Studio needed)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.mixer import register_mixer_tools
from fl_studio_mcp.tools.transport import register_transport_tools


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
    register_transport_tools(mcp)
    register_mixer_tools(mcp)
    return mcp.tools


@pytest.fixture
def offline_tools(monkeypatch):
    return _register(monkeypatch, NoConnection())


@pytest.mark.parametrize("bpm", [9.9, 522.1, 0, -140, True])
def test_set_tempo_rejects_out_of_range_before_talking_to_fl(offline_tools, bpm):
    assert offline_tools["fl_set_tempo"](bpm).startswith("Error")


def test_set_tempo_sends_valid_bpm(monkeypatch):
    conn = Recorder({"success": True, "bpm": 104.0})
    tools = _register(monkeypatch, conn)

    result = tools["fl_set_tempo"](104)

    assert conn.sent == [("transport.setTempo", {"bpm": 104})]
    assert "104" in result


def test_route_track_rejects_self_route_before_talking_to_fl(offline_tools):
    assert offline_tools["fl_route_track"](5, 5).startswith("Error")


def test_route_track_sends_route_command(monkeypatch):
    conn = Recorder({"success": True, "active": True})
    tools = _register(monkeypatch, conn)

    result = tools["fl_route_track"](3, 10)

    assert conn.sent == [
        ("mixer.routeTo", {"source": 3, "dest": 10, "enabled": True}),
    ]
    assert "active" in result


def test_get_track_peaks_picks_single_or_all_command(monkeypatch):
    conn = Recorder({"success": True, "peaks": []})
    tools = _register(monkeypatch, conn)

    tools["fl_get_track_peaks"]()
    tools["fl_get_track_peaks"](track=0)

    assert conn.sent[0][0] == "mixer.getAllPeaks"
    assert conn.sent[1] == ("mixer.getPeaks", {"track": 0})


def test_get_track_peaks_strips_success_key(monkeypatch):
    conn = Recorder({"success": True, "track": 0, "left": 0.5, "right": 0.4, "clipping": False})
    tools = _register(monkeypatch, conn)

    result = tools["fl_get_track_peaks"](track=0)

    assert "success" not in result
    assert result["left"] == 0.5


def test_set_metronome_passes_explicit_state_and_toggle(monkeypatch):
    conn = Recorder({"success": True, "metronome": True})
    tools = _register(monkeypatch, conn)

    result = tools["fl_set_metronome"](enabled=True)
    tools["fl_set_metronome"]()

    assert conn.sent == [
        ("transport.setMetronome", {"enabled": True}),
        ("transport.setMetronome", {"enabled": None}),
    ]
    assert "on" in result


def test_project_snapshot_strips_success_and_keeps_sections(monkeypatch):
    conn = Recorder({
        "success": True,
        "tempo_bpm": 130.0,
        "transport": {"is_playing": False},
        "patterns": {"error": "patterns module not available"},
        "metronome": False,
    })
    tools = _register(monkeypatch, conn)

    result = tools["fl_project_snapshot"]()

    assert "success" not in result
    assert result["tempo_bpm"] == 130.0
    assert result["patterns"]["error"].startswith("patterns module")
