# name=FL Studio MCP Controller
# url=https://github.com/karl-andres/fl-studio-mcp
# supportedDevices=FL Studio MCP

"""
FL Studio MIDI Controller Script for MCP Integration.

This script runs inside FL Studio and receives MIDI trigger messages from the
MCP server. When triggered, it reads a command from a JSON file, executes the
corresponding FL Studio API function, and writes the response to another JSON file.

Communication flow:
1. MCP server writes command to mcp_command.json
2. MCP server sends MIDI note 127 (trigger)
3. This script receives the trigger via OnMidiMsg()
4. Script reads command JSON, executes FL Studio API
5. Script writes response to mcp_response.json
6. MCP server reads response
"""

import json
import os
import sys
from pathlib import Path

# FL Studio API modules (available when running inside FL Studio)
import channels
import midi
import mixer
import plugins
import transport


def _get_script_dir() -> Path:
    """Get the script directory path.

    FL Studio's Python environment doesn't support __file__, so we construct
    the path based on the platform's standard FL Studio settings location.
    """
    if sys.platform == "darwin":
        # macOS
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    elif sys.platform == "win32":
        # Windows
        userprofile = os.environ.get("USERPROFILE", "~")
        base = Path(userprofile) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        # Linux (unlikely but handle it)
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"

    return base / "Hardware" / "FLStudioMCP"


# File paths for JSON communication
SCRIPT_DIR = _get_script_dir()
COMMAND_FILE = SCRIPT_DIR / "mcp_command.json"
RESPONSE_FILE = SCRIPT_DIR / "mcp_response.json"

# MIDI trigger note
TRIGGER_NOTE = 127


def OnInit():
    """Called when the script is loaded."""
    print("FL Studio MCP Controller initialized")
    print(f"Command file: {COMMAND_FILE}")
    print(f"Response file: {RESPONSE_FILE}")


def OnDeInit():
    """Called when the script is unloaded."""
    print("FL Studio MCP Controller deinitialized")


def OnMidiMsg(event):
    """Called when a MIDI message is received."""
    # Check for trigger note (Note On, note 127)
    if event.midiId == 0x90 and event.data1 == TRIGGER_NOTE and event.data2 > 0:
        execute_pending_command()
        event.handled = True


def OnIdle():
    """Called periodically when FL Studio is idle."""
    pass  # Required FL Studio API hook; no polling needed


def execute_pending_command():
    """Read command from JSON file, execute it, and write response."""
    response = {"success": False, "error": None}

    try:
        # Read command file
        if not COMMAND_FILE.exists():
            response["error"] = "No command file found"
            write_response(response)
            return

        command_text = COMMAND_FILE.read_text()
        command = json.loads(command_text)

        action = command.get("action", "")
        params = command.get("params", {})

        # Execute command and get result
        result = dispatch_command(action, params)
        # A handler that returns {"error": ...} has failed; do not mark it a success.
        response = {"success": not result.get("error"), **result}

    except json.JSONDecodeError as e:
        response["error"] = f"Invalid JSON in command file: {e}"
    except Exception as e:
        response["error"] = f"Error executing command: {e}"

    write_response(response)


# ---------------------------------------------------------------------------
# Pattern management (requires newer FL Studio, lazy-imported)
# ---------------------------------------------------------------------------

def _patterns_mod():
    """Lazily import the patterns module (not available on older FL versions)."""
    import patterns  # noqa: PLC0415
    return patterns


def _ui_mod():
    """Lazily import the ui module."""
    import ui  # noqa: PLC0415
    return ui


# FL window indices (midi.wid* constants) by the names the MCP tools accept.
_WINDOWS = {
    "mixer": 0,
    "channel_rack": 1,
    "playlist": 2,
    "piano_roll": 3,
    "browser": 4,
}


def _window_index(params: dict) -> int:
    """Resolve the 'window' parameter (name or index) to an FL window index."""
    window = params.get("window", "piano_roll")
    if isinstance(window, int) and not isinstance(window, bool):
        return window
    index = _WINDOWS.get(str(window).lower())
    if index is None:
        raise ValueError("Unknown window '%s'. Valid: %s" % (window, ", ".join(_WINDOWS)))
    return index


def _window_report(ui, index: int) -> dict:
    """Visibility/focus of one window plus the caption of whatever is focused."""
    name = next((n for n, i in _WINDOWS.items() if i == index), str(index))
    return {
        "window": name,
        "visible": bool(ui.getVisible(index)),
        "focused": bool(ui.getFocused(index)),
        "focused_caption": ui.getFocusedFormCaption(),
    }


def handle_ui_get_focus(params: dict) -> dict:
    """Report which FL windows are visible/focused and the focused window's caption.

    The caption of a focused piano roll is "Piano roll - <channel name>", which
    is the only way to learn which channel an open piano roll targets.
    """
    try:
        ui = _ui_mod()
        return {
            "focused": {n: bool(ui.getFocused(i)) for n, i in _WINDOWS.items()},
            "visible": {n: bool(ui.getVisible(i)) for n, i in _WINDOWS.items()},
            "caption": ui.getFocusedFormCaption(),
            "form_id": ui.getFocusedFormID(),
            "plugin": ui.getFocusedPluginName(),
        }
    except Exception as e:
        return {"error": str(e)}


def handle_ui_show_window(params: dict) -> dict:
    """Show an FL window and (by default) give it FL-internal focus."""
    try:
        ui = _ui_mod()
        index = _window_index(params)
        ui.showWindow(index)
        if params.get("focus", True):
            ui.setFocused(index)
        return _window_report(ui, index)
    except Exception as e:
        return {"error": str(e)}


def handle_ui_hide_window(params: dict) -> dict:
    """Hide an FL window."""
    try:
        ui = _ui_mod()
        index = _window_index(params)
        ui.hideWindow(index)
        return _window_report(ui, index)
    except Exception as e:
        return {"error": str(e)}


def handle_ui_set_focus(params: dict) -> dict:
    """Give an FL window FL-internal focus (without changing its visibility)."""
    try:
        ui = _ui_mod()
        index = _window_index(params)
        ui.setFocused(index)
        return _window_report(ui, index)
    except Exception as e:
        return {"error": str(e)}


def handle_pianoroll_open(params: dict) -> dict:
    """Retarget the piano roll to a channel and make it FL's focused window.

    An open piano roll ignores channels selected via scripting, and merely
    showing/focusing it does not help either. What does work (verified against
    FL 2026): hide the piano roll, select the channel, show it again - a
    freshly shown piano roll picks up the selected channel. Without "index"
    the piano roll is only shown and focused, its target is left alone.
    """
    try:
        ui = _ui_mod()
        pr = _WINDOWS["piano_roll"]
        index = params.get("index")
        if index is not None:
            index = int(index)
            if index < 0 or index >= channels.channelCount(True):
                return {"error": "Channel index %d out of range (0..%d)"
                        % (index, channels.channelCount(True) - 1)}
            ui.hideWindow(pr)
            channels.selectOneChannel(index, True)
        ui.showWindow(pr)
        ui.setFocused(pr)
        report = _window_report(ui, _WINDOWS["piano_roll"])
        if index is not None:
            report["channel"] = {"index": index, "name": channels.getChannelName(index, True)}
        return report
    except Exception as e:
        return {"error": str(e)}


def _pattern_index_error(patterns, index: int) -> dict | None:
    """Return an error dict for indices outside 1..patternMax, else None.

    FL silently creates or selects unexpected patterns for out-of-range
    indices instead of failing, so validate before calling into the API.
    """
    max_index = patterns.patternMax()
    if index < 1 or index > max_index:
        return {"error": f"Pattern index {index} out of range (1..{max_index})"}
    return None


def handle_patterns_get_count(params: dict) -> dict:
    try:
        patterns = _patterns_mod()
        return {
            "count": patterns.patternCount(),
            "current": patterns.patternNumber(),
            "max": patterns.patternMax(),
        }
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_get_all(params: dict) -> dict:
    try:
        patterns = _patterns_mod()
        include_default = params.get("include_default", False)
        max_index = patterns.patternMax()
        out = []
        for i in range(1, max_index + 1):
            is_default = patterns.isPatternDefault(i)
            if is_default and not include_default:
                continue
            out.append({
                "index": i,
                "name": patterns.getPatternName(i),
                "color": patterns.getPatternColor(i),
                "length_beats": patterns.getPatternLength(i),
                "is_default": is_default,
                "is_selected": patterns.isPatternSelected(i),
            })
        return {"patterns": out, "current": patterns.patternNumber()}
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_get_current(params: dict) -> dict:
    try:
        patterns = _patterns_mod()
        i = patterns.patternNumber()
        return {
            "index": i,
            "name": patterns.getPatternName(i),
            "length_beats": patterns.getPatternLength(i),
        }
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_select(params: dict) -> dict:
    try:
        patterns = _patterns_mod()
        index = int(params.get("index", 0))
        error = _pattern_index_error(patterns, index)
        if error:
            return error
        patterns.jumpToPattern(index)
        return {"selected": index, "name": patterns.getPatternName(index)}
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_new_empty(params: dict) -> dict:
    """Select the first/next empty pattern (automation-safe: no name prompt).

    Note: patterns are virtual in FL; this jumps to an unused one, which is
    the closest equivalent to "create new pattern".
    """
    try:
        patterns = _patterns_mod()
        FFNEP_DontPromptName = 1 << 1  # from midi module flags
        patterns.findFirstNextEmptyPat(FFNEP_DontPromptName)
        i = patterns.patternNumber()
        return {"selected": i, "name": patterns.getPatternName(i)}
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_clone(params: dict) -> dict:
    """Clone a pattern. NOTE: this closes the piano roll (FL behaviour)."""
    try:
        patterns = _patterns_mod()
        index = params.get("index")
        if index is None:
            patterns.clonePattern()
            new_index = patterns.patternNumber()
        else:
            error = _pattern_index_error(patterns, int(index))
            if error:
                return error
            patterns.clonePattern(int(index))
            new_index = patterns.patternNumber()
        return {"cloned_to": new_index, "name": patterns.getPatternName(new_index)}
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


def handle_patterns_set_name(params: dict) -> dict:
    try:
        patterns = _patterns_mod()
        index = int(params.get("index", 0))
        name = str(params.get("name", ""))
        error = _pattern_index_error(patterns, index)
        if error:
            return error
        patterns.setPatternName(index, name)
        return {"index": index, "name": patterns.getPatternName(index)}
    except ImportError:
        return {"error": "patterns module not available (requires FL Studio 2024+)"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Undo / redo safety net
# ---------------------------------------------------------------------------

def _general_mod():
    import general  # noqa: PLC0415
    return general


def _midi_mod():
    import midi  # noqa: PLC0415
    return midi


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------

# FL Studio's own tempo bounds (the BPM field clamps to this range).
TEMPO_MIN = 10.0
TEMPO_MAX = 522.0


def _current_bpm() -> float:
    """Current tempo in BPM, whatever unit this FL version reports.

    getCurrentTempo returns plain BPM on some FL versions and BPM*1000 on
    others; BPM*1000 is always >= 10000 while plain BPM tops out at 522.
    """
    raw = mixer.getCurrentTempo(0)
    return raw / 1000.0 if raw >= 10000 else float(raw)


def handle_transport_get_tempo() -> dict:
    """Get the current project tempo in BPM."""
    return {"bpm": _current_bpm()}


def handle_transport_set_tempo(params: dict) -> dict:
    """Set the project tempo in BPM via a REC event (the only scriptable way)."""
    bpm = params.get("bpm")
    if bpm is None:
        return {"error": "bpm is required"}
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        return {"error": "bpm must be a number"}
    if not TEMPO_MIN <= bpm <= TEMPO_MAX:
        return {"error": "bpm must be between %s and %s" % (TEMPO_MIN, TEMPO_MAX)}
    try:
        general = _general_mod()
        midi_mod = _midi_mod()
        general.processRECEvent(
            midi_mod.REC_Tempo,
            int(round(bpm * 1000)),
            midi_mod.REC_Control | midi_mod.REC_UpdateControl,
        )
        return {"bpm": _current_bpm()}
    except ImportError:
        return {"error": "general/midi module not available"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Mixer peaks, routing and insert slots
# ---------------------------------------------------------------------------

def _track_error(track):
    if isinstance(track, bool) or not isinstance(track, int):
        return "track must be an integer"
    if not 0 <= track < mixer.trackCount():
        return "track %s out of range 0..%s" % (track, mixer.trackCount() - 1)
    return None


def handle_mixer_get_peaks(params: dict) -> dict:
    """Get the current output peak levels of one mixer track (playback only)."""
    track = params.get("track", 0)
    err = _track_error(track)
    if err:
        return {"error": err}
    left = mixer.getTrackPeaks(track, 0)
    right = mixer.getTrackPeaks(track, 1)
    return {
        "track": track,
        "name": mixer.getTrackName(track),
        "left": left,
        "right": right,
        "clipping": left > 1.0 or right > 1.0,
    }


def handle_mixer_get_all_peaks(params: dict) -> dict:
    """Get peak levels of every track currently producing signal."""
    threshold = params.get("threshold", 0.0001)
    peaks = []
    for i in range(mixer.trackCount()):
        left = mixer.getTrackPeaks(i, 0)
        right = mixer.getTrackPeaks(i, 1)
        if left > threshold or right > threshold:
            peaks.append({
                "track": i,
                "name": mixer.getTrackName(i),
                "left": left,
                "right": right,
                "clipping": left > 1.0 or right > 1.0,
            })
    return {"peaks": peaks, "is_playing": transport.isPlaying() == 1}


def handle_mixer_route_to(params: dict) -> dict:
    """Enable or disable a send from one mixer track to another."""
    source = params.get("source")
    dest = params.get("dest")
    enabled = params.get("enabled", True)
    for name, value in (("source", source), ("dest", dest)):
        err = _track_error(value)
        if err:
            return {"error": "%s: %s" % (name, err)}
    if source == dest:
        return {"error": "source and dest must differ"}
    mixer.setRouteTo(source, dest, 1 if enabled else 0)
    mixer.afterRoutingChanged()
    return {
        "source": source,
        "dest": dest,
        "active": mixer.getRouteSendActive(source, dest) == 1,
    }


def handle_mixer_get_routing(params: dict) -> dict:
    """List the destination tracks a mixer track sends to."""
    track = params.get("track", 0)
    err = _track_error(track)
    if err:
        return {"error": err}
    routes = [
        {"track": i, "name": mixer.getTrackName(i)}
        for i in range(mixer.trackCount())
        if i != track and mixer.getRouteSendActive(track, i) == 1
    ]
    return {"track": track, "name": mixer.getTrackName(track), "routes_to": routes}


def handle_mixer_get_track_slots(params: dict) -> dict:
    """List the effect plugins loaded in a mixer track's 10 insert slots."""
    track = params.get("track", 0)
    err = _track_error(track)
    if err:
        return {"error": err}
    slots = []
    for slot in range(10):
        try:
            if plugins.isValid(track, slot, True) == 1:
                slots.append({
                    "slot": slot,
                    "name": plugins.getPluginName(track, slot, True),
                })
        except Exception:
            continue
    return {"track": track, "name": mixer.getTrackName(track), "slots": slots}


# ---------------------------------------------------------------------------
# Metronome
# ---------------------------------------------------------------------------

def handle_transport_set_metronome(params: dict) -> dict:
    """Enable, disable or toggle the metronome (globalTransport can only toggle)."""
    try:
        ui = _ui_mod()
        midi_mod = _midi_mod()
        enabled = params.get("enabled")
        current = ui.isMetronomeEnabled() == 1
        if enabled is None or current != bool(enabled):
            transport.globalTransport(midi_mod.FPT_Metronome, 1)
            # FL applies the toggle asynchronously; re-reading here races and
            # can report the old state, so return the computed one.
            current = not current
        return {"metronome": current}
    except ImportError:
        return {"error": "ui/midi module not available"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Project snapshot: the whole project state in one MIDI round-trip
# ---------------------------------------------------------------------------

def handle_project_get_snapshot(params: dict) -> dict:
    """Aggregate project state by reusing the individual handlers.

    Sections that need modules missing on older FL versions degrade to an
    inline {"error": ...} instead of failing the whole snapshot.
    """
    snapshot = {
        "tempo_bpm": _current_bpm(),
        "transport": handle_transport_get_status(),
        "patterns": handle_patterns_get_all({}),
        "channels": handle_channels_get_all(),
        "mixer_tracks": handle_mixer_get_all_tracks({"include_empty": False}),
        "playlist_tracks": handle_playlist_get_tracks({}),
        "markers": handle_arrangement_get_markers({}),
        "undo": handle_general_get_undo_status({}),
    }
    # Insert effects for every named mixer track (in-process, no extra trips).
    tracks = snapshot["mixer_tracks"].get("tracks") or []
    fx = {}
    for t in tracks:
        index = t.get("index")
        if index is None:
            continue
        slots = handle_mixer_get_track_slots({"track": index}).get("slots") or []
        if slots:
            fx[str(index)] = slots
    snapshot["mixer_fx_slots"] = fx
    try:
        ui = _ui_mod()
        snapshot["metronome"] = ui.isMetronomeEnabled() == 1
    except Exception:
        snapshot["metronome"] = None
    return snapshot


# ---------------------------------------------------------------------------
# Playlist tracks and arrangement markers (lazy imports)
# ---------------------------------------------------------------------------

def _playlist_mod():
    import playlist  # noqa: PLC0415
    return playlist


def _arrangement_mod():
    import arrangement  # noqa: PLC0415
    return arrangement


def _playlist_track_error(pl, track):
    """Playlist tracks are 1-based, unlike mixer tracks and channels."""
    if isinstance(track, bool) or not isinstance(track, int):
        return "track must be an integer"
    if not 1 <= track <= pl.trackCount():
        return "track %s out of range 1..%s" % (track, pl.trackCount())
    return None


def handle_playlist_get_tracks(params: dict) -> dict:
    """List playlist tracks. By default only tracks changed from stock state."""
    include_default = params.get("include_default", False)
    try:
        pl = _playlist_mod()
        tracks = []
        for i in range(1, pl.trackCount() + 1):
            name = pl.getTrackName(i)
            muted = pl.isTrackMuted(i) == 1
            solo = pl.isTrackSolo(i) == 1
            is_default = name == "Track %d" % i and not muted and not solo
            if is_default and not include_default:
                continue
            tracks.append({
                "index": i,
                "name": name,
                "color": pl.getTrackColor(i),
                "is_muted": muted,
                "is_solo": solo,
            })
        return {"tracks": tracks, "count": pl.trackCount()}
    except ImportError:
        return {"error": "playlist module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_playlist_set_track_name(params: dict) -> dict:
    try:
        pl = _playlist_mod()
        track = params.get("track")
        err = _playlist_track_error(pl, track)
        if err:
            return {"error": err}
        pl.setTrackName(track, params.get("name", ""))
        return {"track": track, "name": pl.getTrackName(track)}
    except ImportError:
        return {"error": "playlist module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_playlist_set_track_color(params: dict) -> dict:
    try:
        pl = _playlist_mod()
        track = params.get("track")
        err = _playlist_track_error(pl, track)
        if err:
            return {"error": err}
        r = params.get("r", 0)
        g = params.get("g", 0)
        b = params.get("b", 0)
        # FL Studio's scripting API takes 0xRRGGBB
        pl.setTrackColor(track, (r << 16) | (g << 8) | b)
        return {"track": track, "color": "RGB(%s, %s, %s)" % (r, g, b)}
    except ImportError:
        return {"error": "playlist module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_playlist_mute_track(params: dict) -> dict:
    try:
        pl = _playlist_mod()
        track = params.get("track")
        err = _playlist_track_error(pl, track)
        if err:
            return {"error": err}
        muted = params.get("muted")
        # muteTrack only toggles, so skip the toggle when already in the state.
        if muted is None or (pl.isTrackMuted(track) == 1) != bool(muted):
            pl.muteTrack(track)
        return {"track": track, "name": pl.getTrackName(track),
                "is_muted": pl.isTrackMuted(track) == 1}
    except ImportError:
        return {"error": "playlist module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_playlist_solo_track(params: dict) -> dict:
    try:
        pl = _playlist_mod()
        track = params.get("track")
        err = _playlist_track_error(pl, track)
        if err:
            return {"error": err}
        solo = params.get("solo")
        if solo is None or (pl.isTrackSolo(track) == 1) != bool(solo):
            pl.soloTrack(track)
        return {"track": track, "name": pl.getTrackName(track),
                "is_solo": pl.isTrackSolo(track) == 1}
    except ImportError:
        return {"error": "playlist module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_arrangement_add_marker(params: dict) -> dict:
    """Add a time marker; time in beats from song start (None = playhead)."""
    try:
        arr = _arrangement_mod()
        general = _general_mod()
        name = params.get("name", "Marker")
        time_beats = params.get("time_beats")
        ppq = general.getRecPPQ()
        if time_beats is None:
            time_ticks = arr.currentTime(0)
        else:
            time_ticks = int(round(float(time_beats) * ppq))
        arr.addAutoTimeMarker(time_ticks, name)
        return {"name": name, "time_ticks": time_ticks,
                "time_beats": time_ticks / ppq}
    except ImportError:
        return {"error": "arrangement module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_arrangement_get_markers(params: dict) -> dict:
    try:
        arr = _arrangement_mod()
        markers = []
        # No marker-count API: names run out when getMarkerName returns "".
        for i in range(500):
            name = arr.getMarkerName(i)
            if not name:
                break
            markers.append({"index": i, "name": name})
        return {"markers": markers}
    except ImportError:
        return {"error": "arrangement module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_arrangement_jump_to_marker(params: dict) -> dict:
    """Jump playhead to the next or previous marker."""
    try:
        arr = _arrangement_mod()
        direction = params.get("direction", "next")
        if direction not in ("next", "prev"):
            return {"error": "direction must be 'next' or 'prev'"}
        arr.jumpToMarker(1 if direction == "next" else -1, False)
        return {"jumped": direction}
    except ImportError:
        return {"error": "arrangement module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_arrangement_get_time(params: dict) -> dict:
    """Get playhead position and timeline selection in ticks and beats."""
    try:
        arr = _arrangement_mod()
        general = _general_mod()
        ppq = general.getRecPPQ()
        current = arr.currentTime(0)
        return {
            "ppq": ppq,
            "current_ticks": current,
            "current_beats": current / ppq,
            "selection_start_ticks": arr.selectionStart(),
            "selection_end_ticks": arr.selectionEnd(),
        }
    except ImportError:
        return {"error": "arrangement module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_general_undo(params: dict) -> dict:
    try:
        general = _general_mod()
        result = general.undoUp()
        return {"undone": True, "result": result,
                "history_pos": general.getUndoHistoryPos(),
                "history_count": general.getUndoHistoryCount()}
    except ImportError:
        return {"error": "general module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_general_redo(params: dict) -> dict:
    try:
        general = _general_mod()
        result = general.undoDown()
        return {"redone": True, "result": result,
                "history_pos": general.getUndoHistoryPos(),
                "history_count": general.getUndoHistoryCount()}
    except ImportError:
        return {"error": "general module not available"}
    except Exception as e:
        return {"error": str(e)}


# UF flags (see FL API docs for general.saveUndo)
_UNDO_FLAGS = {
    "none": 0, "ee": 1, "pr": 2, "playlist": 4, "knob": 32,
    "audio_rec": 256, "auto_clip": 512, "pr_marker": 1024,
    "pl_marker": 2048, "plugin": 4096, "ss_looping": 8192, "reset": 65536,
}


def handle_general_save_undo_point(params: dict) -> dict:
    try:
        general = _general_mod()
        name = str(params.get("name", "MCP undo point"))
        flags_in = params.get("flags", ["pr", "playlist", "knob", "ss_looping"])
        if isinstance(flags_in, str):
            flags_in = [flags_in]
        unknown = [str(f) for f in flags_in if str(f).lower() not in _UNDO_FLAGS]
        if unknown:
            # Ignoring a flag silently would create an undo point that does not
            # cover what the caller assumed.
            return {"error": "Unknown undo flag(s): %s. Valid: %s"
                    % (", ".join(unknown), ", ".join(_UNDO_FLAGS))}
        flags = 0
        for f in flags_in:
            flags |= _UNDO_FLAGS[str(f).lower()]
        general.saveUndo(name, flags)
        return {"saved": True, "name": name, "flags": flags,
                "history_pos": general.getUndoHistoryPos(),
                "history_count": general.getUndoHistoryCount()}
    except ImportError:
        return {"error": "general module not available"}
    except Exception as e:
        return {"error": str(e)}


def handle_general_get_undo_status(params: dict) -> dict:
    try:
        general = _general_mod()
        return {
            "history_count": general.getUndoHistoryCount(),
            "history_pos": general.getUndoHistoryPos(),
            "history_last": general.getUndoHistoryLast(),
            "level_hint": general.getUndoLevelHint(),
            "changed_flag": general.getChangedFlag(),
            "safe_to_edit": general.safeToEdit(),
        }
    except ImportError:
        return {"error": "general module not available"}
    except Exception as e:
        return {"error": str(e)}


def write_response(response: dict):
    """Write response to JSON file."""
    try:
        RESPONSE_FILE.write_text(json.dumps(response, indent=2))
    except Exception as e:
        print(f"Error writing response: {e}")


def dispatch_command(action: str, params: dict) -> dict:
    """Route command to appropriate handler and return result."""

    # Transport commands
    if action == "transport.start":
        return handle_transport_start()
    elif action == "transport.stop":
        return handle_transport_stop()
    elif action == "transport.record":
        return handle_transport_record()
    elif action == "transport.getStatus":
        return handle_transport_get_status()
    elif action == "transport.setPosition":
        return handle_transport_set_position(params)
    elif action == "transport.getLength":
        return handle_transport_get_length()
    elif action == "transport.setLoopMode":
        return handle_transport_set_loop_mode(params)
    elif action == "transport.setPlaybackSpeed":
        return handle_transport_set_playback_speed(params)
    elif action == "transport.getTempo":
        return handle_transport_get_tempo()
    elif action == "transport.setTempo":
        return handle_transport_set_tempo(params)

    # Mixer commands
    elif action == "mixer.getTrackCount":
        return handle_mixer_get_track_count()
    elif action == "mixer.getTrackInfo":
        return handle_mixer_get_track_info(params)
    elif action == "mixer.getAllTracks":
        return handle_mixer_get_all_tracks(params)
    elif action == "mixer.setTrackVolume":
        return handle_mixer_set_track_volume(params)
    elif action == "mixer.setTrackPan":
        return handle_mixer_set_track_pan(params)
    elif action == "mixer.muteTrack":
        return handle_mixer_mute_track(params)
    elif action == "mixer.soloTrack":
        return handle_mixer_solo_track(params)
    elif action == "mixer.armTrack":
        return handle_mixer_arm_track(params)
    elif action == "mixer.setTrackName":
        return handle_mixer_set_track_name(params)
    elif action == "mixer.setTrackColor":
        return handle_mixer_set_track_color(params)
    elif action == "mixer.setStereoSep":
        return handle_mixer_set_stereo_sep(params)
    elif action == "mixer.getPeaks":
        return handle_mixer_get_peaks(params)
    elif action == "mixer.getAllPeaks":
        return handle_mixer_get_all_peaks(params)
    elif action == "mixer.routeTo":
        return handle_mixer_route_to(params)
    elif action == "mixer.getRouting":
        return handle_mixer_get_routing(params)
    elif action == "mixer.getTrackSlots":
        return handle_mixer_get_track_slots(params)

    # Playlist and arrangement commands
    elif action == "playlist.getTracks":
        return handle_playlist_get_tracks(params)
    elif action == "playlist.setTrackName":
        return handle_playlist_set_track_name(params)
    elif action == "playlist.setTrackColor":
        return handle_playlist_set_track_color(params)
    elif action == "playlist.muteTrack":
        return handle_playlist_mute_track(params)
    elif action == "playlist.soloTrack":
        return handle_playlist_solo_track(params)
    elif action == "arrangement.addMarker":
        return handle_arrangement_add_marker(params)
    elif action == "arrangement.getMarkers":
        return handle_arrangement_get_markers(params)
    elif action == "arrangement.jumpToMarker":
        return handle_arrangement_jump_to_marker(params)
    elif action == "arrangement.getTime":
        return handle_arrangement_get_time(params)
    elif action == "transport.setMetronome":
        return handle_transport_set_metronome(params)
    elif action == "project.getSnapshot":
        return handle_project_get_snapshot(params)

    # Channel commands
    elif action == "channels.getCount":
        return handle_channels_get_count(params)
    elif action == "channels.getInfo":
        return handle_channels_get_info(params)
    elif action == "channels.getAll":
        return handle_channels_get_all()
    elif action == "channels.getSelected":
        return handle_channels_get_selected()
    elif action == "channels.select":
        return handle_channels_select(params)
    elif action == "channels.selectOne":
        return handle_channels_select_one(params)
    elif action == "channels.triggerNote":
        return handle_channels_trigger_note(params)
    elif action == "channels.setVolume":
        return handle_channels_set_volume(params)
    elif action == "channels.setPan":
        return handle_channels_set_pan(params)
    elif action == "channels.mute":
        return handle_channels_mute(params)
    elif action == "channels.solo":
        return handle_channels_solo(params)
    elif action == "channels.setName":
        return handle_channels_set_name(params)
    elif action == "channels.setColor":
        return handle_channels_set_color(params)
    elif action == "channels.routeToMixer":
        return handle_channels_route_to_mixer(params)

    # Step sequencer commands
    elif action == "channels.getGridBit":
        return handle_channels_get_grid_bit(params)
    elif action == "channels.setGridBit":
        return handle_channels_set_grid_bit(params)
    elif action == "channels.getStepSequence":
        return handle_channels_get_step_sequence(params)
    elif action == "channels.setStepSequence":
        return handle_channels_set_step_sequence(params)

    # Plugin commands
    elif action == "plugins.isValid":
        return handle_plugins_is_valid(params)
    elif action == "plugins.getName":
        return handle_plugins_get_name(params)
    elif action == "plugins.getParamCount":
        return handle_plugins_get_param_count(params)
    elif action == "plugins.getParams":
        return handle_plugins_get_params(params)
    elif action == "plugins.getParamValue":
        return handle_plugins_get_param_value(params)
    elif action == "plugins.setParamValue":
        return handle_plugins_set_param_value(params)
    elif action == "plugins.getPresetCount":
        return handle_plugins_get_preset_count(params)
    elif action == "plugins.nextPreset":
        return handle_plugins_next_preset(params)
    elif action == "plugins.prevPreset":
        return handle_plugins_prev_preset(params)
    elif action == "patterns.getCount":
        return handle_patterns_get_count(params)
    elif action == "patterns.getAll":
        return handle_patterns_get_all(params)
    elif action == "patterns.getCurrent":
        return handle_patterns_get_current(params)
    elif action == "patterns.select":
        return handle_patterns_select(params)
    elif action == "patterns.newEmpty":
        return handle_patterns_new_empty(params)
    elif action == "patterns.clone":
        return handle_patterns_clone(params)
    elif action == "patterns.setName":
        return handle_patterns_set_name(params)
    elif action == "general.undo":
        return handle_general_undo(params)
    elif action == "general.redo":
        return handle_general_redo(params)
    elif action == "general.saveUndoPoint":
        return handle_general_save_undo_point(params)
    elif action == "general.getUndoStatus":
        return handle_general_get_undo_status(params)

    # UI / window handling
    elif action == "ui.getFocus":
        return handle_ui_get_focus(params)
    elif action == "ui.showWindow":
        return handle_ui_show_window(params)
    elif action == "ui.hideWindow":
        return handle_ui_hide_window(params)
    elif action == "ui.setFocus":
        return handle_ui_set_focus(params)
    elif action == "pianoroll.open":
        return handle_pianoroll_open(params)
    elif action == "plugins.getColor":
        return handle_plugins_get_color(params)

    else:
        return {"error": f"Unknown action: {action}"}


# =============================================================================
# Transport Handlers
# =============================================================================


def handle_transport_start() -> dict:
    """Toggle play/pause."""
    transport.start()
    return {"is_playing": transport.isPlaying() == 1}


def handle_transport_stop() -> dict:
    """Stop playback."""
    transport.stop()
    return {"stopped": True}


def handle_transport_record() -> dict:
    """Toggle recording."""
    transport.record()
    return {"is_recording": transport.isRecording() == 1}


def handle_transport_get_status() -> dict:
    """Get transport status."""
    loop_mode = transport.getLoopMode()
    return {
        "is_playing": transport.isPlaying() == 1,
        "is_recording": transport.isRecording() == 1,
        "position": transport.getSongPosHint(),
        "loop_mode": "song" if loop_mode == 1 else "pattern",
    }


def handle_transport_set_position(params: dict) -> dict:
    """Set playback position."""
    position = params.get("position", 0)
    mode = params.get("mode", 2)  # Default: seconds
    transport.setSongPos(position, mode)
    return {"position": transport.getSongPosHint()}


def handle_transport_get_length() -> dict:
    """Get song length."""
    return {
        "ticks": transport.getSongLength(3),
        "seconds": transport.getSongLength(2),
        "milliseconds": transport.getSongLength(1),
    }


def handle_transport_set_loop_mode(params: dict) -> dict:
    """Set loop mode."""
    mode = params.get("mode", "pattern")
    current_mode = transport.getLoopMode()
    target_mode = 1 if mode.lower() == "song" else 0

    if current_mode != target_mode:
        transport.setLoopMode()

    return {"mode": mode}


def handle_transport_set_playback_speed(params: dict) -> dict:
    """Set playback speed."""
    speed = params.get("speed", 1.0)
    transport.setPlaybackSpeed(speed)
    return {"speed": speed}


# =============================================================================
# Mixer Handlers
# =============================================================================


def handle_mixer_get_track_count() -> dict:
    """Get number of mixer tracks."""
    return {"count": mixer.trackCount()}


def handle_mixer_get_track_info(params: dict) -> dict:
    """Get info about a mixer track."""
    track = params.get("track", 0)
    return {
        "index": track,
        "name": mixer.getTrackName(track),
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
        "pan": mixer.getTrackPan(track),
        "stereo_separation": mixer.getTrackStereoSep(track),
        "is_muted": mixer.isTrackMuted(track) == 1,
        "is_solo": mixer.isTrackSolo(track) == 1,
        "is_armed": mixer.isTrackArmed(track) == 1,
        "color": hex(mixer.getTrackColor(track)),
    }


def handle_mixer_get_all_tracks(params: dict) -> dict:
    """Get info about all mixer tracks."""
    include_empty = params.get("include_empty", False)
    tracks = []
    track_count = mixer.trackCount()

    for i in range(track_count):
        name = mixer.getTrackName(i)

        # Skip empty tracks if requested
        if not include_empty and (not name or name.startswith("Insert ")):
            if i != 0:  # Always include master
                continue

        tracks.append({
            "index": i,
            "name": name if name else ("Master" if i == 0 else f"Insert {i}"),
            "volume": mixer.getTrackVolume(i),
            "pan": mixer.getTrackPan(i),
            "is_muted": mixer.isTrackMuted(i) == 1,
            "is_solo": mixer.isTrackSolo(i) == 1,
        })

    return {"tracks": tracks}


def handle_mixer_set_track_volume(params: dict) -> dict:
    """Set mixer track volume."""
    track = params.get("track", 0)
    volume = params.get("volume", 0.8)
    mixer.setTrackVolume(track, volume)
    return {
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
    }


def handle_mixer_set_track_pan(params: dict) -> dict:
    """Set mixer track pan."""
    track = params.get("track", 0)
    pan = params.get("pan", 0.0)
    mixer.setTrackPan(track, pan)
    return {"pan": mixer.getTrackPan(track)}


def handle_mixer_mute_track(params: dict) -> dict:
    """Mute/unmute mixer track."""
    track = params.get("track", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        mixer.muteTrack(track, -1)
    else:
        mixer.muteTrack(track, 1 if muted else 0)

    return {
        "is_muted": mixer.isTrackMuted(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_solo_track(params: dict) -> dict:
    """Solo/unsolo mixer track."""
    track = params.get("track", 0)
    solo = params.get("solo")  # None = toggle
    mode = params.get("mode", 3)

    if solo is None:
        mixer.soloTrack(track, -1, mode)
    else:
        mixer.soloTrack(track, 1 if solo else 0, mode)

    return {
        "is_solo": mixer.isTrackSolo(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_arm_track(params: dict) -> dict:
    """Toggle arm state of mixer track."""
    track = params.get("track", 0)
    mixer.armTrack(track)
    return {
        "is_armed": mixer.isTrackArmed(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_set_track_name(params: dict) -> dict:
    """Set mixer track name."""
    track = params.get("track", 0)
    name = params.get("name", "")
    mixer.setTrackName(track, name)
    return {"name": name}


def handle_mixer_set_track_color(params: dict) -> dict:
    """Set mixer track color."""
    track = params.get("track", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    mixer.setTrackColor(track, color)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_mixer_set_stereo_sep(params: dict) -> dict:
    """Set mixer track stereo separation."""
    track = params.get("track", 0)
    separation = params.get("separation", 0.0)
    mixer.setTrackStereoSep(track, separation)
    return {"separation": separation}


# =============================================================================
# Channel Handlers
# =============================================================================


def handle_channels_get_count(params: dict) -> dict:
    """Get number of channels."""
    global_count = params.get("global_count", True)
    return {"count": channels.channelCount(global_count)}


def handle_channels_get_info(params: dict) -> dict:
    """Get info about a channel."""
    index = params.get("index", 0)
    use_global = params.get("use_global", True)

    return {
        "index": index,
        "name": channels.getChannelName(index, use_global),
        "color": hex(channels.getChannelColor(index, use_global)),
        "volume": channels.getChannelVolume(index, use_global),
        "pan": channels.getChannelPan(index, use_global),
        "pitch": channels.getChannelPitch(index, useGlobalIndex=use_global),
        "is_muted": channels.isChannelMuted(index, use_global) == 1,
        "is_solo": channels.isChannelSolo(index, use_global) == 1,
        "is_selected": channels.isChannelSelected(index, use_global) == 1,
        "target_fx_track": channels.getTargetFxTrack(index, use_global),
    }


def handle_channels_get_all() -> dict:
    """Get info about all channels."""
    channels_list = []
    count = channels.channelCount(True)

    for i in range(count):
        channels_list.append({
            "index": i,
            "name": channels.getChannelName(i, True),
            "is_muted": channels.isChannelMuted(i, True) == 1,
            "is_selected": channels.isChannelSelected(i, True) == 1,
            "target_fx_track": channels.getTargetFxTrack(i, True),
        })

    return {"channels": channels_list}


def handle_channels_get_selected() -> dict:
    """Get currently selected channel."""
    index = channels.selectedChannel(canBeNone=True, indexGlobal=True)

    if index is None or index < 0:
        return {"channel": None}

    return {
        "channel": {
            "index": index,
            "name": channels.getChannelName(index, True),
            "volume": channels.getChannelVolume(index, True),
            "pan": channels.getChannelPan(index, True),
            "is_muted": channels.isChannelMuted(index, True) == 1,
            "is_solo": channels.isChannelSolo(index, True) == 1,
        }
    }


def handle_channels_select(params: dict) -> dict:
    """Select/deselect a channel."""
    index = params.get("index", 0)
    select = params.get("select", True)
    channels.selectChannel(index, 1 if select else 0, True)
    return {
        "selected": select,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_select_one(params: dict) -> dict:
    """Select only one channel, deselecting others."""
    index = params.get("index", 0)
    channels.selectOneChannel(index, True)
    return {"channel_name": channels.getChannelName(index, True)}


def handle_channels_trigger_note(params: dict) -> dict:
    """Trigger a MIDI note on a channel."""
    channel = params.get("channel", 0)
    note = params.get("note", 60)
    velocity = params.get("velocity", 100)
    midi_channel = params.get("midi_channel", -1)
    channels.midiNoteOn(channel, note, velocity, midi_channel)
    return {"triggered": True, "note": note, "velocity": velocity}


def handle_channels_set_volume(params: dict) -> dict:
    """Set channel volume."""
    index = params.get("index", 0)
    volume = params.get("volume", 0.8)
    channels.setChannelVolume(index, volume, True)
    return {
        "volume": channels.getChannelVolume(index, True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_pan(params: dict) -> dict:
    """Set channel pan."""
    index = params.get("index", 0)
    pan = params.get("pan", 0.0)
    channels.setChannelPan(index, pan, True)
    return {
        "pan": channels.getChannelPan(index, True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_mute(params: dict) -> dict:
    """Mute/unmute channel."""
    index = params.get("index", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        channels.muteChannel(index, -1, True)
    else:
        channels.muteChannel(index, 1 if muted else 0, True)

    return {
        "is_muted": channels.isChannelMuted(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_solo(params: dict) -> dict:
    """Solo/unsolo channel."""
    index = params.get("index", 0)
    solo = params.get("solo")  # None = toggle

    if solo is None:
        channels.soloChannel(index, -1, True)
    else:
        channels.soloChannel(index, 1 if solo else 0, True)

    return {
        "is_solo": channels.isChannelSolo(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_name(params: dict) -> dict:
    """Set channel name."""
    index = params.get("index", 0)
    name = params.get("name", "")
    channels.setChannelName(index, name, True)
    return {"name": name}


def handle_channels_set_color(params: dict) -> dict:
    """Set channel color."""
    index = params.get("index", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    channels.setChannelColor(index, color, True)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_channels_route_to_mixer(params: dict) -> dict:
    """Route channel to mixer track."""
    channel_index = params.get("channel_index", 0)
    mixer_track = params.get("mixer_track", 0)
    channels.setTargetFxTrack(channel_index, mixer_track, True)
    return {
        "channel_name": channels.getChannelName(channel_index, True),
        "mixer_track": mixer_track,
    }


# =============================================================================
# Step Sequencer Handlers
# =============================================================================


def handle_channels_get_grid_bit(params: dict) -> dict:
    """Get whether a step is active."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    return {"value": channels.getGridBit(channel, position, True) == 1}


def handle_channels_set_grid_bit(params: dict) -> dict:
    """Set a step on or off."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    value = params.get("value", False)
    channels.setGridBit(channel, position, 1 if value else 0, True)
    return {
        "value": value,
        "channel_name": channels.getChannelName(channel, True),
    }


def handle_channels_get_step_sequence(params: dict) -> dict:
    """Get step sequence for a channel."""
    channel = params.get("channel", 0)
    steps = params.get("steps", 16)
    sequence = []

    for i in range(steps):
        sequence.append(channels.getGridBit(channel, i, True) == 1)

    return {"sequence": sequence}


def handle_channels_set_step_sequence(params: dict) -> dict:
    """Set complete step sequence for a channel."""
    channel = params.get("channel", 0)
    pattern = params.get("pattern", [])

    for i, value in enumerate(pattern):
        channels.setGridBit(channel, i, 1 if value else 0, True)

    active_steps = sum(pattern)
    return {
        "active_steps": active_steps,
        "total_steps": len(pattern),
        "channel_name": channels.getChannelName(channel, True),
    }


# =============================================================================
# Plugin Handlers
# =============================================================================


def handle_plugins_is_valid(params: dict) -> dict:
    """Check if plugin exists at location."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        valid = plugins.isValid(index, slot_index, True)
    else:
        valid = plugins.isValid(index, -1, use_global)

    return {"valid": valid == 1}


def handle_plugins_get_name(params: dict) -> dict:
    """Get plugin name."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getPluginName(index, slot_index, True)
    else:
        name = plugins.getPluginName(index, -1, use_global)

    return {"name": name}


def handle_plugins_get_param_count(params: dict) -> dict:
    """Get number of plugin parameters."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getParamCount(index, slot_index, True)
    else:
        count = plugins.getParamCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_get_params(params: dict) -> dict:
    """Get all plugin parameters."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)
    max_params = params.get("max_params", 50)

    if slot_index >= 0:
        param_count = plugins.getParamCount(index, slot_index, True)
    else:
        param_count = plugins.getParamCount(index, -1, use_global)

    param_list = []
    for i in range(min(param_count, max_params)):
        try:
            if slot_index >= 0:
                name = plugins.getParamName(i, index, slot_index, True)
                value = plugins.getParamValue(i, index, slot_index, True)
                value_str = plugins.getParamValueString(i, index, slot_index, True)
            else:
                name = plugins.getParamName(i, index, -1, use_global)
                value = plugins.getParamValue(i, index, -1, use_global)
                value_str = plugins.getParamValueString(i, index, -1, use_global)

            param_list.append({
                "index": i,
                "name": name,
                "value": value,
                "value_string": value_str,
            })
        except Exception as e:
            print(f"Warning: could not read param {i}: {e}")
            continue

    return {"params": param_list}


def handle_plugins_get_param_value(params: dict) -> dict:
    """Get specific parameter value."""
    param_index = params.get("param_index", 0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "index": param_index,
        "name": name,
        "value": value,
        "value_string": value_str,
    }


def handle_plugins_set_param_value(params: dict) -> dict:
    """Set plugin parameter value."""
    param_index = params.get("param_index", 0)
    value = params.get("value", 0.0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    # setParamValue's 5th argument is pickupMode, NOT useGlobalIndex:
    # setParamValue(value, paramIndex, index, slotIndex, pickupMode, useGlobalIndex).
    # Passing True there enables pickup mode and the value is silently ignored.
    pim_none = _midi_mod().PIM_None
    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        plugins.setParamValue(value, param_index, plugin_index, slot_index, pim_none, True)
        new_value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        plugins.setParamValue(value, param_index, plugin_index, -1, pim_none, use_global)
        new_value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "name": name,
        "value": new_value,
        "value_string": value_str,
    }


def handle_plugins_get_preset_count(params: dict) -> dict:
    """Get number of plugin presets."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getPresetCount(index, slot_index, True)
    else:
        count = plugins.getPresetCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_next_preset(params: dict) -> dict:
    """Switch to next preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.nextPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, use_global)
        plugins.nextPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_prev_preset(params: dict) -> dict:
    """Switch to previous preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.prevPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, use_global)
        plugins.prevPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_get_color(params: dict) -> dict:
    """Get plugin color."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        color = plugins.getColor(index, slot_index, True)
    else:
        color = plugins.getColor(index, -1, use_global)

    return {"color": hex(color)}
