"""Window and focus tools for FL Studio.

FL Studio keeps its own notion of which of its windows (mixer, channel rack,
playlist, piano roll, browser) is focused, independent of the OS window. These
tools read and set that state through the controller script's `ui` module.

The piano roll is the important case: an open piano roll does not follow a
channel selected via scripting; hiding it, selecting the channel and showing
it again does retarget it (fl_open_piano_roll). The piano roll script trigger
(Ctrl+Alt+Y) only works while the piano roll is FL's focused window, and FL
applies focus changes only while its main window is the active OS window.

FL Studio 2026 reports a focused piano roll's caption as "Piano roll -"
without the channel name, so the piano roll's current target cannot be read
back - set it explicitly with fl_open_piano_roll instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

WINDOW_NAMES = ("mixer", "channel_rack", "playlist", "piano_roll", "browser")


def _window_error(window: str) -> str | None:
    if window not in WINDOW_NAMES:
        return f"Error: unknown window '{window}'. Valid: {', '.join(WINDOW_NAMES)}"
    return None


def register_ui_tools(mcp: FastMCP) -> None:
    """Register window/focus tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_get_focused_window() -> dict:
        """Report which FL Studio windows are visible and which one has focus.

        Returns per-window visible/focused flags plus the focused window's
        caption and form id. Note that FL does not include the target channel
        in the piano roll's caption; use fl_open_piano_roll to set it.
        """
        conn = get_connection()
        return conn.send_command("ui.getFocus")

    @mcp.tool()
    def fl_show_window(window: str = "piano_roll", focus: bool = True) -> dict:
        """Show an FL Studio window and (by default) give it FL-internal focus.

        Args:
            window: mixer, channel_rack, playlist, piano_roll or browser
            focus: also make it FL's focused window (default True)
        """
        if error := _window_error(window):
            return {"error": error}
        conn = get_connection()
        return conn.send_command("ui.showWindow", {"window": window, "focus": focus})

    @mcp.tool()
    def fl_hide_window(window: str) -> dict:
        """Hide an FL Studio window (mixer, channel_rack, playlist, piano_roll, browser)."""
        if error := _window_error(window):
            return {"error": error}
        conn = get_connection()
        return conn.send_command("ui.hideWindow", {"window": window})

    @mcp.tool()
    def fl_focus_window(window: str = "piano_roll") -> dict:
        """Give an FL Studio window FL-internal focus without changing visibility.

        Args:
            window: mixer, channel_rack, playlist, piano_roll or browser
        """
        if error := _window_error(window):
            return {"error": error}
        conn = get_connection()
        return conn.send_command("ui.setFocus", {"window": window})

    @mcp.tool()
    def fl_open_piano_roll(channel: int | None = None) -> dict:
        """Retarget the piano roll to a channel and make it FL's focused window.

        Hides the piano roll, selects the channel (global index) in the
        channel rack and shows the piano roll again - the only sequence that
        makes an open piano roll switch channels from a script. Use it before
        fl_send_notes whenever the notes must land on a specific channel.
        Without `channel` the piano roll is only shown and focused; its target
        is left unchanged. Returns the selected channel and focus state.
        """
        if channel is not None and (isinstance(channel, bool) or channel < 0):
            return {"error": f"Error: channel must be a non-negative global index, got {channel!r}"}
        conn = get_connection()
        params = {} if channel is None else {"index": channel}
        return conn.send_command("pianoroll.open", params)
