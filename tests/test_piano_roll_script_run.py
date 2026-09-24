"""Tests for the piano roll script round-trip helpers.

The FL Studio side is simulated by a fake trigger that writes the files the
ComposeWithLLM script would write. All file paths are redirected to a temp
directory via FL_STUDIO_MCP_SETTINGS_DIR.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from fl_studio_mcp.tools import piano_roll


class FakeTrigger:
    """Stands in for FLStudioTrigger; runs `on_trigger` instead of a keystroke."""

    is_supported = True
    platform = "TestOS"
    keystroke = "Ctrl+Alt+Y"

    def __init__(self, on_trigger=None, send_ok=True):
        self.on_trigger = on_trigger
        self.send_ok = send_ok
        self.calls = 0

    def activate_window(self):
        self.activations = getattr(self, "activations", 0) + 1
        return True

    def trigger(self, delay=0.0):
        self.calls += 1
        if not self.send_ok:
            return False
        if self.on_trigger:
            self.on_trigger()
        return True


@pytest.fixture
def scripts_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FL_STUDIO_MCP_SETTINGS_DIR", str(tmp_path))
    return tmp_path / "Piano roll scripts"


def install_trigger(monkeypatch, trigger):
    monkeypatch.setattr(piano_roll, "get_trigger", lambda: trigger)
    # The pre-trigger focus step talks to FL over MIDI; keep it out of the tests.
    monkeypatch.setattr(piano_roll, "_focus_piano_roll", lambda: None)
    return trigger


def script_run(scripts_dir, response=None, consume=True, export_state=True):
    """Simulate one execution of ComposeWithLLM.pyscript."""
    if consume:
        (scripts_dir / "mcp_request.json").write_text("[]")
    if export_state:
        (scripts_dir / "piano_roll_state.json").write_text(
            json.dumps({"ppq": 96, "noteCount": 0, "notes": []})
        )
    if response is not None:
        (scripts_dir / "mcp_response.json").write_text(json.dumps(response))


def test_run_reports_processed_request(scripts_dir, monkeypatch):
    piano_roll._write_request({"action": "add_notes", "notes": [{"midi": 60, "duration": 1}]})
    response = {"status": "success", "requests_processed": 1, "notes_added": 1, "notes_deleted": 0}
    install_trigger(monkeypatch, FakeTrigger(lambda: script_run(scripts_dir, response)))

    run = piano_roll._run_pr_script(timeout=1.0)

    assert run["ran"] is True
    assert run["response"] == response
    assert run["error"] is None
    assert not (scripts_dir / "mcp_response.json").exists(), "response is consumed"
    assert "1 note(s) added" in piano_roll._describe_run(run)


def test_run_detects_script_that_did_not_run(scripts_dir, monkeypatch):
    piano_roll._write_request({"action": "get_context"})
    trigger = install_trigger(monkeypatch, FakeTrigger())  # keystroke sent, FL ignores it

    run = piano_roll._run_pr_script(timeout=0.3)

    assert trigger.calls == 1
    assert run["triggered"] is True
    assert run["ran"] is False
    assert "did not run" in run["error"]
    assert piano_roll._load_request_queue() == [{"action": "get_context"}], "request stays queued"
    assert piano_roll._describe_run(run).startswith("Warning:")


def test_run_reports_failed_keystroke(scripts_dir, monkeypatch):
    install_trigger(monkeypatch, FakeTrigger(send_ok=False))

    run = piano_roll._run_pr_script(timeout=0.3)

    assert run["triggered"] is False
    assert run["ran"] is False
    assert "Could not send the trigger keystroke" in run["error"]


def test_state_export_alone_proves_the_script_ran(scripts_dir, monkeypatch):
    # An empty queue makes the script write no response, only the state export.
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "piano_roll_state.json").write_text("{}")
    time.sleep(0.01)
    install_trigger(monkeypatch, FakeTrigger(lambda: script_run(scripts_dir, consume=False)))

    run = piano_roll._run_pr_script(timeout=2.0)

    assert run["ran"] is True
    assert run["response"] is None
    assert piano_roll._describe_run(run) == "FL Studio ran the piano roll script."


def test_stale_response_is_removed_before_triggering(scripts_dir, monkeypatch):
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "mcp_response.json").write_text(json.dumps({"status": "success", "stale": True}))
    install_trigger(monkeypatch, FakeTrigger())

    run = piano_roll._run_pr_script(timeout=0.3)

    assert run["ran"] is False, "a stale response must not count as an answer"
    assert not (scripts_dir / "mcp_response.json").exists()


def test_partially_written_response_is_retried(scripts_dir, monkeypatch):
    scripts_dir.mkdir(parents=True)
    response_file = scripts_dir / "mcp_response.json"
    full = json.dumps({"status": "success", "notes_added": 3, "notes_deleted": 0})

    def slow_writer():
        response_file.write_text(full[: len(full) // 2])  # FL is still writing...

        def finish():
            time.sleep(0.15)
            response_file.write_text(full)

        threading.Thread(target=finish, daemon=True).start()

    install_trigger(monkeypatch, FakeTrigger(slow_writer))

    run = piano_roll._run_pr_script(timeout=2.0)

    assert run["ran"] is True
    assert run["response"]["notes_added"] == 3


def test_remove_queued_actions_keeps_other_requests(scripts_dir):
    piano_roll._write_request(
        [{"action": "get_context"}, {"action": "add_notes", "notes": []}, {"action": "get_context"}]
    )

    removed = piano_roll._remove_queued_actions("get_context")

    assert removed == 2
    assert piano_roll._load_request_queue() == [{"action": "add_notes", "notes": []}]


def test_enrich_pr_context_uses_controller_and_strips_script_errors(monkeypatch):
    class FakeConnection:
        def send_command(self, action, params=None, timeout=2.0):
            if action == "patterns.getCurrent":
                return {"success": True, "index": 3, "name": "Verse 1", "length_beats": 32}
            if action == "channels.getSelected":
                return {"success": True, "channel": {"index": 1, "name": "TruePianos", "pan": 0}}
            if action == "ui.getFocus":
                return {"success": True, "caption": "Piano roll -", "focused": {"piano_roll": True}}
            raise AssertionError(action)

    import fl_studio_mcp.utils.connection as connection

    monkeypatch.setattr(connection, "get_connection", lambda: FakeConnection())
    context = {
        "ppq": 96,
        "selected_channel_error": "No module named 'channels'",
        "current_pattern_error": "No module named 'patterns'",
    }

    enriched = piano_roll._enrich_pr_context(context)

    assert enriched["current_pattern"] == {"index": 3, "name": "Verse 1", "length_beats": 32}
    assert enriched["selected_channel"] == {"index": 1, "name": "TruePianos"}
    assert "selected_channel_error" not in enriched
    assert "current_pattern_error" not in enriched
    assert enriched["piano_roll_focused"] is True
    assert enriched["focused_caption"] == "Piano roll -"
    assert "fl_open_piano_roll" in enriched["note"]


def test_enrich_pr_context_survives_missing_midi_bridge(monkeypatch):
    import fl_studio_mcp.utils.connection as connection

    def broken():
        raise RuntimeError("MIDI port not found")

    monkeypatch.setattr(connection, "get_connection", broken)

    enriched = piano_roll._enrich_pr_context({"ppq": 96})

    assert enriched["ppq"] == 96
    assert "MIDI port not found" in enriched["controller_error"]


def test_queued_request_waits_for_a_late_response(scripts_dir, monkeypatch):
    # State export first, response noticeably later (slow FL): the response
    # must still be picked up instead of returning a state-only result.
    piano_roll._write_request({"action": "add_notes", "notes": [{"midi": 60, "duration": 1}]})
    response = {"status": "success", "requests_processed": 1, "notes_added": 1, "notes_deleted": 0}

    def slow_script():
        script_run(scripts_dir, consume=True, export_state=True)

        def finish():
            time.sleep(0.9)
            (scripts_dir / "mcp_response.json").write_text(json.dumps(response))

        threading.Thread(target=finish, daemon=True).start()

    install_trigger(monkeypatch, FakeTrigger(slow_script))

    run = piano_roll._run_pr_script(timeout=3.0)

    assert run["ran"] is True
    assert run["response"] == response


def test_focus_step_runs_before_the_keystroke(scripts_dir, monkeypatch):
    order = []

    class OrderedTrigger(FakeTrigger):
        def activate_window(self):
            order.append("activate")
            return True

    monkeypatch.setattr(
        piano_roll, "get_trigger", lambda: OrderedTrigger(lambda: order.append("key"))
    )
    monkeypatch.setattr(piano_roll, "_focus_piano_roll", lambda: order.append("focus"))

    piano_roll._run_pr_script(timeout=0.2)

    assert order == ["activate", "focus", "key"]


def test_focus_step_is_skipped_when_fl_window_cannot_be_activated(scripts_dir, monkeypatch):
    order = []

    class NoWindowTrigger(FakeTrigger):
        def activate_window(self):
            return False

    monkeypatch.setattr(
        piano_roll, "get_trigger", lambda: NoWindowTrigger(lambda: order.append("key"))
    )
    monkeypatch.setattr(piano_roll, "_focus_piano_roll", lambda: order.append("focus"))

    piano_roll._run_pr_script(timeout=0.2)

    assert order == ["key"]


def test_focus_helper_survives_missing_midi_bridge(monkeypatch):
    import fl_studio_mcp.utils.connection as connection

    def broken():
        raise RuntimeError("no MIDI port")

    monkeypatch.setattr(connection, "get_connection", broken)

    assert piano_roll._focus_piano_roll() is None
