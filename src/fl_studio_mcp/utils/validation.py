"""Shared argument validation for MCP tools (runs before talking to FL Studio)."""

from __future__ import annotations


def rgb_error(red, green, blue) -> str | None:
    """Validate RGB components; the controller packs them into 0xRRGGBB."""
    for label, value in (("red", red), ("green", green), ("blue", blue)):
        if isinstance(value, bool) or not isinstance(value, int):
            return f"Error: {label} must be an integer 0-255, got {value!r}"
        if not 0 <= value <= 255:
            return f"Error: {label} must be in range 0-255, got {value}"
    return None
