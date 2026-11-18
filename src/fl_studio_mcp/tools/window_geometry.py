"""Expose physical window geometry without using the MIDI controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fl_studio_mcp.utils import windows_geometry

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_window_geometry_tools(mcp: FastMCP) -> None:
    """Register Windows form discovery and repositioning tools."""

    @mcp.tool()
    def fl_list_windows() -> list[dict]:
        """List visible FL forms, including the main window, Mixer and Playlist."""
        return windows_geometry.list_windows()

    @mcp.tool()
    def fl_move_window(
        hwnd: int,
        expected_pid: int,
        expected_title: str,
        expected_bounds: tuple[int, int, int, int],
        x: int,
        y: int,
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        """Move an observed FL form to physical screen coordinates and read its new bounds.

        Copy handle, PID, title and bounds from fl_list_windows. Supply both size fields only to
        resize. FL may adjust or reject the requested geometry, especially for docked windows.
        """
        return windows_geometry.move_window(
            hwnd, expected_pid, expected_title, expected_bounds, x, y, width, height
        )
