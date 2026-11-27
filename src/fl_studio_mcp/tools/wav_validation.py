"""Inspect completed WAV renders without connecting to FL Studio."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fl_studio_mcp.utils.wav_validation import inspect_wav

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_wav_validation_tools(mcp: FastMCP) -> None:
    """Register the read-only WAV checks."""

    @mcp.tool()
    def fl_verify_audio_output(
        audio_path: str, expected_duration: float | None = None, max_frames: int = 5_000_000
    ) -> dict:
        """Inspect a local PCM or float WAV render for duration, signal and full-scale samples.

        A partial scan never passes. The check does not create a render or judge the mix.
        """
        return inspect_wav(audio_path, max_frames=max_frames, expected_duration=expected_duration)
