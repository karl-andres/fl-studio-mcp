import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from fl_studio_mcp.tools.plugin_editor import PluginEditor


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    host = SimpleNamespace(
        names=["Drive", "Mix"] + [""] * 128 + ["Wide"],
        values=[0.25, 0.5] + [0.0] * 128 + [0.2],
        writes=[],
        reject=None,
        coupled=False,
        editable=True,
        sent=[],
        second_effect=None,
    )

    def values_at(index, slot):
        return host.second_effect if (index, slot) == (12, 9) else host.values

    def is_valid(index, slot, use_global):
        return use_global and (
            (index, slot) in {(1, -1), (13, 9)}
            or (index, slot) == (12, 9) and host.second_effect is not None
        )

    def set_value(value, parameter, index, slot, pickup, global_index):
        assert is_valid(index, slot, global_index)
        assert pickup == 0 and global_index is True
        values = values_at(index, slot)
        host.writes.append(parameter)
        if parameter != host.reject:
            values[parameter] = value
        if host.coupled and parameter == 1:
            values[0] = 0.25

    modules = {
        "channels": {"channelCount": lambda use_global: 2},
        "mixer": {"trackCount": lambda: 14},
        "midi": {"PIM_None": 0},
        "transport": {},
        "general": {"safeToEdit": lambda: host.editable},
        "plugins": {
            "isValid": is_valid,
            "getPluginName": lambda i, s, user, glob: "Instrument" if s == -1 else "Effect",
            "getParamCount": lambda *args: len(host.names),
            "getParamName": lambda i, *args: host.names[i],
            "getParamValue": lambda i, index, slot, glob: values_at(index, slot)[i],
            "getParamValueString": lambda i, index, slot, glob: f"{values_at(index, slot)[i]:.0%}",
            "setParamValue": set_value,
        },
    }
    for name, functions in modules.items():
        module = ModuleType(name)
        vars(module).update(functions)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "fl_controller/device_FLStudioMCP.py"
    spec = importlib.util.spec_from_file_location("fake_controller", path)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    controller.COMMAND_FILE = tmp_path / "command.json"
    controller.RESPONSE_FILE = tmp_path / "response.json"

    def send_command(action, params):
        host.sent.append(action)
        controller.COMMAND_FILE.write_text(json.dumps({"action": action, "params": params}))
        controller.OnMidiMsg(SimpleNamespace(midiId=0x90, data1=127, data2=127, handled=False))
        return json.loads(controller.RESPONSE_FILE.read_text())

    host.send_command = send_command
    return host, PluginEditor(host)


def test_finds_instruments_and_effects_across_pages(bridge):
    _, editor = bridge
    result = editor.instances()
    assert [p["target"] for p in result["instances"]] == ["channel:1", "mixer:13:9"]
    assert editor.instances("effect")["count"] == 1


def test_search_finds_named_parameter_beyond_first_page_and_reads_display(bridge):
    _, editor = bridge
    result = editor.describe("channel:1", "wide", 0, 1, True, True)
    assert result["named_parameter_count"] == 3 and result["next_start"] is None
    assert result["parameters"] == [
        {"index": 130, "name": "Wide", "value": 0.2, "value_text": "20%"}
    ]


def test_only_edits_the_requested_instance_of_identical_effects(bridge):
    host, editor = bridge
    host.second_effect = host.values.copy()
    first, second = editor.instances("effect")["instances"]
    assert first["plugin_name"] == second["plugin_name"]

    result = editor.edit(first["target"], [{"parameter": "Drive", "value": 0.4}], None, False)

    assert result["success"]
    assert editor.describe(first["target"], "Drive", 0, 1, True, False)["parameters"][0][
        "value"
    ] == 0.4
    assert editor.describe(second["target"], "Drive", 0, 1, True, False)["parameters"][0][
        "value"
    ] == 0.25


@pytest.mark.parametrize("target", ["channel:1", "mixer:13:9"])
def test_dry_run_and_normalized_name_or_index_edit_with_new_readback(bridge, target):
    host, editor = bridge
    edits = [
        {"parameter": "  DRIVE ", "value": 0.4},
        {"parameter": 1, "value": 0.7, "expected_name": "Mix", "expected_value": 0.5},
    ]
    preview = editor.edit(target, edits, None, True)
    assert preview["dry_run"] and not host.writes
    result = editor.edit(target, edits, preview["fingerprint"], False)
    assert result["success"] and result["submitted"] == [0, 1]
    assert [p["observed"] for p in result["parameters"]] == [0.4, 0.7]
    assert host.sent[-2:] == ["plugins.editorWrite", "plugins.editorRead"]


@pytest.mark.parametrize("failure", ["duplicate", "changed_value", "unnamed", "fingerprint"])
def test_validation_refuses_before_any_setter(bridge, failure):
    host, editor = bridge
    edits = [{"parameter": "Drive", "value": 0.4}, {"parameter": 1, "value": 0.7}]
    fingerprint = None
    if failure == "duplicate":
        host.names[1] = "DRIVE"
    elif failure == "changed_value":
        edits[1]["expected_value"] = 0.6
    elif failure == "unnamed":
        edits[1]["parameter"] = 2
    else:
        fingerprint = "expired"
    with pytest.raises(ValueError):
        editor.edit("channel:1", edits, fingerprint, False)
    assert not host.writes


def test_unsafe_host_state_is_rejected_by_controller(bridge):
    host, editor = bridge
    host.editable = False
    result = editor.edit("channel:1", [{"parameter": 0, "value": 0.4}], None, False)
    assert not result["success"] and not host.writes


@pytest.mark.parametrize("coupled", [True, False])
def test_returns_mismatched_values_without_replaying_writes(bridge, coupled):
    host, editor = bridge
    host.coupled = coupled
    host.reject = None if coupled else 1
    result = editor.edit(
        "channel:1", [{"parameter": 0, "value": 0.4}, {"parameter": 1, "value": 0.7}], None, False
    )
    assert not result["success"] and host.writes == [0, 1]
    assert [item["verified"] for item in result["parameters"]] == [not coupled, coupled]


def test_missing_write_acknowledgement_is_unknown_and_is_not_retried(bridge, monkeypatch):
    host, editor = bridge
    send = host.send_command

    def drop_ack(action, params):
        response = send(action, params)
        if action == "plugins.editorWrite":
            response.pop("editor_request_id")
        return response

    monkeypatch.setattr(host, "send_command", drop_ack)
    result = editor.edit("channel:1", [{"parameter": 0, "value": 0.4}], None, False)
    assert result["write_outcome_unknown"] and host.writes == [0]
