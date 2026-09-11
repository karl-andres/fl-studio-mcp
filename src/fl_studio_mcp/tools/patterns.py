"""Pattern management tools for FL Studio.

Requires FL Studio 2024+ (the `patterns` scripting module). On older versions
the tools return a clear error message instead of failing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _index_error(index: object) -> str | None:
    """Reject pattern indices FL Studio would silently turn into new patterns.

    Pattern indices are 1-based; jumping to index 0 or a negative index makes
    FL create or select unexpected patterns instead of failing.
    """
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        return f"Error: pattern index must be a positive integer (1-based), got {index!r}"
    return None


def register_pattern_tools(mcp: FastMCP) -> None:
    """Register pattern management tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_list_patterns(include_default: bool = False) -> dict:
        """List all patterns in the project.

        By default only patterns that were modified from their default state
        are listed. Set include_default=True to list all 999 potential slots
        (slow, rarely useful).

        Returns each pattern's index (1-based), name, color, length in beats
        and selection state, plus the currently active pattern.
        """
        conn = get_connection()
        return conn.send_command("patterns.getAll", {"include_default": include_default})

    @mcp.tool()
    def fl_get_current_pattern() -> dict:
        """Get the currently active pattern (index, name, length in beats)."""
        conn = get_connection()
        return conn.send_command("patterns.getCurrent")

    @mcp.tool()
    def fl_select_pattern(index: int) -> str:
        """Select and activate a pattern (1-based index).

        Note: jumping to a non-existent pattern index creates it, so stay
        within sane bounds (use fl_new_pattern for a fresh pattern).
        """
        if error := _index_error(index):
            return error
        conn = get_connection()
        result = conn.send_command("patterns.select", {"index": index})
        if result.get("error"):
            return f"Error: {result['error']}"
        return f"Selected pattern {result.get('selected')} ({result.get('name')})"

    @mcp.tool()
    def fl_new_pattern() -> str:
        """Switch to the next empty pattern (automation-safe, no name prompt).

        FL patterns are virtual; this finds and activates the next unused
        pattern, which is the practical equivalent of creating one. Give it a
        name afterwards with fl_rename_pattern.

        Note: FL reports the length of an empty pattern as the project's
        current default (often the previous pattern's length), not 0.
        """
        conn = get_connection()
        result = conn.send_command("patterns.newEmpty", {})
        if result.get("error"):
            return f"Error: {result['error']}"
        return f"Switched to empty pattern {result.get('selected')} ({result.get('name')})"

    @mcp.tool()
    def fl_clone_pattern(index: int | None = None) -> str:
        """Clone a pattern (default: the currently active one).

        Warning: FL Studio closes the piano roll when cloning, to protect you
        from editing the wrong pattern. Reopen the piano roll afterwards if
        needed.
        """
        if index is not None and (error := _index_error(index)):
            return error
        conn = get_connection()
        params = {"index": index} if index is not None else {}
        result = conn.send_command("patterns.clone", params)
        if result.get("error"):
            return f"Error: {result['error']}"
        return f"Cloned to pattern {result.get('cloned_to')} ({result.get('name')})"

    @mcp.tool()
    def fl_rename_pattern(index: int, name: str) -> str:
        """Rename the pattern at index (1-based). Empty name resets to default."""
        if error := _index_error(index):
            return error
        conn = get_connection()
        result = conn.send_command("patterns.setName", {"index": index, "name": name})
        if result.get("error"):
            return f"Error: {result['error']}"
        return f"Pattern {result.get('index')} is now named '{result.get('name')}'"
