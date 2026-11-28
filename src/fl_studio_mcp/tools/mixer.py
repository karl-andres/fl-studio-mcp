"""Mixer control tools for FL Studio."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _wait_for(
    read: Callable[[], dict[str, Any]],
    done: Callable[[dict[str, Any]], bool],
    timeout: float = 1.5,
) -> dict[str, Any]:
    """Re-read FL Studio until `done` holds or the timeout expires.

    FL applies some changes (slot mix and on/off, stereo separation) only
    after the command that made them returns, so they have to be confirmed
    with separate read commands. Returns the last read.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = read()
        if done(result) or time.monotonic() >= deadline:
            return result
        time.sleep(0.05)


def _find_slot(track_fx: dict[str, Any], slot: int) -> dict[str, Any]:
    return next((s for s in track_fx.get("slots", []) if s.get("slot") == slot), {})


def register_mixer_tools(mcp: FastMCP) -> None:
    """Register mixer control tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_get_mixer_track_count() -> int:
        """Get the total number of mixer tracks available.

        FL Studio typically has 125 mixer tracks (0-124), where track 0 is the Master.
        """
        conn = get_connection()
        result = conn.send_command("mixer.getTrackCount")

        if not result.get("success", False) and "error" in result:
            return -1  # Return -1 to indicate error

        return result.get("count", 0)

    @mcp.tool()
    def fl_get_mixer_track_info(track: int) -> dict:
        """Get detailed information about a specific mixer track.

        Includes the effects loaded in its slots (with each slot's Mix knob)
        and the tracks it sends to (with send levels).

        Args:
            track: Mixer track index (0 = Master, 1-124 = insert tracks)
        """
        conn = get_connection()
        result = conn.send_command("mixer.getTrackInfo", {"track": track})

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "index": result.get("index", track),
            "name": result.get("name", ""),
            "volume": result.get("volume", 0),
            "volume_db": result.get("volume_db", 0),
            "pan": result.get("pan", 0),
            "stereo_separation": result.get("stereo_separation", 0),
            "stereo_separation_display": result.get("stereo_separation_display", ""),
            "is_muted": result.get("is_muted", False),
            "is_solo": result.get("is_solo", False),
            "is_armed": result.get("is_armed", False),
            "color": result.get("color", "0x0"),
            "fx_slots": result.get("fx_slots", []),
            "sends_to": result.get("sends_to", []),
        }

    @mcp.tool()
    def fl_get_all_mixer_tracks(include_empty: bool = False) -> list[dict]:
        """Get information about all mixer tracks.

        Args:
            include_empty: If False, only returns tracks with non-default names.
                          If True, returns all 125 tracks.
        """
        conn = get_connection()
        result = conn.send_command("mixer.getAllTracks", {"include_empty": include_empty})

        if not result.get("success", False) and "error" in result:
            return [{"error": result["error"]}]

        return result.get("tracks", [])

    @mcp.tool()
    def fl_set_track_volume(track: int, volume: float) -> str:
        """Set the volume of a mixer track.

        Args:
            track: Mixer track index (0 = Master)
            volume: Volume level from 0.0 (silence) to 1.0 (0dB).
                   Default FL Studio volume is 0.8 (~-5.2dB).
                   Values above 1.0 may cause clipping.
        """
        if not 0.0 <= volume <= 1.25:
            return "Error: Volume should be between 0.0 and 1.25"

        conn = get_connection()
        result = conn.send_command("mixer.setTrackVolume", {
            "track": track,
            "volume": volume,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        new_vol = result.get("volume", 0)
        new_vol_db = result.get("volume_db", 0)
        return f"Track {track} volume set to {new_vol:.3f} ({new_vol_db:.1f} dB)"

    @mcp.tool()
    def fl_set_track_pan(track: int, pan: float) -> str:
        """Set the pan position of a mixer track.

        Args:
            track: Mixer track index (0 = Master)
            pan: Pan position from -1.0 (full left) to 1.0 (full right).
                 0.0 is center.
        """
        if not -1.0 <= pan <= 1.0:
            return "Error: Pan must be between -1.0 (left) and 1.0 (right)"

        conn = get_connection()
        result = conn.send_command("mixer.setTrackPan", {
            "track": track,
            "pan": pan,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        new_pan = result.get("pan", 0)
        if new_pan < -0.01:
            direction = f"{abs(new_pan) * 100:.0f}% left"
        elif new_pan > 0.01:
            direction = f"{new_pan * 100:.0f}% right"
        else:
            direction = "center"

        return f"Track {track} pan set to {direction}"

    @mcp.tool()
    def fl_mute_track(track: int, muted: bool | None = None) -> str:
        """Mute or unmute a mixer track.

        Args:
            track: Mixer track index
            muted: True to mute, False to unmute, None to toggle
        """
        conn = get_connection()
        result = conn.send_command("mixer.muteTrack", {
            "track": track,
            "muted": muted,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_muted = result.get("is_muted", False)
        track_name = result.get("track_name", f"Track {track}")
        return f"{track_name} {'muted' if is_muted else 'unmuted'}"

    @mcp.tool()
    def fl_solo_track(track: int, solo: bool | None = None, mode: int = 3) -> str:
        """Solo or unsolo a mixer track.

        Args:
            track: Mixer track index
            solo: True to solo, False to unsolo, None to toggle
            mode: Solo mode:
                  1 = Solo with source tracks
                  2 = Solo with send tracks
                  3 = Solo with both source and send tracks (default)
                  4 = Solo track only
        """
        conn = get_connection()
        result = conn.send_command("mixer.soloTrack", {
            "track": track,
            "solo": solo,
            "mode": mode,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_solo = result.get("is_solo", False)
        track_name = result.get("track_name", f"Track {track}")
        return f"{track_name} {'soloed' if is_solo else 'unsoloed'}"

    @mcp.tool()
    def fl_arm_track(track: int) -> str:
        """Toggle the recording arm state of a mixer track.

        Armed tracks will record audio when recording is enabled.

        Args:
            track: Mixer track index
        """
        conn = get_connection()
        result = conn.send_command("mixer.armTrack", {"track": track})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_armed = result.get("is_armed", False)
        track_name = result.get("track_name", f"Track {track}")
        return f"{track_name} recording {'armed' if is_armed else 'disarmed'}"

    @mcp.tool()
    def fl_set_track_name(track: int, name: str) -> str:
        """Set the name of a mixer track.

        Args:
            track: Mixer track index
            name: New name for the track. Empty string resets to default.
        """
        conn = get_connection()
        result = conn.send_command("mixer.setTrackName", {
            "track": track,
            "name": name,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Track {track} renamed to '{name}'"

    @mcp.tool()
    def fl_set_track_color(track: int, red: int, green: int, blue: int) -> str:
        """Set the color of a mixer track.

        Args:
            track: Mixer track index
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        conn = get_connection()
        result = conn.send_command("mixer.setTrackColor", {
            "track": track,
            "r": red,
            "g": green,
            "b": blue,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Track {track} color set to RGB({red}, {green}, {blue})"

    @mcp.tool()
    def fl_set_stereo_separation(track: int, separation: float) -> str:
        """Set the stereo separation of a mixer track.

        Args:
            track: Mixer track index
            separation: -1.0 (100% separated, widest) to 1.0 (100% merged, mono).
                       0.0 is the original stereo image (default). Negative
                       values widen, positive values narrow.
        """
        if not -1.0 <= separation <= 1.0:
            return "Error: Separation must be between -1.0 and 1.0"

        conn = get_connection()
        result = conn.send_command("mixer.setStereoSep", {
            "track": track,
            "separation": separation,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        # FL stores separation in 1/64 steps, hence the tolerance
        info = _wait_for(
            lambda: conn.send_command("mixer.getTrackInfo", {"track": track}),
            lambda r: abs(r.get("stereo_separation", 99) - separation) < 0.02,
        )
        actual = info.get("stereo_separation", 0.0)
        display = info.get("stereo_separation_display", "")
        if abs(actual - separation) >= 0.02:
            return (
                f"Error: track {track} stereo separation is still {actual:.2f} ({display}) "
                f"instead of {separation:.2f}"
            )
        return f"Track {track} stereo separation set to {actual:.2f} ({display})"

    @mcp.tool()
    def fl_get_track_fx(track: int) -> dict:
        """List the effects loaded on a mixer track, with each slot's Mix knob.

        Every effect slot has its own Mix knob (dry/wet, 0-100%) next to the
        plugin name in the mixer. It scales the whole effect: a reverb whose
        own wet parameter is at maximum but whose slot Mix is at 15% is only
        15% audible. Always check it before judging how strong an effect is.

        Args:
            track: Mixer track index (0 = Master)

        Returns slots_enabled (the track's "enable effect slots" switch) and,
        for each loaded slot: slot index (0-9), plugin name, enabled (False =
        slot bypassed), mix (0.0-1.0) and mix_display (as FL shows it).
        """
        conn = get_connection()
        result = conn.send_command("mixer.getTrackFx", {"track": track})

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "track": result.get("track", track),
            "track_name": result.get("track_name", ""),
            "slots_enabled": result.get("slots_enabled", True),
            "slots": result.get("slots", []),
        }

    @mcp.tool()
    def fl_set_fx_mix(track: int, slot: int, mix: float) -> str:
        """Set the Mix (dry/wet) knob of an effect slot on a mixer track.

        This is the slot's own Mix knob in the mixer, not a plugin parameter.

        Args:
            track: Mixer track index (0 = Master)
            slot: Effect slot index (0-9)
            mix: 0.0 (effect inaudible) to 1.0 (100%, FL's default)
        """
        if not 0.0 <= mix <= 1.0:
            return "Error: Mix must be between 0.0 and 1.0"

        conn = get_connection()
        result = conn.send_command("mixer.setSlotMix", {
            "track": track,
            "slot": slot,
            "mix": mix,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        track_fx = _wait_for(
            lambda: conn.send_command("mixer.getTrackFx", {"track": track}),
            lambda r: abs(_find_slot(r, slot).get("mix", -1.0) - mix) < 0.01,
        )
        state = _find_slot(track_fx, slot)
        name = result.get("name", f"Slot {slot}")
        if abs(state.get("mix", -1.0) - mix) >= 0.01:
            return (
                f"Error: track {track} slot {slot} ({name}) mix is still "
                f"{state.get('mix_display', 'unknown')}"
            )
        return f"Track {track} slot {slot} ({name}) mix set to {state.get('mix_display')}"

    @mcp.tool()
    def fl_set_fx_enabled(track: int, slot: int, enabled: bool) -> str:
        """Turn an effect slot on or off (bypass) on a mixer track.

        Args:
            track: Mixer track index (0 = Master)
            slot: Effect slot index (0-9)
            enabled: True to turn the effect on, False to bypass it
        """
        conn = get_connection()
        result = conn.send_command("mixer.setSlotEnabled", {
            "track": track,
            "slot": slot,
            "enabled": enabled,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        track_fx = _wait_for(
            lambda: conn.send_command("mixer.getTrackFx", {"track": track}),
            lambda r: _find_slot(r, slot).get("enabled") == enabled,
        )
        name = result.get("name", f"Slot {slot}")
        if _find_slot(track_fx, slot).get("enabled") != enabled:
            return f"Error: FL Studio did not confirm the change on track {track} slot {slot}"
        return f"Track {track} slot {slot} ({name}) is now {'on' if enabled else 'bypassed'}"

    @mcp.tool()
    def fl_get_track_routing(track: int) -> dict:
        """Show where a mixer track's audio goes and which tracks feed into it.

        Args:
            track: Mixer track index (0 = Master)

        Returns sends_to (each destination with its send level, 0.0-1.0 where
        0.8 is 0 dB, plus level_display as FL shows it) and receives_from.
        By default every insert track sends to the Master (track 0).
        """
        conn = get_connection()
        result = conn.send_command("mixer.getRouting", {"track": track})

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "track": result.get("track", track),
            "track_name": result.get("track_name", ""),
            "sends_to": result.get("sends_to", []),
            "receives_from": result.get("receives_from", []),
        }

    @mcp.tool()
    def fl_route_track(
        src_track: int,
        dst_track: int,
        enabled: bool = True,
        level: float | None = None,
        exclusive: bool = False,
    ) -> str:
        """Route (send) one mixer track to another, or remove that route.

        Use it to send tracks to a bus, to add a parallel send to an FX track
        (reverb/delay bus), or to feed a sidechain.

        Args:
            src_track: Mixer track the audio comes from
            dst_track: Mixer track the audio goes to (0 = Master)
            enabled: True to create the route, False to remove it
            level: Send level from 0.0 to 1.0, on FL's fader curve: 0.8 = 0 dB
                   (FL's default), 0.6 = -6 dB, 0.5 = -9.2 dB, 1.0 = +5.6 dB.
                   None leaves the current level untouched.
            exclusive: True to remove every other output of src_track first
                       (FL's "Route to this track only"), e.g. to send a track
                       to a bus instead of straight to the Master.
        """
        if level is not None and not 0.0 <= level <= 1.0:
            return "Error: Level must be between 0.0 and 1.0"

        conn = get_connection()
        result = conn.send_command("mixer.setRoute", {
            "src": src_track,
            "dst": dst_track,
            "enabled": enabled,
            "level": level,
            "exclusive": exclusive,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        if result.get("active", False) != enabled:
            return (
                f"Error: FL Studio did not {'create' if enabled else 'remove'} the route "
                f"from track {src_track} to track {dst_track}"
            )

        sends = ", ".join(
            f"track {s.get('track')} '{s.get('name', '')}' at {s.get('level_display', '')}"
            for s in result.get("sends_to", [])
        )
        src_name = result.get("src_name", f"Track {src_track}")
        return f"{src_name} now sends to: {sends or 'nothing'}"
