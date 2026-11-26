"""Portable song documents and deterministic musical rendering."""

import io
import re
from typing import Literal

import mido
from pydantic import BaseModel, ConfigDict, Field, model_validator

CHORD = re.compile(r"^([A-G])([#b]?)(m7|maj|min|m|7)?$")
ROOTS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitches(symbol: str) -> list[int]:
    match = CHORD.fullmatch(symbol)
    if not match:
        raise ValueError(f"Unsupported chord: {symbol}")
    letter, accidental, quality = match.groups()
    root = 48 + (ROOTS[letter] + {"": 0, "#": 1, "b": -1}[accidental]) % 12
    intervals = {"m": [0, 3, 7], "min": [0, 3, 7], "m7": [0, 3, 7, 10], "7": [0, 4, 7, 10]}.get(
        quality, [0, 4, 7]
    )
    return [root + interval for interval in intervals]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Chord(Model):
    id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(max_length=8)
    anchor: int | None = Field(default=None, ge=0)
    beats: float = Field(gt=0, le=64, multiple_of=0.5)

    @model_validator(mode="after")
    def valid(self):
        pitches(self.symbol)
        return self


class Section(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    lyrics: str = Field(max_length=50000)
    chords: list[Chord] = Field(max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        if len({c.id for c in self.chords}) != len(self.chords):
            raise ValueError("Duplicate chord IDs")
        if any(c.anchor is not None and c.anchor > len(self.lyrics) for c in self.chords):
            raise ValueError("Chord anchor exceeds lyrics")
        return self


class Song(Model):
    version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    title: str = Field(max_length=200)
    tempo: int = Field(default=120, ge=30, le=300)
    meter: Literal["4/4", "3/4", "6/8"] = "4/4"
    sections: list[Section] = Field(min_length=1, max_length=100)
    arrangement: list[str] = Field(max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        sections = {s.id: s for s in self.sections}
        if len(sections) != len(self.sections):
            raise ValueError("Duplicate section IDs")
        if any(key not in sections for key in self.arrangement):
            raise ValueError("Unknown section in arrangement")
        if sum(len(sections[key].chords) for key in self.arrangement) > 10000:
            raise ValueError("Arrangement exceeds 10,000 chord events")
        return self


def events(song: Song) -> list[dict]:
    sections = {s.id: s for s in song.sections}
    result, beat = [], 0.0
    for key in song.arrangement:
        section = sections[key]
        for chord in section.chords:
            result.append(
                dict(
                    section=section.name,
                    chord=chord.symbol,
                    start=beat,
                    beats=chord.beats,
                    notes=pitches(chord.symbol),
                )
            )
            beat += chord.beats
    return result


def midi_bytes(song: Song) -> bytes:
    midi = mido.MidiFile(type=0, ticks_per_beat=480, charset="utf8")
    track = mido.MidiTrack()
    midi.tracks.append(track)
    numerator, denominator = map(int, song.meter.split("/"))
    track.extend(
        [
            mido.MetaMessage("track_name", name="SongsFlow piano"),
            mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(song.tempo)),
            mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator),
            mido.Message("program_change", program=0),
        ]
    )
    sections = {s.id: s for s in song.sections}
    for key in song.arrangement:
        track.append(mido.MetaMessage("marker", text=sections[key].name))
        for chord in sections[key].chords:
            notes = pitches(chord.symbol)
            for note in notes:
                track.append(mido.Message("note_on", note=note, velocity=80))
            for index, note in enumerate(notes):
                track.append(
                    mido.Message(
                        "note_off",
                        note=note,
                        velocity=0,
                        time=round(chord.beats * 480) if index == 0 else 0,
                    )
                )
    track.append(mido.MetaMessage("end_of_track"))
    output = io.BytesIO()
    midi.save(file=output)
    return output.getvalue()
