import asyncio
import hashlib
import io
import time
import wave

import mido
import pytest
from fastmcp import Client
from pydantic import ValidationError
from starlette.testclient import TestClient

from songsflow.music import AudioInfo, Song, events, lyrics_text, midi_bytes, occurrences
from songsflow.server import create_app, create_server, exports, prune, uploads


def wav_bytes(seconds=8):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * (8000 * seconds))
    return output.getvalue()


def info(data=None):
    data = data if data is not None else wav_bytes()
    return AudioInfo(
        name="reference.wav",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        duration=8,
        media_type="audio/wav",
    )


def song():
    result = Song(
        title="Été",
        sections=[
            dict(
                id="v",
                name="Verse",
                lyrics="Hello 🌎",
                chords=[
                    dict(id="c", symbol="C", anchor=0, beats=4),
                    dict(id="f", symbol="F", anchor=6, beats=4),
                ],
            )
        ],
        arrangement=["v", "v"],
        audio=info(),
        timing_mode="performance",
    )
    payload = result.model_dump()
    payload["performance"] = [
        dict(key=key, start=start, end=end)
        for (key, _, _), (start, end) in zip(
            occurrences(result), [(0.75, 1.2), (1.5, 2.4), (3.1, 4), (5.2, 7.7)]
        )
    ]
    return Song.model_validate(payload)


def test_v1_migrates_without_audio():
    legacy = dict(
        version=1,
        title="Legacy",
        sections=[dict(id="v", name="Verse", lyrics="Words", chords=[])],
        arrangement=["v"],
    )
    migrated = Song.model_validate(legacy)
    assert migrated.version == 2
    assert migrated.audio is None
    assert migrated.timing_mode == "beats"


@pytest.mark.parametrize("tempo", [30, 120, 299])
def test_performance_midi_matches_audio_seconds(tempo):
    s = song()
    s.tempo = tempo
    midi = mido.MidiFile(file=io.BytesIO(midi_bytes(s)))
    tempo_us = next(m.tempo for m in midi.tracks[0] if m.type == "set_tempo")
    seconds, rendered = 0, []
    for msg in midi.tracks[0]:
        seconds += mido.tick2second(msg.time, 480, tempo_us)
        if msg.type in ("note_on", "note_off"):
            rendered.append((msg.type, msg.note, seconds))
    for event, mark in zip(events(s), s.performance):
        assert abs(event["start_seconds"] - mark.start) < 1e-9
        assert abs(event["duration_seconds"] - (mark.end - mark.start)) < 1e-9
        for note in event["notes"]:
            assert any(
                kind == "note_on"
                and pitch == note
                and abs(at - mark.start) <= mido.tick2second(1, 480, tempo_us)
                for kind, pitch, at in rendered
            )
            assert any(
                kind == "note_off"
                and pitch == note
                and abs(at - mark.end) <= mido.tick2second(1, 480, tempo_us)
                for kind, pitch, at in rendered
            )
    assert min(t for kind, _, t in rendered if kind == "note_on") > 0


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["performance"][0].update(start=-1),
        lambda s: s["performance"][0].update(end=0.5),
        lambda s: s["performance"][1].update(start=1),
        lambda s: s["performance"][-1].update(end=9),
        lambda s: s["performance"][0].update(start=None),
        lambda s: s.update(arrangement=["v"]),
        lambda s: s["performance"][0].update(start=float("nan")),
    ],
)
def test_invalid_performance(change):
    data = song().model_dump()
    change(data)
    with pytest.raises(ValidationError):
        Song.model_validate(data)


def test_incomplete_draft_can_be_saved_but_not_exported():
    s = song()
    s.performance[0].end = None
    with pytest.raises(ValueError, match="Mark every"):
        midi_bytes(s)
    assert Song.model_validate(s.model_dump()).performance[0].end is None


def test_lyrics_annotations_unicode_and_repeats():
    text = lyrics_text(song()).decode("utf8")
    assert "Été" in text
    assert text.count("[Verse]") == 2
    assert text.count("[C]Hello [F]🌎") == 2


def ticket(metadata):
    async def prepare():
        async with Client(create_server("http://localhost:8000")) as client:
            result = await client.call_tool(
                "prepare_audio_export", {"metadata": metadata.model_dump()}
            )
            return result.data["upload_url"]

    return asyncio.run(prepare())


def test_binary_upload_roundtrip_revoke_and_single_use():
    data = wav_bytes()
    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        url = ticket(info(data))
        result = client.post(
            url,
            content=data,
            headers={
                "Content-Type": "audio/wav",
                "Origin": "https://web-sandbox.oaiusercontent.com",
            },
        )
        assert result.status_code == 200
        assert (
            result.headers["access-control-allow-origin"]
            == "https://web-sandbox.oaiusercontent.com"
        )
        download = result.json()
        assert client.get(download["download_url"]).content == data
        assert client.post(url, content=data).status_code == 404
        token = download["token"]

        async def revoke():
            async with Client(create_server("http://localhost:8000")) as mcp:
                await mcp.call_tool("revoke_exports", {"tokens": [token]})

        asyncio.run(revoke())
        assert client.get(download["download_url"]).status_code == 404


def test_upload_invalid_hash_invalid_file_size_and_expiry():
    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        data = wav_bytes()
        assert client.post(ticket(info(data)), content=data[:-1]).status_code == 422
        invalid = b"not audio data"
        assert client.post(ticket(info(invalid)), content=invalid).status_code == 422
        assert (
            client.post(ticket(info(data)), content=b"x" * (20 * 1024 * 1024 + 1)).status_code
            == 413
        )
        url = ticket(info(data))
        token = url.rsplit("/", 1)[-1]
        uploads[token] = (0, info(data))
        prune()
        assert client.post(url, content=data).status_code == 404


def test_upload_filename_and_memory_cap():
    data = wav_bytes()
    metadata = info(data).model_copy(update={"name": "../../evil\r\nHeader.wav"})
    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        result = client.post(ticket(metadata), content=data)
        assert result.status_code == 200
        assert result.json()["filename"] == "evil-Header.wav"
        exports.clear()
        exports["occupied"] = (time.monotonic() + 100, b"x" * 32_000_000, "audio/wav", "x.wav")
        assert client.post(ticket(info(data)), content=data).status_code == 503


def test_proposals_preserve_or_invalidate_timing():
    async def scenario():
        baseline = song().model_dump()
        async with Client(create_server("http://localhost:8000")) as client:
            changed = {**baseline, "title": "New title", "performance": []}
            result = await client.call_tool(
                "propose_song",
                {"document": changed, "current_document": baseline, "base_revision": 0},
            )
            assert result.data["song"]["performance"] == baseline["performance"]
            changed["arrangement"] = ["v"]
            result = await client.call_tool(
                "propose_song",
                {"document": changed, "current_document": baseline, "base_revision": 0},
            )
            assert result.data["song"]["performance"] == []

    asyncio.run(scenario())


@pytest.mark.parametrize(("extension", "media"), [("mp3", "audio/mpeg"), ("m4a", "audio/mp4")])
def test_compressed_audio_formats(extension, media):
    from pathlib import Path

    data = (Path(__file__).parent / "fixtures" / f"reference.{extension}").read_bytes()
    metadata = AudioInfo(
        name=f"reference.{extension}",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        duration=1,
        media_type=media,
    )
    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        response = client.post(ticket(metadata), content=data)
        assert response.status_code == 200
        assert client.get(response.json()["download_url"]).content == data


def test_tiny_chords_do_not_produce_overlapping_midi_notes():
    s = song()
    s.performance[0].end = s.performance[0].start + 0.00001
    with pytest.raises(ValueError, match="shorter than one MIDI tick"):
        midi_bytes(s)
