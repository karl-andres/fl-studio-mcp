"""Composition helper tools: humanize/swing and diatonic chord progressions.

Pure server-side transforms on top of the piano roll request pipeline —
no new controller commands. Notes are written through the same
mcp_request.json / ComposeWithLLM path as fl_send_notes.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from fl_studio_mcp.tools.piano_roll import (
    _describe_run,
    _read_state,
    _run_pr_script,
    _write_request,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Pitch classes for note names, with sharp and flat spellings.
_PITCH_CLASSES = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "FB": 4,
    "E#": 5, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9,
    "A#": 10, "BB": 10, "B": 11, "CB": 11, "B#": 0,
}

# Scale interval patterns in semitones from the root.
_SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
}
_SCALES["natural_minor"] = _SCALES["minor"]
_SCALES["aeolian"] = _SCALES["minor"]
_SCALES["ionian"] = _SCALES["major"]

_ROMAN_DEGREES = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}

# Chord tones as stacked diatonic thirds: scale-degree offsets from the root
# degree. Diatonic stacking derives each chord's quality from the scale itself.
_VOICING_STEPS = {"triad": [0, 2, 4], "seventh": [0, 2, 4, 6], "ninth": [0, 2, 4, 6, 8]}


def _parse_degree(symbol) -> tuple[int, str | None] | str:
    """Parse a progression entry into (degree 1-7, voicing override or None).

    Accepts integers 1-7 and roman numerals like "ii", "V", "IV7", "i9".
    Returns an error string on bad input.
    """
    if isinstance(symbol, bool):
        return f"Error: bad progression entry {symbol!r}"
    if isinstance(symbol, int):
        if 1 <= symbol <= 7:
            return symbol, None
        return f"Error: degree {symbol} out of range 1..7"
    if not isinstance(symbol, str):
        return f"Error: bad progression entry {symbol!r}"

    text = symbol.strip().lower()
    voicing = None
    if text.endswith("9"):
        voicing, text = "ninth", text[:-1]
    elif text.endswith("7"):
        voicing, text = "seventh", text[:-1]
    degree = _ROMAN_DEGREES.get(text)
    if degree is None:
        return (
            f"Error: cannot parse progression entry {symbol!r} "
            "(use 1-7 or roman numerals like ii, V, IV7)"
        )
    return degree, voicing


def build_progression(
    key: str,
    scale: str,
    progression: list,
    octave: int = 4,
    chord_duration: float = 4.0,
    start_time: float = 0.0,
    velocity: float = 0.8,
    voicing: str = "triad",
) -> list[dict] | str:
    """Build note dicts for a diatonic chord progression; error string on bad input."""
    root_pc = _PITCH_CLASSES.get(key.strip().upper())
    if root_pc is None:
        return f"Error: unknown key {key!r} (use C, F#, Bb...)"
    intervals = _SCALES.get(scale.strip().lower())
    if intervals is None:
        return f"Error: unknown scale {scale!r} (available: {', '.join(sorted(_SCALES))})"
    if voicing not in _VOICING_STEPS:
        return f"Error: voicing must be one of {', '.join(_VOICING_STEPS)}"
    if not progression:
        return "Error: progression is empty"
    if not 0 <= octave <= 8:
        return "Error: octave must be between 0 and 8"
    if chord_duration <= 0:
        return "Error: chord_duration must be positive"

    base = (octave + 1) * 12 + root_pc  # MIDI root of the key in that octave
    notes = []
    time = start_time
    for symbol in progression:
        parsed = _parse_degree(symbol)
        if isinstance(parsed, str):
            return parsed
        degree, override = parsed
        for step in _VOICING_STEPS[override or voicing]:
            scale_index = degree - 1 + step
            midi = base + intervals[scale_index % 7] + 12 * (scale_index // 7)
            if not 0 <= midi <= 127:
                return f"Error: chord on degree {degree} leaves MIDI range; lower the octave"
            notes.append({
                "midi": midi,
                "time": time,
                "duration": chord_duration,
                "velocity": velocity,
            })
        time += chord_duration
    return notes


def humanize_notes(
    notes: list[dict],
    velocity_jitter: float = 0.06,
    timing_jitter: float = 0.02,
    swing: float = 0.0,
    swing_grid: float = 0.25,
    seed: int | None = None,
) -> list[dict]:
    """Return humanized copies of note dicts (midi/time/duration/velocity only).

    Swing shifts notes on the off-beat of `swing_grid` (every odd grid step)
    later by up to half a grid step at swing=1.0. Jitter is applied after
    swing so the groove stays intact.
    """
    rng = random.Random(seed)
    out = []
    for note in notes:
        time = float(note.get("time", 0))
        velocity = float(note.get("velocity", 0.8))

        if swing > 0 and swing_grid > 0:
            step = round(time / swing_grid)
            # Off-beat steps only, and only notes actually sitting on the grid.
            if step % 2 == 1 and abs(time - step * swing_grid) < swing_grid / 8:
                time = step * swing_grid + swing * swing_grid * 0.5

        if timing_jitter > 0:
            time += rng.uniform(-timing_jitter, timing_jitter)
        if velocity_jitter > 0:
            velocity += rng.uniform(-velocity_jitter, velocity_jitter)

        out.append({
            "midi": note["midi"],
            "time": max(0.0, round(time, 4)),
            "duration": float(note.get("duration", 0.25)),
            "velocity": round(min(1.0, max(0.05, velocity)), 4),
        })
    return out


def register_compose_tools(mcp: FastMCP) -> None:
    """Register composition helper tools with the MCP server."""

    @mcp.tool()
    def fl_send_chord_progression(
        key: str,
        progression: list,
        scale: str = "minor",
        octave: int = 4,
        chord_duration: float = 4.0,
        start_time: float = 0.0,
        velocity: float = 0.8,
        voicing: str = "triad",
        mode: str = "add",
        auto_trigger: bool = True,
    ) -> str:
        """Write a diatonic chord progression into the open piano roll.

        Chord qualities come from the scale automatically (in C minor the i is
        Cm, the VI is Ab major...). Open the target channel's piano roll first
        (fl_open_piano_roll).

        Args:
            key: Root of the key, e.g. "C", "F#", "Bb".
            progression: Chord list as scale degrees: integers 1-7 or roman
                         numerals ("i", "VI", "III", "VII"). A "7" or "9"
                         suffix upgrades that chord ("ii7", "V9").
            scale: major, minor, harmonic_minor, dorian, phrygian, lydian,
                   mixolydian or locrian.
            octave: Octave of the key's root (4 = around middle C).
            chord_duration: Beats per chord (4.0 = one 4/4 bar each).
            start_time: Start position in beats.
            velocity: Velocity 0.0-1.0 for all notes.
            voicing: "triad", "seventh" or "ninth" (default for all chords).
            mode: "add" or "replace" (clears the piano roll first).
            auto_trigger: Trigger FL Studio automatically (default True).
        """
        notes = build_progression(
            key, scale, progression, octave, chord_duration,
            start_time, velocity, voicing,
        )
        if isinstance(notes, str):
            return notes

        requests = []
        if mode == "replace":
            requests.append({"action": "clear"})
        requests.append({"action": "add_notes", "notes": notes})
        _write_request(requests)

        summary = " - ".join(str(s) for s in progression)
        outcome = ""
        if auto_trigger:
            outcome = " " + _describe_run(_run_pr_script())
        return (
            f"Queued {len(progression)} chord(s) ({summary}) in {key} {scale}, "
            f"{len(notes)} notes.{outcome}"
        )

    @mcp.tool()
    def fl_humanize(
        velocity_jitter: float = 0.06,
        timing_jitter: float = 0.02,
        swing: float = 0.0,
        swing_grid: float = 0.25,
        seed: int | None = None,
    ) -> str:
        """Humanize the notes in the open piano roll (velocity/timing jitter + swing).

        Reads the current notes, applies the transform and replaces them.
        Swing gives the MPC-style late push to off-beat notes: with
        swing_grid=0.25 every second 16th is delayed by up to half a 16th at
        swing=1.0. Try swing 0.55-0.65 for that lazy Kaytranada feel.

        Only midi/time/duration/velocity survive the rewrite; per-note pan,
        color and slide flags are reset.

        Args:
            velocity_jitter: Random velocity change, +/- this amount (0-1 scale).
            timing_jitter: Random timing change in beats (0.02 = subtle drift).
            swing: 0.0 = straight, 1.0 = maximum shuffle.
            swing_grid: Grid for swing in beats (0.25 = 16th notes).
            seed: Random seed for a reproducible result.
        """
        if not 0 <= swing <= 1:
            return "Error: swing must be between 0.0 and 1.0"
        if velocity_jitter < 0 or timing_jitter < 0 or swing_grid <= 0:
            return "Error: jitter values must be >= 0 and swing_grid > 0"

        # Refresh the state export first: an empty-queue trigger makes the
        # script re-export what is really in the piano roll right now.
        refresh = _run_pr_script()
        if not refresh["ran"]:
            return f"Error: {refresh['error']}"

        state = _read_state()
        if not state or not state.get("notes"):
            return "Error: the piano roll has no notes to humanize"

        notes = humanize_notes(
            state["notes"], velocity_jitter, timing_jitter, swing, swing_grid, seed,
        )
        _write_request([{"action": "clear"}, {"action": "add_notes", "notes": notes}])
        outcome = _describe_run(_run_pr_script())

        swung = f", swing {swing:g} on {swing_grid:g}-beat grid" if swing > 0 else ""
        return f"Humanized {len(notes)} note(s){swung}. {outcome}"
