"""Music-theory and humanize logic of the compose tools (no FL Studio needed)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.compose import build_progression, humanize_notes


def _pitches_at(notes, time):
    return sorted(n["midi"] for n in notes if n["time"] == time)


# --- build_progression ------------------------------------------------------

def test_c_major_one_chord_is_c_major_triad():
    notes = build_progression("C", "major", [1])
    assert _pitches_at(notes, 0.0) == [60, 64, 67]  # C4 E4 G4


def test_diatonic_quality_ii_in_c_major_is_d_minor():
    notes = build_progression("C", "major", ["ii"])
    assert _pitches_at(notes, 0.0) == [62, 65, 69]  # D4 F4 A4


def test_seventh_suffix_upgrades_single_chord():
    notes = build_progression("C", "major", ["V7"])
    assert _pitches_at(notes, 0.0) == [67, 71, 74, 77]  # G4 B4 D5 F5


def test_minor_key_vi_is_major_triad():
    # In C minor the VI chord is Ab major.
    notes = build_progression("C", "minor", [6])
    assert _pitches_at(notes, 0.0) == [68, 72, 75]  # Ab4 C5 Eb5


def test_chords_advance_by_duration_and_start_time():
    notes = build_progression("A", "minor", [1, 4], chord_duration=2.0, start_time=8.0)
    assert {n["time"] for n in notes} == {8.0, 10.0}


def test_flat_key_names_parse():
    notes = build_progression("Bb", "major", [1])
    assert _pitches_at(notes, 0.0)[0] == 70  # Bb4


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"key": "H", "scale": "major", "progression": [1]}, "unknown key"),
        ({"key": "C", "scale": "blues", "progression": [1]}, "unknown scale"),
        ({"key": "C", "scale": "major", "progression": []}, "empty"),
        ({"key": "C", "scale": "major", "progression": [8]}, "out of range"),
        ({"key": "C", "scale": "major", "progression": ["viii"]}, "cannot parse"),
        ({"key": "C", "scale": "major", "progression": [1], "voicing": "cluster"}, "voicing"),
        ({"key": "C", "scale": "major", "progression": [1], "octave": 9}, "octave"),
        ({"key": "C", "scale": "major", "progression": [1], "chord_duration": 0}, "positive"),
    ],
)
def test_bad_input_returns_error_string(kwargs, fragment):
    result = build_progression(**kwargs)
    assert isinstance(result, str)
    assert fragment in result


# --- humanize_notes ---------------------------------------------------------

BASE_NOTES = [
    {"midi": 60, "time": 0.0, "duration": 0.25, "velocity": 0.8},
    {"midi": 60, "time": 0.25, "duration": 0.25, "velocity": 0.8},
    {"midi": 60, "time": 0.5, "duration": 0.25, "velocity": 0.8},
    {"midi": 60, "time": 0.75, "duration": 0.25, "velocity": 0.8},
]


def test_seed_makes_result_reproducible():
    a = humanize_notes(BASE_NOTES, seed=42)
    b = humanize_notes(BASE_NOTES, seed=42)
    assert a == b


def test_swing_delays_only_offbeat_grid_steps():
    out = humanize_notes(BASE_NOTES, velocity_jitter=0, timing_jitter=0, swing=1.0)
    times = [n["time"] for n in out]
    # Down-beats untouched, off-beats pushed late by half a grid step.
    assert times[0] == 0.0
    assert times[1] == pytest.approx(0.375)
    assert times[2] == 0.5
    assert times[3] == pytest.approx(0.875)


def test_velocity_stays_clamped():
    loud = [{"midi": 60, "time": 0.0, "duration": 1.0, "velocity": 0.99}]
    for seed in range(20):
        (note,) = humanize_notes(loud, velocity_jitter=0.5, timing_jitter=0, seed=seed)
        assert 0.05 <= note["velocity"] <= 1.0


def test_time_never_goes_negative():
    early = [{"midi": 60, "time": 0.0, "duration": 1.0, "velocity": 0.8}]
    for seed in range(20):
        (note,) = humanize_notes(early, velocity_jitter=0, timing_jitter=0.5, seed=seed)
        assert note["time"] >= 0.0


def test_no_jitter_no_swing_is_identity_on_core_fields():
    out = humanize_notes(BASE_NOTES, velocity_jitter=0, timing_jitter=0, swing=0)
    assert [(n["midi"], n["time"], n["duration"], n["velocity"]) for n in out] == [
        (n["midi"], n["time"], n["duration"], n["velocity"]) for n in BASE_NOTES
    ]
