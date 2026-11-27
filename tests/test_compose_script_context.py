"""ComposeWithLLM.pyscript loaded with a fake flpianoroll (no FL Studio needed)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ComposeWithLLM.pyscript"


class BrokenScore:
    """A score whose context fields are missing, like an older FL version."""

    noteCount = 0

    def __getattr__(self, name):
        raise AttributeError(f"score has no attribute {name!r}")


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "flpianoroll", types.SimpleNamespace(score=BrokenScore()))
    loader = importlib.machinery.SourceFileLoader("compose_with_llm", str(SCRIPT))
    spec = importlib.util.spec_from_loader("compose_with_llm", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setattr(module, "REQUEST_FILE", str(tmp_path / "mcp_request.json"))
    return module


def test_failed_context_still_clears_the_request_queue(script):
    Path(script.REQUEST_FILE).write_text(json.dumps([{"action": "get_context"}]))

    summary = script.process_mcp_request()

    assert summary["status"] == "error"
    assert "PPQ" in summary["message"]
    assert "context" not in summary
    assert json.loads(Path(script.REQUEST_FILE).read_text()) == []
