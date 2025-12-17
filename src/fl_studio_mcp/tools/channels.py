"""Channel rack control tools for FL Studio."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_channel_tools(mcp: FastMCP) -> None:
    """Register channel rack tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_get_channel_count(global_count: bool = True) -> int:
        """Get the number of channels in the channel rack.

        Args:
            global_count: If True, returns total channels ignoring groups.
                         If False, returns channels in current group only.
        """
        conn = get_connection()
        result = conn.send_command("channels.getCount", {"global_count": global_count})

        if not result.get("success", False) and "error" in result:
            return -1

        return result.get("count", 0)

    @mcp.tool()
    def fl_get_channel_info(index: int, use_global_index: bool = True) -> dict:
        """Get detailed information about a channel.

        Args:
            index: Channel index
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("channels.getInfo", {
            "index": index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "index": result.get("index", index),
            "name": result.get("name", ""),
            "color": result.get("color", "0x0"),
            "volume": result.get("volume", 0),
            "pan": result.get("pan", 0),
            "pitch": result.get("pitch", 0),
            "is_muted": result.get("is_muted", False),
            "is_solo": result.get("is_solo", False),
            "is_selected": result.get("is_selected", False),
            "target_fx_track": result.get("target_fx_track", 0),
        }

    @mcp.tool()
    def fl_get_all_channels() -> list[dict]:
        """Get information about all channels in the channel rack.

        Returns a list of all channels with their basic properties.
        """
        conn = get_connection()
        result = conn.send_command("channels.getAll")

        if not result.get("success", False) and "error" in result:
            return [{"error": result["error"]}]

        return result.get("channels", [])

    @mcp.tool()
    def fl_get_selected_channel() -> dict | None:
        """Get information about the currently selected channel.

        Returns None if no channel is selected.
        """
        conn = get_connection()
        result = conn.send_command("channels.getSelected")

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return result.get("channel")

    @mcp.tool()
    def fl_select_channel(index: int, select: bool = True) -> str:
        """Select or deselect a channel.

        Args:
            index: Channel index (global)
            select: True to select, False to deselect
        """
        conn = get_connection()
        result = conn.send_command("channels.select", {
            "index": index,
            "select": select,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {index}")
        return f"Channel '{channel_name}' {'selected' if select else 'deselected'}"

    @mcp.tool()
    def fl_select_one_channel(index: int) -> str:
        """Select only one channel, deselecting all others.

        Args:
            index: Channel index (global) to select exclusively
        """
        conn = get_connection()
        result = conn.send_command("channels.selectOne", {"index": index})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {index}")
        return f"Channel '{channel_name}' selected exclusively"

    @mcp.tool()
    def fl_trigger_note(
        channel: int,
        note: int,
        velocity: int = 100,
        midi_channel: int = -1
    ) -> str:
        """Trigger a MIDI note on a channel (real-time, does NOT persist to pattern).

        This triggers the note in real-time. To persist notes in a pattern,
        FL Studio must be in record mode, or use the step sequencer functions.

        Args:
            channel: Channel index (global)
            note: MIDI note number (0-127, where 60 = C5/Middle C)
            velocity: Note velocity (1-127, 0 = note off)
            midi_channel: MIDI channel (-1 for default)
        """
        if not 0 <= note <= 127:
            return "Error: Note must be between 0 and 127"
        if not 0 <= velocity <= 127:
            return "Error: Velocity must be between 0 and 127"

        conn = get_connection()
        result = conn.send_command("channels.triggerNote", {
            "channel": channel,
            "note": note,
            "velocity": velocity,
            "midi_channel": midi_channel,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        note_name = note_names[note % 12]
        octave = (note // 12) - 1

        if velocity == 0:
            return f"Note {note_name}{octave} (MIDI {note}) released on channel {channel}"
        return f"Note {note_name}{octave} (MIDI {note}) triggered with velocity {velocity} on channel {channel}"

    @mcp.tool()
    def fl_set_channel_volume(index: int, volume: float) -> str:
        """Set the volume of a channel.

        Args:
            index: Channel index (global)
            volume: Volume level from 0.0 (silence) to 1.0 (full)
        """
        if not 0.0 <= volume <= 1.0:
            return "Error: Volume must be between 0.0 and 1.0"

        conn = get_connection()
        result = conn.send_command("channels.setVolume", {
            "index": index,
            "volume": volume,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {index}")
        new_volume = result.get("volume", volume)
        return f"Channel '{channel_name}' volume set to {new_volume:.2f}"

    @mcp.tool()
    def fl_set_channel_pan(index: int, pan: float) -> str:
        """Set the pan position of a channel.

        Args:
            index: Channel index (global)
            pan: Pan from -1.0 (full left) to 1.0 (full right), 0.0 = center
        """
        if not -1.0 <= pan <= 1.0:
            return "Error: Pan must be between -1.0 and 1.0"

        conn = get_connection()
        result = conn.send_command("channels.setPan", {
            "index": index,
            "pan": pan,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {index}")
        new_pan = result.get("pan", pan)
        return f"Channel '{channel_name}' pan set to {new_pan:.2f}"

    @mcp.tool()
    def fl_mute_channel(index: int, muted: bool | None = None) -> str:
        """Mute or unmute a channel.

        Args:
            index: Channel index (global)
            muted: True to mute, False to unmute, None to toggle
        """
        conn = get_connection()
        result = conn.send_command("channels.mute", {
            "index": index,
            "muted": muted,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_muted = result.get("is_muted", False)
        channel_name = result.get("channel_name", f"Channel {index}")
        return f"Channel '{channel_name}' {'muted' if is_muted else 'unmuted'}"

    @mcp.tool()
    def fl_solo_channel(index: int, solo: bool | None = None) -> str:
        """Solo or unsolo a channel.

        Args:
            index: Channel index (global)
            solo: True to solo, False to unsolo, None to toggle
        """
        conn = get_connection()
        result = conn.send_command("channels.solo", {
            "index": index,
            "solo": solo,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_solo = result.get("is_solo", False)
        channel_name = result.get("channel_name", f"Channel {index}")
        return f"Channel '{channel_name}' {'soloed' if is_solo else 'unsoloed'}"

    @mcp.tool()
    def fl_set_channel_name(index: int, name: str) -> str:
        """Set the name of a channel.

        Args:
            index: Channel index (global)
            name: New name for the channel
        """
        conn = get_connection()
        result = conn.send_command("channels.setName", {
            "index": index,
            "name": name,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Channel {index} renamed to '{name}'"

    @mcp.tool()
    def fl_set_channel_color(index: int, red: int, green: int, blue: int) -> str:
        """Set the color of a channel.

        Args:
            index: Channel index (global)
            red: Red component (0-255)
            green: Green component (0-255)
            blue: Blue component (0-255)
        """
        conn = get_connection()
        result = conn.send_command("channels.setColor", {
            "index": index,
            "r": red,
            "g": green,
            "b": blue,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Channel {index} color set to RGB({red}, {green}, {blue})"

    @mcp.tool()
    def fl_route_channel_to_mixer(channel_index: int, mixer_track: int) -> str:
        """Route a channel to a specific mixer track.

        Args:
            channel_index: Channel index (global)
            mixer_track: Mixer track index to route to
        """
        conn = get_connection()
        result = conn.send_command("channels.routeToMixer", {
            "channel_index": channel_index,
            "mixer_track": mixer_track,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {channel_index}")
        return f"Channel '{channel_name}' routed to mixer track {mixer_track}"

    # Step Sequencer Tools

    @mcp.tool()
    def fl_get_grid_bit(channel: int, position: int) -> bool:
        """Get whether a step is active in the step sequencer.

        Args:
            channel: Channel index (global)
            position: Step position (0-based)
        """
        conn = get_connection()
        result = conn.send_command("channels.getGridBit", {
            "channel": channel,
            "position": position,
        })

        if not result.get("success", False) and "error" in result:
            return False

        return result.get("value", False)

    @mcp.tool()
    def fl_set_grid_bit(channel: int, position: int, value: bool) -> str:
        """Set a step in the step sequencer on or off.

        This allows basic pattern programming for drum-style instruments.

        Args:
            channel: Channel index (global)
            position: Step position (0-based)
            value: True to enable the step, False to disable
        """
        conn = get_connection()
        result = conn.send_command("channels.setGridBit", {
            "channel": channel,
            "position": position,
            "value": value,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {channel}")
        return f"Channel '{channel_name}' step {position} {'enabled' if value else 'disabled'}"

    @mcp.tool()
    def fl_get_step_sequence(channel: int, steps: int = 16) -> list[bool]:
        """Get the step sequence pattern for a channel.

        Args:
            channel: Channel index (global)
            steps: Number of steps to retrieve (default 16)
        """
        conn = get_connection()
        result = conn.send_command("channels.getStepSequence", {
            "channel": channel,
            "steps": steps,
        })

        if not result.get("success", False) and "error" in result:
            return []

        return result.get("sequence", [])

    @mcp.tool()
    def fl_set_step_sequence(channel: int, pattern: list[bool]) -> str:
        """Set a complete step sequence pattern for a channel.

        Args:
            channel: Channel index (global)
            pattern: List of boolean values for each step (True = on, False = off)
        """
        conn = get_connection()
        result = conn.send_command("channels.setStepSequence", {
            "channel": channel,
            "pattern": pattern,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        channel_name = result.get("channel_name", f"Channel {channel}")
        active_steps = result.get("active_steps", sum(pattern))
        total_steps = result.get("total_steps", len(pattern))
        return f"Channel '{channel_name}' pattern set with {active_steps}/{total_steps} steps active"
