"""Tool-call policy for GameForge.

Two actions reach outside what Hermes already gates — a caller-named Python file run inside
Blender, and a public upload to itch.io. Both are escalated to the human approval gate through
the ``pre_tool_call`` hook, so a model cannot make either happen on its own.
"""

from __future__ import annotations


def pre_tool_call(tool_name: str = "", args: dict | None = None, **_kwargs):
    """Return an ``approve`` directive for the actions that leave the sandbox, else ``None``."""
    a = args or {}
    if tool_name == "forge_engine" and a.get("engine") == "blender" and a.get("action") == "script":
        script = a.get("script") or "the named file"
        return {"action": "approve",
                "message": f"Run {script} inside Blender? It is arbitrary Python on this machine.",
                "rule_key": "gameforge:blender-script"}
    if tool_name == "forge_export" and a.get("target") == "itch":
        target = a.get("itch_target") or "no target given"
        return {"action": "approve",
                "message": f"Publish this build publicly to itch.io ({target})?",
                "rule_key": "gameforge:itch-publish"}
    return None
