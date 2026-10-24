"""Playlist track and arrangement marker tools for FL Studio.

Playlist tracks are 1-based in FL Studio's API (unlike mixer tracks and
channels, which are 0-based). Placing or moving clips on the playlist is not
possible through the MIDI scripting API; these tools cover track properties
and time markers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fl_studio_mcp.utils.validation import rgb_error

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _track_error(track) -> str | None:
    """Validate a 1-based playlist track index before talking to FL Studio."""
    if isinstance(track, bool) or not isinstance(track, int):
        return "Error: track must be an integer"
    if track < 1:
        return "Error: playlist tracks are 1-based; track must be >= 1"
    return None


def register_playlist_tools(mcp: FastMCP) -> None:
    """Register playlist and arrangement tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_get_playlist_tracks(include_default: bool = False) -> dict:
        """List playlist tracks (name, color, mute/solo state).

        By default only tracks changed from their stock state (renamed,
        muted or soloed) are returned. A track whose only change is its color
        is not detected: FL exposes no stock-color baseline to compare against.
        Set include_default=True to list all 500 (slow, rarely useful).
        """
        conn = get_connection()
        result = conn.send_command("playlist.getTracks", {
            "include_default": include_default,
        })

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {"tracks": result.get("tracks", []), "count": result.get("count", 0)}

    @mcp.tool()
    def fl_set_playlist_track_name(track: int, name: str) -> str:
        """Rename a playlist track.

        Args:
            track: Playlist track index (1-based)
            name: New name. Empty string resets to default.
        """
        err = _track_error(track)
        if err:
            return err

        conn = get_connection()
        result = conn.send_command("playlist.setTrackName", {
            "track": track,
            "name": name,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Playlist track {track} renamed to '{result.get('name', name)}'"

    @mcp.tool()
    def fl_set_playlist_track_color(track: int, red: int, green: int, blue: int) -> str:
        """Set the color of a playlist track.

        Args:
            track: Playlist track index (1-based)
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        err = _track_error(track) or rgb_error(red, green, blue)
        if err:
            return err

        conn = get_connection()
        result = conn.send_command("playlist.setTrackColor", {
            "track": track,
            "r": red,
            "g": green,
            "b": blue,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Playlist track {track} color set to RGB({red}, {green}, {blue})"

    @mcp.tool()
    def fl_mute_playlist_track(track: int, muted: bool | None = None) -> str:
        """Mute or unmute a playlist track.

        Args:
            track: Playlist track index (1-based)
            muted: True to mute, False to unmute, None to toggle
        """
        err = _track_error(track)
        if err:
            return err

        conn = get_connection()
        result = conn.send_command("playlist.muteTrack", {
            "track": track,
            "muted": muted,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        name = result.get("name", f"Track {track}")
        return f"Playlist track '{name}' {'muted' if result.get('is_muted') else 'unmuted'}"

    @mcp.tool()
    def fl_solo_playlist_track(track: int, solo: bool | None = None) -> str:
        """Solo or unsolo a playlist track.

        Args:
            track: Playlist track index (1-based)
            solo: True to solo, False to unsolo, None to toggle
        """
        err = _track_error(track)
        if err:
            return err

        conn = get_connection()
        result = conn.send_command("playlist.soloTrack", {
            "track": track,
            "solo": solo,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        name = result.get("name", f"Track {track}")
        return f"Playlist track '{name}' {'soloed' if result.get('is_solo') else 'unsoloed'}"

    @mcp.tool()
    def fl_add_marker(name: str, time_beats: float | None = None) -> str:
        """Add a time marker to the arrangement (for song sections: intro, drop...).

        Args:
            name: Marker name
            time_beats: Position in beats from song start (e.g. bar 5 in 4/4 = 16.0).
                        None places the marker at the current playhead position.
        """
        if time_beats is not None:
            if isinstance(time_beats, bool) or not isinstance(time_beats, (int, float)):
                return "Error: time_beats must be a number"
            if time_beats < 0:
                return "Error: time_beats must be >= 0"

        conn = get_connection()
        result = conn.send_command("arrangement.addMarker", {
            "name": name,
            "time_beats": time_beats,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        beats = result.get("time_beats", time_beats)
        return f"Marker '{name}' added at beat {beats:g}"

    @mcp.tool()
    def fl_list_markers() -> dict:
        """List the arrangement's time markers in timeline order."""
        conn = get_connection()
        result = conn.send_command("arrangement.getMarkers")

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {"markers": result.get("markers", [])}

    @mcp.tool()
    def fl_jump_to_marker(direction: str = "next") -> str:
        """Jump the playhead to the next or previous arrangement marker.

        Args:
            direction: "next" or "prev"
        """
        if direction not in ("next", "prev"):
            return "Error: direction must be 'next' or 'prev'"

        conn = get_connection()
        result = conn.send_command("arrangement.jumpToMarker", {"direction": direction})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Jumped to {direction} marker"

    @mcp.tool()
    def fl_get_arrangement_position() -> dict:
        """Get the playhead position and timeline selection (ticks and beats)."""
        conn = get_connection()
        result = conn.send_command("arrangement.getTime")

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        result.pop("success", None)
        return result
