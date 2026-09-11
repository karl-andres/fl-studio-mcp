"""_wait_for_response must tolerate a response file that is still being written."""

from __future__ import annotations

import json
import threading
import time

from fl_studio_mcp.utils.midi_connection import MIDIConnection


def test_partial_response_is_polled_until_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("FL_STUDIO_MCP_SETTINGS_DIR", str(tmp_path))
    conn = MIDIConnection()
    full = json.dumps({"success": True, "window": "piano_roll", "focused": True})
    conn._response_file.write_text(full[: len(full) // 2])  # FL is still writing

    def finish():
        time.sleep(0.15)
        conn._response_file.write_text(full)

    threading.Thread(target=finish, daemon=True).start()

    result = conn._wait_for_response(timeout=2.0)

    assert result == json.loads(full)
    assert not conn._response_file.exists()


def test_never_completed_response_reports_the_parse_problem(tmp_path, monkeypatch):
    monkeypatch.setenv("FL_STUDIO_MCP_SETTINGS_DIR", str(tmp_path))
    conn = MIDIConnection()
    conn._response_file.write_text('{"success": tr')

    result = conn._wait_for_response(timeout=0.3)

    assert result["success"] is False
    assert "never became readable" in result["error"]
