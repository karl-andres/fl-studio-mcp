"""Discover and edit host-exposed parameters on loaded FL Studio plugins."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from uuid import uuid4

from fl_studio_mcp.utils.connection import get_connection

VALUE_TOLERANCE = 1e-5


def normalized_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def target_location(target: str) -> dict:
    channel = re.fullmatch(r"channel:(0|[1-9][0-9]*)", target)
    if channel:
        return {"index": int(channel[1]), "slot": -1}
    effect = re.fullmatch(r"mixer:(0|[1-9][0-9]*):([0-9])", target)
    if effect:
        return {"index": int(effect[1]), "slot": int(effect[2])}
    raise ValueError("Use channel:<global index> or mixer:<track>:<slot 0..9>")


def fingerprint(target: str, metadata: dict) -> str:
    return hashlib.sha256(json.dumps([target, metadata], sort_keys=True).encode()).hexdigest()


def normalized_value(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1


def values_match(observed, expected) -> bool:
    return normalized_value(observed) and math.isclose(observed, expected, abs_tol=VALUE_TOLERANCE)


class PluginEditor:
    def __init__(self, connection=None):
        self.connection = connection if connection is not None else get_connection()

    def request(self, action: str, **params) -> dict:
        request_id = uuid4().hex
        response = self.connection.send_command(
            "plugins.editor" + action, {**params, "request_id": request_id}
        )
        error = response.get("error")
        if response.get("editor_request_id") != request_id:
            if isinstance(error, str) and error.startswith("Unknown action:"):
                raise RuntimeError("Update and reload the FL Studio MCP controller script")
            raise RuntimeError(error or "Controller response could not be matched to the request")
        if error and action != "Write":
            raise RuntimeError(error)
        return response

    def instances(self, query: str = "") -> dict:
        instances = []
        start = 0
        while start is not None:
            page = self.request("Instances", start=start)
            instances.extend(page["instances"])
            start = page["next_start"]
        query = normalized_name(query)
        matches = [p for p in instances if query in normalized_name(p["plugin_name"])]
        return {"success": True, "instances": matches, "count": len(matches)}

    def names(self, location: dict, metadata: dict) -> list[str]:
        names = []
        start = 0
        while start is not None:
            page = self.request("Read", **location, start=start, expected_metadata=metadata)
            names.extend(page["names"])
            start = page["next_start"]
        return names

    def describe(
        self, target: str, query: str, start: int, limit: int, named_only: bool, include_text: bool
    ) -> dict:
        if start < 0 or not 1 <= limit <= 128:
            raise ValueError("start must be nonnegative and limit must be 1..128")
        location = target_location(target)
        metadata = self.request("Read", **location, indices=[])["metadata"]
        names = self.names(location, metadata)
        query = normalized_name(query)
        matches = [
            i
            for i, name in enumerate(names)
            if (name or not named_only) and query in normalized_name(name)
        ]
        indices = matches[start : start + limit]
        page = self.request(
            "Read",
            **location,
            indices=indices,
            expected_metadata=metadata,
            include_text=include_text,
        )
        return {
            "success": True,
            "target": target,
            **metadata,
            "fingerprint": fingerprint(target, metadata),
            "named_parameter_count": sum(bool(name) for name in names),
            "matching_parameters": len(matches),
            "parameters": page["parameters"],
            "next_start": start + len(indices) if start + len(indices) < len(matches) else None,
        }

    def edit(
        self, target: str, edits: list[dict], expected_fingerprint: str | None, dry_run: bool
    ) -> dict:
        if not 1 <= len(edits) <= 64:
            raise ValueError("Expected 1..64 edits")
        location = target_location(target)
        metadata = self.request("Read", **location, indices=[])["metadata"]
        observed_fingerprint = fingerprint(target, metadata)
        if expected_fingerprint is not None and expected_fingerprint != observed_fingerprint:
            raise ValueError("Plugin metadata changed; describe the target again")

        names = None
        by_index = {}
        for edit in edits:
            parameter, value = edit.get("parameter"), edit.get("value")
            if not normalized_value(value):
                raise ValueError("Each edit needs a normalized value in 0..1")
            if "expected_value" in edit and not normalized_value(edit["expected_value"]):
                raise ValueError("expected_value must be normalized in 0..1")
            if "expected_name" in edit and not isinstance(edit["expected_name"], str):
                raise ValueError("expected_name must be a string")
            if isinstance(parameter, str):
                if names is None:
                    names = self.names(location, metadata)
                name = normalized_name(parameter)
                candidates = [
                    i for i, label in enumerate(names) if label and normalized_name(label) == name
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        f"Parameter {parameter!r} must have a unique match. "
                        f"Matching indices: {candidates[:20]}. Use an explicit index."
                    )
                parameter = candidates[0]
            if (
                type(parameter) is not int
                or not 0 <= parameter < metadata["parameter_count"]
                or parameter in by_index
            ):
                raise ValueError("Parameter index is invalid or duplicated")
            by_index[parameter] = edit

        read_args = {**location, "indices": list(by_index), "expected_metadata": metadata}
        before = self.request("Read", **read_args)["parameters"]
        plan = []
        for parameter in before:
            index, name, value = parameter["index"], parameter["name"], parameter["value"]
            edit = by_index[index]
            if not name or not normalized_value(value):
                raise ValueError(f"Parameter {index} has no name or a usable normalized value")
            expected_name = edit.get("expected_name", name)
            selector = edit["parameter"]
            if normalized_name(name) != normalized_name(expected_name) or (
                isinstance(selector, str) and normalized_name(name) != normalized_name(selector)
            ):
                raise ValueError(f"Name of parameter {index} changed")
            if not values_match(value, edit.get("expected_value", value)):
                raise ValueError(f"Current value of parameter {index} changed")
            plan.append({"index": index, "name": name, "before": value, "value": edit["value"]})
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "plan": plan,
                "fingerprint": observed_fingerprint,
            }

        try:
            write = self.request("Write", **location, edits=plan, expected_metadata=metadata)
        except RuntimeError as exc:
            return {"success": False, "error": str(exc), "write_outcome_unknown": True}
        submitted = write.get("submitted", [])
        if write.get("error") and not submitted:
            return {"success": False, "error": write["error"], "submitted": submitted}

        # Poll only getters and report the actual result even for a partially applied edit.
        for attempt in range(4):
            if attempt:
                time.sleep(0.05)
            try:
                after = self.request("Read", **read_args)["parameters"]
            except RuntimeError as exc:
                return {"success": False, "error": str(exc), "submitted": submitted}
            results = [
                {
                    **item,
                    "observed": current["value"],
                    "verified": item["name"] == current["name"]
                    and values_match(current["value"], item["value"]),
                }
                for item, current in zip(plan, after)
            ]
            if all(item["verified"] for item in results) or write.get("error"):
                break
        success = all(item["verified"] for item in results) and not write.get("error")
        result = {"success": success, "parameters": results, "submitted": submitted}
        if not success:
            result["error"] = write.get("error") or "One or more values did not match on readback"
        return result


def editor_result(function, *args) -> dict:
    try:
        return function(*args)
    except (RuntimeError, ValueError) as exc:
        return {"success": False, "error": str(exc)}


def register_plugin_editor_tools(mcp) -> None:
    @mcp.tool()
    def fl_list_plugin_instances(query: str = "") -> dict:
        """Find loaded Channel Rack instruments and Mixer effects, optionally by plugin name."""
        return editor_result(PluginEditor().instances, query)

    @mcp.tool()
    def fl_describe_plugin(
        target: str,
        query: str = "",
        start: int = 0,
        limit: int = 64,
        named_only: bool = True,
        include_text: bool = False,
    ) -> dict:
        """Search parameter names and read values for channel:N or mixer:N:slot."""
        return editor_result(
            PluginEditor().describe, target, query, start, limit, named_only, include_text
        )

    @mcp.tool()
    def fl_edit_plugin(
        target: str,
        edits: list[dict],
        expected_fingerprint: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Edit by exact parameter name or index, then verify each value on readback.

        Each edit takes parameter and normalized value (0..1), with optional expected_name
        and expected_value guards. Use dry_run to preview and fl_describe_plugin for metadata.
        """
        return editor_result(PluginEditor().edit, target, edits, expected_fingerprint, dry_run)
