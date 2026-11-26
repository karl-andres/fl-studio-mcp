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


class AudioInfo(Model):
    name: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(gt=0, le=20 * 1024 * 1024)
    duration: float = Field(gt=0, le=7200)
    media_type: Literal["audio/mpeg", "audio/wav", "audio/mp4"]


class Timing(Model):
    key: str = Field(min_length=1, max_length=200)
    start: float | None = Field(default=None, ge=0, le=7200)
    end: float | None = Field(default=None, ge=0, le=7200)


class Song(Model):
    version: Literal[2] = 2
    revision: int = Field(default=0, ge=0)
    title: str = Field(max_length=200)
    tempo: int = Field(default=120, ge=30, le=300)
    meter: Literal["4/4", "3/4", "6/8"] = "4/4"
    sections: list[Section] = Field(min_length=1, max_length=100)
    arrangement: list[str] = Field(max_length=1000)
    timing_mode: Literal["beats", "performance"] = "beats"
    audio: AudioInfo | None = None
    performance: list[Timing] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="before")
    @classmethod
    def migrate(cls, data):
        if isinstance(data, dict) and data.get("version") == 1:
            if any(key in data for key in ("audio", "performance", "timing_mode")):
                raise ValueError("Version 1 cannot contain version 2 fields")
            return {**data, "version": 2}
        return data

    @model_validator(mode="after")
    def valid(self):
        sections = {s.id: s for s in self.sections}
        if len(sections) != len(self.sections):
            raise ValueError("Duplicate section IDs")
        if any(key not in sections for key in self.arrangement):
            raise ValueError("Unknown section in arrangement")
        if sum(len(sections[key].chords) for key in self.arrangement) > 10000:
            raise ValueError("Arrangement exceeds 10,000 chord events")
        sequence = occurrences(self)
        if self.timing_mode == "performance" and self.audio is None:
            raise ValueError("Performance timing needs reference audio metadata")
        if self.performance:
            if [mark.key for mark in self.performance] != [item[0] for item in sequence]:
                raise ValueError("Progression changed: mark the chord timings again")
            previous = 0.0
            for mark in self.performance:
                if mark.start is None:
                    if mark.end is not None:
                        raise ValueError("Set a start before an end")
                    continue
                if not self.audio or mark.start >= self.audio.duration:
                    raise ValueError("Chord start is outside the audio")
                if mark.start < previous:
                    raise ValueError("Chord timings overlap or are out of order")
                if mark.end is not None:
                    if mark.end <= mark.start or mark.end > self.audio.duration:
                        raise ValueError("Invalid chord end")
                previous = mark.end if mark.end is not None else mark.start
        return self


def occurrences(song: Song) -> list[tuple[str, Section, Chord]]:
    sections = {s.id: s for s in song.sections}
    return [
        (f"{index}:{position}:{key}:{chord.id}", sections[key], chord)
        for index, key in enumerate(song.arrangement)
        for position, chord in enumerate(sections[key].chords)
    ]


def timing_complete(song: Song) -> bool:
    return (
        song.timing_mode == "beats"
        or bool(song.performance)
        and all(m.start is not None and m.end is not None for m in song.performance)
    )


def events(song: Song) -> list[dict]:
    if not timing_complete(song):
        raise ValueError("Mark every chord start and end before preview or MIDI export")
    result, beat = [], 0.0
    tempo_us = mido.bpm2tempo(song.tempo)
    for index, (key, section, chord) in enumerate(occurrences(song)):
        if song.timing_mode == "performance":
            mark = song.performance[index]
            start = mark.start * 1_000_000 / tempo_us
            duration = (mark.end - mark.start) * 1_000_000 / tempo_us
        else:
            start, duration = beat, chord.beats
        if round((start + duration) * 480) <= round(start * 480):
            raise ValueError("A chord is shorter than one MIDI tick at this tempo")
        result.append(
            dict(
                key=key,
                section=section.name,
                chord=chord.symbol,
                start=start,
                beats=duration,
                notes=pitches(chord.symbol),
                start_seconds=start * tempo_us / 1_000_000,
                duration_seconds=duration * tempo_us / 1_000_000,
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
    absolute = []
    previous_section = None
    for event in events(song):
        start = round(event["start"] * 480)
        end = round((event["start"] + event["beats"]) * 480)
        occurrence = event["key"].split(":", 1)[0]
        if occurrence != previous_section:
            absolute.append((start, 1, mido.MetaMessage("marker", text=event["section"])))
            previous_section = occurrence
        for note in event["notes"]:
            absolute.append((start, 2, mido.Message("note_on", note=note, velocity=80)))
            absolute.append((end, 0, mido.Message("note_off", note=note, velocity=0)))
    tick = 0
    for at, _, message in sorted(absolute, key=lambda item: (item[0], item[1])):
        track.append(message.copy(time=at - tick))
        tick = at
    track.append(mido.MetaMessage("end_of_track"))
    output = io.BytesIO()
    midi.save(file=output)
    return output.getvalue()


def lyrics_text(song: Song) -> bytes:
    lines = [song.title, f"Tempo: {song.tempo} quarter notes/min | Meter: {song.meter}", ""]
    sections = {s.id: s for s in song.sections}
    for key in song.arrangement:
        section = sections[key]
        insertions = {}
        for chord in section.chords:
            if chord.anchor is not None:
                insertions.setdefault(chord.anchor, []).append(f"[{chord.symbol}]")
        text = "".join(
            "".join(insertions.get(i, [])) + char for i, char in enumerate(section.lyrics)
        )
        text += "".join(insertions.get(len(section.lyrics), []))
        unattached = [c.symbol for c in section.chords if c.anchor is None]
        lines.extend([f"[{section.name}]", text])
        if unattached:
            lines.append("Unattached chords: " + " → ".join(unattached))
        lines.append("")
    return "\n".join(lines).encode("utf8")
