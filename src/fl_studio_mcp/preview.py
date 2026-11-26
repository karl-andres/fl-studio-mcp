"""Read-only MCP preview for the open FL Studio session."""

from threading import Lock

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from fl_studio_mcp.utils.connection import get_connection

mcp = FastMCP("fl-studio-preview")
bridge_lock = Lock()
read_only = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


@mcp.tool(annotations=read_only)
def fl_list_mixer_tracks(include_empty: bool = False) -> dict:
    """List mixer tracks in the open project. Include default-named tracks if requested."""
    with bridge_lock:
        return get_connection().send_command(
            "mixer.getAllTracks", {"include_empty": include_empty}
        )


@mcp.tool(annotations=read_only)
def fl_get_playback_status() -> dict:
    """Read playback, recording, and position from the open FL Studio session."""
    with bridge_lock:
        return get_connection().send_command("transport.getStatus")


def main() -> None:
    """Serve the preview over local stdio."""
    mcp.run(transport="stdio")
