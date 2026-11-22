"""Pattern and playlist track tools for FL Studio."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_arrangement_tools(mcp: FastMCP) -> None:
    """Register pattern and playlist track tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    def call(action: str, **params) -> dict:
        result = get_connection().send_command(action, params)
        return result if result.get("success") else {"error": result.get("error", "Unknown error")}

    @mcp.tool()
    def fl_get_patterns() -> dict:
        """List all patterns with their name and color (hex)."""
        return call("patterns.getAll")

    @mcp.tool()
    def fl_set_pattern(pattern: int, name: str, red: int, green: int, blue: int) -> dict:
        """Set the name and color of a pattern.

        Args:
            pattern: Pattern number (1-based)
            name: New name for the pattern
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        return call("patterns.set", index=pattern, name=name, r=red, g=green, b=blue)

    @mcp.tool()
    def fl_get_playlist_tracks() -> dict:
        """List playlist tracks that have a custom name, with name and color (hex)."""
        return call("playlist.getTracks")

    @mcp.tool()
    def fl_set_playlist_track(track: int, name: str, red: int, green: int, blue: int) -> dict:
        """Set the name and color of a playlist track.

        Args:
            track: Playlist track number (1-based)
            name: New name for the track
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        return call("playlist.setTrack", index=track, name=name, r=red, g=green, b=blue)
