"""Regression tests for FL Studio Documents path detection."""
import sys
import types
from pathlib import Path

import pytest

from fl_studio_mcp.utils import midi_connection


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.mark.parametrize(
    ("folder", "onedrive_script", "expected"),
    [
        ("Documents", False, "Documents"),
        ("Documents", True, "OneDrive/Documents"),
        ("CustomDocs", False, "CustomDocs"),
    ],
)
def test_windows_documents_resolution(tmp_path, monkeypatch, folder, onedrive_script, expected):
    monkeypatch.setattr(midi_connection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        sys.modules,
        "winreg",
        types.SimpleNamespace(
            HKEY_CURRENT_USER=object(),
            OpenKey=lambda *_: FakeKey(),
            QueryValueEx=lambda *_: (str(tmp_path / folder), 1),
        ),
    )
    if onedrive_script:
        script = (
            tmp_path / "OneDrive" / "Documents" / "Image-Line" / "FL Studio"
            / "Settings" / "Hardware" / "FLStudioMCP" / "device_FLStudioMCP.py"
        )
        script.parent.mkdir(parents=True)
        script.touch()
    expected_dir = (
        tmp_path / expected / "Image-Line" / "FL Studio"
        / "Settings" / "Hardware" / "FLStudioMCP"
    )
    assert midi_connection._get_fl_hardware_dir() == expected_dir


def test_registry_unavailable_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(midi_connection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    def fail(*_):
        raise OSError("registry unavailable")
    monkeypatch.setitem(
        sys.modules, "winreg",
        types.SimpleNamespace(HKEY_CURRENT_USER=object(), OpenKey=fail),
    )
    assert midi_connection._get_fl_hardware_dir() == (
        tmp_path / "Documents" / "Image-Line" / "FL Studio"
        / "Settings" / "Hardware" / "FLStudioMCP"
    )


def test_macos_documents_path_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(midi_connection.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert midi_connection._get_fl_hardware_dir() == (
        tmp_path / "Documents" / "Image-Line" / "FL Studio"
        / "Settings" / "Hardware" / "FLStudioMCP"
    )
