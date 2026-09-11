"""Piano Roll tools for FL Studio - persistent note placement.

This module provides tools for creating, editing, and deleting notes in
FL Studio's piano roll. Unlike MIDI real-time note triggering, these
tools create persistent notes by communicating with FL Studio's Piano Roll
scripting API via JSON files.

Communication flow:
1. MCP server writes requests to mcp_request.json
2. Keystroke trigger (Cmd+Opt+Y) executes FL Studio's ComposeWithLLM script
3. Script reads JSON, modifies piano roll, exports state to piano_roll_state.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fl_studio_mcp.utils.fl_trigger import get_trigger
from fl_studio_mcp.utils.midi_connection import get_fl_settings_base

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _get_fl_scripts_dir() -> Path:
    """Get the FL Studio Piano Roll scripts directory."""
    base = get_fl_settings_base()

    scripts_dir = base / "Piano roll scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def _get_request_file() -> Path:
    """Get the path to the MCP request JSON file."""
    return _get_fl_scripts_dir() / "mcp_request.json"


def _get_response_file() -> Path:
    """Get the path to the MCP response JSON file."""
    return _get_fl_scripts_dir() / "mcp_response.json"


def _get_state_file() -> Path:
    """Get the path to the piano roll state JSON file."""
    return _get_fl_scripts_dir() / "piano_roll_state.json"


def _write_request(request: dict | list) -> None:
    """Write a request to the MCP request file."""
    request_file = _get_request_file()

    # Read existing requests if any
    existing = []
    if request_file.exists():
        try:
            with open(request_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing = data
                elif isinstance(data, dict):
                    existing = [data]
        except (json.JSONDecodeError, IOError):
            existing = []

    # Append new request(s)
    if isinstance(request, list):
        existing.extend(request)
    else:
        existing.append(request)

    # Write back
    with open(request_file, "w") as f:
        json.dump(existing, f, indent=2)


def _clear_request_file() -> None:
    """Clear the request file."""
    request_file = _get_request_file()
    if request_file.exists():
        request_file.unlink()


def _read_state() -> dict | None:
    """Read the current piano roll state."""
    state_file = _get_state_file()
    if not state_file.exists():
        return None

    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# How long to wait for the piano roll script to consume a request and answer.
PR_SCRIPT_TIMEOUT = 5.0

# Shown whenever the trigger keystroke was sent but the script did not run.
PR_SCRIPT_NOT_RUN_HINT = (
    "The piano roll script did not run. Make sure a piano roll window is open in "
    "FL Studio and that ComposeWithLLM has been run once in this FL Studio session "
    "from the piano roll's Tools > Scripting menu (the trigger keystroke only "
    "re-runs the last script)."
)
PR_SCRIPT_QUEUED_HINT = (
    " The request is still queued and will be processed on the next successful "
    "trigger; cancel it with fl_clear_request_queue."
)


def _not_run_error() -> str:
    """Error text for a trigger that FL Studio ignored, mentioning queued requests."""
    if _load_request_queue():
        return PR_SCRIPT_NOT_RUN_HINT + PR_SCRIPT_QUEUED_HINT
    return PR_SCRIPT_NOT_RUN_HINT


def _load_request_queue() -> list[dict]:
    """Return the queued requests as a list (empty when the file is missing/invalid)."""
    request_file = _get_request_file()
    if not request_file.exists():
        return []
    try:
        with open(request_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and data.get("action"):
        return [data]
    return []


def _remove_queued_actions(action: str) -> int:
    """Drop every queued request with the given action; returns how many were removed."""
    queue = _load_request_queue()
    kept = [r for r in queue if r.get("action") != action]
    removed = len(queue) - len(kept)
    if removed:
        with open(_get_request_file(), "w") as f:
            json.dump(kept, f, indent=2)
    return removed


def _state_mtime() -> int | None:
    """Modification time of the state file in ns, or None when it does not exist."""
    try:
        return _get_state_file().stat().st_mtime_ns
    except OSError:
        return None


def _try_read_response() -> dict | None:
    """Read and remove the response file; None while it is absent or still being written."""
    response_file = _get_response_file()
    if not response_file.exists():
        return None
    try:
        data = json.loads(response_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None  # partial write or transient error - the caller retries
    try:
        response_file.unlink()
    except OSError:
        pass
    return data if isinstance(data, dict) else {"raw_response": data}


def _focus_piano_roll() -> str | None:
    """Make the piano roll FL's focused window before sending the trigger keystroke.

    Ctrl+Alt+Y only reaches the piano roll script while the piano roll is the
    focused window inside FL Studio; the OS-level window activation done by
    the trigger cannot guarantee that. Best effort: a missing MIDI bridge must
    not break the keystroke path. Returns the focused window's caption when
    the controller answered, else None.
    """
    from fl_studio_mcp.utils.connection import get_connection

    try:
        result = get_connection().send_command(
            "ui.showWindow", {"window": "piano_roll", "focus": True}, timeout=1.0
        )
    except Exception:  # noqa: BLE001 - best effort only
        return None
    if not result.get("success"):
        return None
    return result.get("focused_caption")


def _run_pr_script(timeout: float = PR_SCRIPT_TIMEOUT) -> dict:
    """Trigger the piano roll script and report what actually happened.

    The old behaviour slept for a fixed delay and reported success whenever the
    keystroke could be sent, even if nothing in FL Studio reacted. This waits
    for evidence instead: the script's response file or, failing that, the
    state export it always writes.

    Returns a dict with:
    - triggered: the keystroke was sent
    - ran: the script executed in FL Studio
    - response: the script's response dict (None when it processed nothing)
    - error: human-readable problem description, or None
    """
    trigger = get_trigger()
    if not trigger.is_supported:
        return {
            "triggered": False,
            "ran": False,
            "response": None,
            "error": (
                f"Auto-trigger not supported on {trigger.platform}. "
                f"Press {trigger.keystroke} in the piano roll manually."
            ),
        }

    # Remove a stale response BEFORE triggering: the script answers within
    # milliseconds, so deleting it after the keystroke would discard the
    # fresh answer.
    response_file = _get_response_file()
    if response_file.exists():
        try:
            response_file.unlink()
        except OSError:
            pass

    state_before = _state_mtime()
    # With a queued request the script always writes a response, so keep waiting
    # for it until the deadline; only an empty queue is proven by the state export.
    expect_response = bool(_load_request_queue())

    # FL applies ui.setFocused only while its window is the active OS window:
    # activate first, then focus the piano roll, then send the keystroke.
    if trigger.activate_window():
        _focus_piano_roll()

    if not trigger.trigger(delay=0.2):
        return {
            "triggered": False,
            "ran": False,
            "response": None,
            "error": (
                "Could not send the trigger keystroke to FL Studio (window not found?). "
                f"Press {trigger.keystroke} in the piano roll manually."
            ),
        }

    deadline = time.time() + timeout
    state_changed_at: float | None = None
    while time.time() < deadline:
        response = _try_read_response()
        if response is not None:
            return {"triggered": True, "ran": True, "response": response, "error": None}
        if state_changed_at is None and _state_mtime() != state_before:
            # The script exports the state before it writes the response;
            # give the response a short grace period, then accept the export
            # alone as proof (the script writes no response for an empty queue).
            state_changed_at = time.time()
        elif (
            state_changed_at is not None
            and not expect_response
            and time.time() - state_changed_at > 0.5
        ):
            return {"triggered": True, "ran": True, "response": None, "error": None}
        time.sleep(0.05)

    if state_changed_at is not None:
        return {"triggered": True, "ran": True, "response": None, "error": None}
    return {"triggered": True, "ran": False, "response": None, "error": _not_run_error()}


def _describe_run(run: dict) -> str:
    """Human-readable outcome of a _run_pr_script() result, as a sentence."""
    if not run["ran"]:
        return f"Warning: {run['error']}"
    response = run.get("response") or {}
    if response.get("status") == "error":
        return f"FL Studio ran the script but it reported an error: {response.get('message')}"
    added = response.get("notes_added")
    deleted = response.get("notes_deleted")
    if added is None and deleted is None:
        return "FL Studio ran the piano roll script."
    return f"FL Studio processed the request ({added or 0} note(s) added, {deleted or 0} deleted)."


def _enrich_pr_context(context: dict) -> dict:
    """Fill in what the piano roll runtime cannot report itself.

    The `channels` and `patterns` modules are normally not importable from a
    piano roll script, so the active pattern and the selected channel are
    fetched from the controller script over MIDI instead. A failing MIDI bridge
    must not hide the context the script did deliver.
    """
    from fl_studio_mcp.utils.connection import get_connection

    context.pop("selected_channel_error", None)
    context.pop("current_pattern_error", None)
    try:
        conn = get_connection()
        if "current_pattern" not in context:
            result = conn.send_command("patterns.getCurrent")
            if result.get("success") and result.get("index") is not None:
                context["current_pattern"] = {
                    "index": result.get("index"),
                    "name": result.get("name"),
                    "length_beats": result.get("length_beats"),
                }
        if "selected_channel" not in context:
            result = conn.send_command("channels.getSelected")
            channel = result.get("channel") if result.get("success") else None
            if channel:
                context["selected_channel"] = {
                    "index": channel.get("index"),
                    "name": channel.get("name"),
                }
    except Exception as e:  # noqa: BLE001 - keep the script's context regardless
        context["controller_error"] = str(e)
    try:
        focus = conn.send_command("ui.getFocus")
        if focus.get("success"):
            context["piano_roll_focused"] = bool(focus.get("focused", {}).get("piano_roll"))
            context["focused_caption"] = focus.get("caption")
    except Exception as e:  # noqa: BLE001
        context.setdefault("controller_error", str(e))
    context["note"] = (
        "selected_channel is the channel rack selection; an open piano roll does "
        "not follow it when selected via scripting, and FL does not report the "
        "piano roll's target channel. Call fl_open_piano_roll(channel) to make "
        "the piano roll target a specific channel before writing notes."
    )
    return context


def _midi_to_note_name(midi: int) -> str:
    """Convert MIDI note number to note name."""
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    note_name = note_names[midi % 12]
    octave = (midi // 12) - 1
    return f"{note_name}{octave}"


def _get_trigger_info(auto_trigger: bool) -> str:
    """Run the piano roll script (if requested) and return a status suffix."""
    if not auto_trigger:
        return ""
    return " " + _describe_run(_run_pr_script())


def register_piano_roll_tools(mcp: FastMCP) -> None:
    """Register piano roll tools with the MCP server."""

    @mcp.tool()
    def fl_send_notes(notes: list[dict], mode: str = "add", auto_trigger: bool = True) -> str:
        """Add or replace notes in the FL Studio piano roll.

        This creates persistent notes in the currently open piano roll pattern.
        Notes use quarter-note timing for simplicity.

        Args:
            notes: List of note objects with properties:
                   - midi (int): MIDI note number (60 = C4/Middle C)
                   - duration (float): Length in quarter notes (1.0 = quarter note)
                   - time (float, optional): Start position in quarter notes (default 0)
                   - velocity (float, optional): Velocity 0.0-1.0 (default 0.8)
            mode: "add" to add notes, "replace" to clear existing notes first
            auto_trigger: Whether to automatically trigger FL Studio (default True)

        Example notes:
            [
                {"midi": 60, "duration": 1.0, "time": 0},      # C4 quarter note at beat 0
                {"midi": 64, "duration": 1.0, "time": 0},      # E4 (chord with C4)
                {"midi": 67, "duration": 1.0, "time": 0},      # G4 (C major chord)
                {"midi": 60, "duration": 0.5, "time": 1.0},    # C4 eighth note at beat 1
            ]
        """
        if not notes:
            return "Error: No notes provided"

        # Validate notes
        for i, note in enumerate(notes):
            if "midi" not in note:
                return f"Error: Note {i} missing 'midi' field"
            if "duration" not in note:
                return f"Error: Note {i} missing 'duration' field"

            # Set defaults
            note.setdefault("time", 0)
            note.setdefault("velocity", 0.8)

        requests = []

        # If replace mode, clear first
        if mode == "replace":
            requests.append({"action": "clear"})

        # Add notes request
        requests.append({"action": "add_notes", "notes": notes})

        _write_request(requests)

        trigger_info = _get_trigger_info(auto_trigger)
        note_count = len(notes)
        note_summary = ", ".join(
            f"{_midi_to_note_name(n['midi'])}@{n.get('time', 0)}" for n in notes[:5]
        )
        if note_count > 5:
            note_summary += f", ... ({note_count - 5} more)"

        return f"Queued {note_count} note(s): {note_summary}.{trigger_info}"

    @mcp.tool()
    def fl_send_chord(
        midi_notes: list[int],
        time: float = 0,
        duration: float = 1.0,
        velocity: float = 0.8,
        auto_trigger: bool = True,
    ) -> str:
        """Add a chord (multiple simultaneous notes) to the FL Studio piano roll.

        This is a convenience function for adding multiple notes at the same time
        with the same duration. For more control, use fl_send_notes.

        Args:
            midi_notes: List of MIDI note numbers (e.g., [60, 64, 67] for C major)
            time: Start position in quarter notes (default 0)
            duration: Length in quarter notes for all notes (default 1.0)
            velocity: Velocity 0.0-1.0 for all notes (default 0.8)
            auto_trigger: Whether to automatically trigger FL Studio

        Example - C major chord at beat 0:
            fl_send_chord([60, 64, 67], time=0, duration=1.0)

        Example - Am7 chord at beat 2:
            fl_send_chord([57, 60, 64, 67], time=2, duration=2.0)
        """
        if not midi_notes:
            return "Error: No MIDI notes provided"

        # Build chord notes with velocity included
        chord_notes = [{"midi": midi, "velocity": velocity} for midi in midi_notes]

        request = {"action": "add_chord", "time": time, "duration": duration, "notes": chord_notes}

        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        note_names = ", ".join(_midi_to_note_name(n) for n in midi_notes)
        return f"Queued chord [{note_names}] at beat {time}, duration {duration}.{trigger_info}"

    @mcp.tool()
    def fl_delete_notes(notes: list[dict], auto_trigger: bool = True) -> str:
        """Delete specific notes from the FL Studio piano roll.

        Args:
            notes: List of notes to delete, matching by midi and time:
                   - midi (int): MIDI note number
                   - time (float): Start position in quarter notes
            auto_trigger: Whether to automatically trigger FL Studio

        Example:
            [{"midi": 60, "time": 0}, {"midi": 64, "time": 0}]
        """
        if not notes:
            return "Error: No notes specified for deletion"

        request = {"action": "delete_notes", "notes": notes}
        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        return f"Queued deletion of {len(notes)} note(s).{trigger_info}"

    @mcp.tool()
    def fl_clear_piano_roll(auto_trigger: bool = True) -> str:
        """Clear all notes from the FL Studio piano roll.

        Args:
            auto_trigger: Whether to automatically trigger FL Studio
        """
        request = {"action": "clear"}
        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        return f"Queued clear all notes.{trigger_info}"

    @mcp.tool()
    def fl_get_piano_roll_state() -> dict:
        """Get the current state of notes in the FL Studio piano roll.

        Returns a dictionary containing:
        - ppq: Pulses per quarter note (ticks per beat)
        - notes: List of all notes with their properties

        Note: This reads from the last exported state. Trigger FL Studio
        (Cmd+Opt+Y on macOS) to refresh the state file after making changes.
        """
        state = _read_state()

        if state is None:
            return {
                "error": "No piano roll state available. Make sure FL Studio's "
                "ComposeWithLLM script has been run at least once."
            }

        # Add human-readable note names
        if "notes" in state:
            for note in state["notes"]:
                if "midi" in note:
                    note["note_name"] = _midi_to_note_name(note["midi"])

        return state

    @mcp.tool()
    def fl_clear_request_queue() -> str:
        """Clear any pending note requests without executing them.

        Use this if you want to cancel queued changes before triggering FL Studio.
        """
        _clear_request_file()
        return "Request queue cleared."

    @mcp.tool()
    def fl_trigger_script() -> str:
        """Manually trigger FL Studio to process pending note requests.

        This sends the keystroke (Cmd+Opt+Y on macOS, Ctrl+Alt+Y on Windows)
        to FL Studio to execute the ComposeWithLLM piano roll script.
        """
        run = _run_pr_script()
        if not run["ran"]:
            return f"Error: {run['error']}"
        return _describe_run(run)

    @mcp.tool()
    def fl_get_pr_context() -> dict:
        """Get context of the currently open piano roll (read-only).

        Returns PPQ, time signature, note/marker counts, snap-to-scale info,
        timeline selection, the active pattern and the channel selected in the
        channel rack. Useful to verify WHERE notes would be written before
        using fl_send_notes - but note that an open piano roll does not follow
        channel selection made via scripting, only selection in the FL UI.

        Requires an open piano roll and, once per FL Studio session, a manual
        run of ComposeWithLLM from the piano roll's Tools > Scripting menu.
        """
        _write_request({"action": "get_context"})
        run = _run_pr_script()
        if not run["ran"]:
            # Do not let context requests pile up for the next successful trigger.
            _remove_queued_actions("get_context")
            if run["triggered"]:
                # The generic hint mentions the queue; this request is gone.
                return {"error": PR_SCRIPT_NOT_RUN_HINT}
            return {"error": run["error"]}

        response = run.get("response") or {}
        if response.get("status") == "error":
            return {"error": f"Piano roll script error: {response.get('message')}"}
        context = response.get("context")
        if not isinstance(context, dict):
            return {
                "error": (
                    "The piano roll script answered without context data. Update "
                    "ComposeWithLLM.pyscript in FL Studio's 'Piano roll scripts' "
                    "folder from this repository."
                ),
                "raw_response": response,
            }
        return _enrich_pr_context(context)

    @mcp.tool()
    def fl_get_piano_roll_info() -> dict:
        """Get information about the Piano Roll integration status.

        Returns platform info, file paths, and whether auto-triggering is supported.
        """
        trigger = get_trigger()

        return {
            "platform": trigger.platform,
            "auto_trigger_supported": trigger.is_supported,
            "trigger_keystroke": trigger.keystroke,
            "scripts_dir": str(_get_fl_scripts_dir()),
            "request_file": str(_get_request_file()),
            "state_file": str(_get_state_file()),
            "request_file_exists": _get_request_file().exists(),
            "state_file_exists": _get_state_file().exists(),
        }
