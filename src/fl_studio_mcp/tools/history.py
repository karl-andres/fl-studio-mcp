"""Undo/redo safety tools for FL Studio.

These let an AI assistant create an undo point before batch edits and roll
back cleanly when something went wrong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Names accepted by fl_save_undo_point; mirrors _UNDO_FLAGS in the controller
# script (FL's UF_* flags for general.saveUndo).
UNDO_FLAG_NAMES = (
    "none",
    "ee",
    "pr",
    "playlist",
    "knob",
    "audio_rec",
    "auto_clip",
    "pr_marker",
    "pl_marker",
    "plugin",
    "ss_looping",
    "reset",
)
DEFAULT_UNDO_FLAGS = ["pr", "playlist", "knob", "ss_looping"]


def register_history_tools(mcp: FastMCP) -> None:
    """Register undo/redo tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_save_undo_point(
        name: str = "MCP undo point",
        flags: list[str] | None = None,
    ) -> dict:
        """Create an undo point in FL Studio's history.

        Call this BEFORE making batch edits so tracked changes can be rolled
        back with fl_undo. Note: not every scripting mutation is tracked by
        FL's undo system (e.g. pattern renames are not); user actions and
        piano-roll edits are.

        Args:
            name: Descriptive label shown in the undo history.
            flags: What to include, as strings combined automatically:
                none, ee, pr (piano roll), playlist, knob, audio_rec,
                auto_clip, pr_marker, pl_marker, plugin, ss_looping, reset.
                Default covers piano roll, playlist, knobs and step sequencer.
        """
        if flags is None:
            flags = DEFAULT_UNDO_FLAGS
        elif isinstance(flags, str):
            flags = [flags]
        # An explicitly empty list is a valid request for flag mask 0 (UF_None).
        flags = [str(f).lower() for f in flags]
        unknown = [f for f in flags if f not in UNDO_FLAG_NAMES]
        if unknown:
            # Fail loudly: silently ignoring a flag would create an undo point
            # that does not cover what the caller assumed.
            return {
                "error": f"Unknown undo flag(s): {', '.join(unknown)}. "
                f"Valid flags: {', '.join(UNDO_FLAG_NAMES)}"
            }
        conn = get_connection()
        return conn.send_command("general.saveUndoPoint", {"name": name, "flags": flags})

    @mcp.tool()
    def fl_undo() -> dict:
        """Undo the last change (classic undo, like Ctrl+Z).

        Reverts user actions and tracked edits (piano roll, playlist...).
        Some scripting mutations (e.g. pattern renames) are not tracked by
        FL's undo system and cannot be reverted this way.
        """
        conn = get_connection()
        return conn.send_command("general.undo")

    @mcp.tool()
    def fl_redo() -> dict:
        """Redo the last undone change."""
        conn = get_connection()
        return conn.send_command("general.redo")

    @mcp.tool()
    def fl_get_undo_status() -> dict:
        """Get undo history status (count, position, hints, project-changed flag)."""
        conn = get_connection()
        return conn.send_command("general.getUndoStatus")
