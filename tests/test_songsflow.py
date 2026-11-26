import io

import mido
import pytest
from pydantic import ValidationError

from songsflow.music import Song, events, midi_bytes, pitches
from songsflow.server import create_app, exports, prune, store


def document(meter="4/4"):
    return dict(
        version=1,
        revision=0,
        title="Test",
        tempo=120,
        meter=meter,
        sections=[
            dict(
                id="v",
                name="Verse",
                lyrics="Hello 🌎",
                chords=[
                    dict(id="c", symbol="Am7", anchor=0, beats=1.5),
                    dict(id="d", symbol="F", anchor=6, beats=3),
                ],
            )
        ],
        arrangement=["v", "v"],
    )


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("C", [48, 52, 55]),
        ("Am", [57, 60, 64]),
        ("Bb7", [58, 62, 65, 68]),
        ("C#m7", [49, 52, 56, 59]),
        ("Db", [49, 53, 56]),
    ],
)
def test_chords(symbol, expected):
    assert pitches(symbol) == expected


@pytest.mark.parametrize("meter", ["4/4", "3/4", "6/8"])
def test_midi_matches_preview(meter):
    song = Song.model_validate(document(meter))
    preview = events(song)
    midi = mido.MidiFile(file=io.BytesIO(midi_bytes(song)))
    tick, sounding, rendered = 0, {}, []
    for msg in midi.tracks[0]:
        tick += msg.time
        if msg.type == "note_on":
            assert msg.note not in sounding
            sounding[msg.note] = tick
        elif msg.type == "note_off":
            rendered.append((sounding.pop(msg.note), tick, msg.note))
    expected = [
        (round(e["start"] * 480), round((e["start"] + e["beats"]) * 480), n)
        for e in preview
        for n in e["notes"]
    ]
    assert sorted(rendered) == sorted(expected)
    assert not sounding
    assert tick == 9 * 480
    signature = next(msg for msg in midi.tracks[0] if msg.type == "time_signature")
    assert (signature.numerator, signature.denominator) == tuple(map(int, meter.split("/")))
    assert sum(msg.type == "marker" for msg in midi.tracks[0]) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.update(tempo=0),
        lambda s: s.update(arrangement=["missing"]),
        lambda s: s["sections"][0]["chords"][0].update(symbol="<script>"),
        lambda s: s["sections"][0]["chords"][0].update(beats=float("nan")),
        lambda s: s["sections"][0]["chords"][0].update(beats=0.25),
        lambda s: s["sections"][0]["chords"][0].update(anchor=99),
        lambda s: s["sections"].append(s["sections"][0]),
    ],
)
def test_invalid_song(mutation):
    s = document()
    mutation(s)
    with pytest.raises(ValidationError):
        Song.model_validate(s)


def test_too_many_arranged_events():
    s = document()
    s["sections"][0]["chords"] = [dict(id=str(i), symbol="C", anchor=0, beats=4) for i in range(11)]
    s["arrangement"] = ["v"] * 1000
    with pytest.raises(ValidationError):
        Song.model_validate(s)


def test_expiry_and_capacity():
    exports.clear()
    token = store(b"hello", "audio/midi", "test.mid")
    assert len(token) >= 40
    _, data, media, name = exports[token]
    exports[token] = (0, data, media, name)
    prune()
    assert token not in exports


def test_http_guards_and_downloads():
    from starlette.testclient import TestClient

    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        assert client.get("/health").json() == {"status": "ok"}
        token = store(b"MThd", "audio/midi", "test.mid")
        result = client.get("/downloads/" + token)
        assert result.content == b"MThd"
        assert result.headers["cache-control"] == "no-store"
        assert client.get("/downloads/not-a-token").status_code == 404
        assert client.post("/mcp", content=b"x" * 1_048_577).status_code == 413
        for _ in range(120):
            result = client.get("/health")
        assert result.status_code == 429


def test_public_requires_tls():
    with pytest.raises(ValueError):
        create_app("http://example.com")


def test_mcp_tool_flow():
    import asyncio

    from fastmcp import Client

    from songsflow.server import URI, create_server

    async def scenario():
        async with Client(create_server("http://localhost:8000")) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            assert names == {
                "open_song",
                "validate_song",
                "propose_song",
                "export_song",
                "revoke_exports",
                "prepare_audio_export",
            }
            assert all(not name.startswith("fl_") for name in names)
            tool = next(t for t in tools if t.name == "open_song")
            assert tool.meta["openai/outputTemplate"] == URI
            resources = await client.read_resource(URI)
            assert "SongsFlow" in resources[0].text
            result = await client.call_tool("validate_song", {"document": document()})
            assert len(result.data["events"]) == 4
            result = await client.call_tool(
                "propose_song",
                {"document": document(), "base_revision": 0, "current_document": document()},
            )
            assert result.data["action"] == "proposal"
            result = await client.call_tool("export_song", {"document": document()})
            token = result.data["token"]
            assert exports[token][1].startswith(b"MThd")
            assert token in result.data["download_url"]
            await client.call_tool("revoke_exports", {"tokens": [token]})
            assert token not in exports

    asyncio.run(scenario())


def test_unicode_markers():
    s = document()
    s["sections"][0]["name"] = "Chœur 🌎"
    midi = mido.MidiFile(file=io.BytesIO(midi_bytes(Song.model_validate(s))), charset="utf8")
    assert next(msg.text for msg in midi.tracks[0] if msg.type == "marker") == "Chœur 🌎"


def test_http_origin_and_host_protection():
    from starlette.testclient import TestClient

    with TestClient(
        create_app("http://localhost:8000"), base_url="http://localhost:8000"
    ) as client:
        response = client.post("/mcp", json={}, headers={"Origin": "https://evil.example"})
        assert response.status_code == 403
        response = client.post("/mcp", json={}, headers={"Host": "evil.example"})
        assert response.status_code == 421
