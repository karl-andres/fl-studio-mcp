"""Look up installed plugins in FL Studio's Plugin database.

FL Studio keeps one .fst preset per installed plugin under
Documents/Image-Line/FL Studio/Presets/Plugin database (refreshed by the
Plugin Manager). Loading one of these presets loads the plugin itself, which
is how the MCP server can add effects and instruments by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

KINDS = {"Effects": "effect", "Generators": "generator"}


@dataclass(frozen=True)
class PluginEntry:
    """An installed plugin, as listed in FL Studio's Plugin database."""

    name: str
    kind: str  # "effect" or "generator"
    format: str  # "Fruity", "VST", "VST3", ... (empty when not known)
    path: Path


def get_plugin_database_dir() -> Path:
    """Get FL Studio's Plugin database directory."""
    return (
        Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Presets" / "Plugin database"
    )


def _display_name(stem: str) -> str:
    # The Plugin Manager suffixes 64-bit builds, e.g. "Fruity Reeverb 2_x64"
    return re.sub(r"[ _]?\(?x64\)?$", "", stem, flags=re.IGNORECASE).strip()


def list_plugins(database_dir: Path | None = None) -> list[PluginEntry]:
    """List every plugin in the Plugin database, deduplicated by kind and name."""
    root = database_dir or get_plugin_database_dir()
    entries: dict[tuple[str, str], PluginEntry] = {}

    for folder, kind in KINDS.items():
        # "Installed" lists every scanned plugin by format; the top-level
        # folders are FL's curated categories and mostly repeat them.
        for base, installed in ((root / "Installed" / folder, True), (root / folder, False)):
            if not base.is_dir():
                continue
            for fst in sorted(base.rglob("*.fst")):
                name = _display_name(fst.stem)
                parts = fst.relative_to(base).parts
                plugin_format = parts[0] if installed and len(parts) > 1 else ""
                entry = PluginEntry(name, kind, plugin_format, fst)
                entries.setdefault((kind, name.lower()), entry)

    return sorted(entries.values(), key=lambda e: (e.kind, e.name.lower()))


def find_plugins(
    query: str = "",
    kind: str | None = None,
    database_dir: Path | None = None,
) -> list[PluginEntry]:
    """Find plugins whose name contains every word of the query.

    Exact name matches come first, then names starting with the query.
    """
    words = query.lower().split()
    matches = [
        entry
        for entry in list_plugins(database_dir)
        if (kind is None or entry.kind == kind)
        and all(word in entry.name.lower() for word in words)
    ]
    wanted = query.lower().strip()
    return sorted(
        matches,
        key=lambda e: (e.name.lower() != wanted, not e.name.lower().startswith(wanted)),
    )
