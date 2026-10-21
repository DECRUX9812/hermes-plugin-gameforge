"""Glue between the plugin context and the handlers: config reads, tool dispatch, and the JSON
envelope every GameForge tool returns."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable

_ctx: Any = None


def bind(ctx: Any) -> None:
    global _ctx
    _ctx = ctx


def config(key: str, default: Any = None) -> Any:
    if _ctx is None:
        return default
    value = _ctx.get_config(key, default=default)
    return default if value in (None, "") else value


def dispatch(tool: str, args: dict, **kw) -> str:
    if _ctx is None:
        raise RuntimeError("GameForge is not registered with Hermes; tool dispatch is unavailable")
    return _ctx.dispatch_tool(tool, args, **kw)


def llm() -> Any:
    return None if _ctx is None else _ctx.llm


def ok(**data: Any) -> str:
    media = [p for p in data.pop("media", []) if p]
    if media:
        data["share"] = " ".join(f"MEDIA:{p}" for p in media)
    return json.dumps({"ok": True, **_jsonable(data)}, indent=1)


def fail(message: str, **data: Any) -> str:
    return json.dumps({"ok": False, "error": message, **_jsonable(data)})


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def handler(fn: Callable[[dict], str]) -> Callable[..., str]:
    """Tool handlers return JSON on every path: a bad argument becomes an error the model can act
    on, never an exception in the agent loop."""
    def wrapped(args: dict, **kwargs) -> str:
        try:
            return fn(args or {})
        except (ValueError, KeyError, FileNotFoundError, NotADirectoryError) as exc:
            return fail(str(exc))
        except Exception as exc:  # the agent loop must never see a raise from a tool
            return fail(f"{type(exc).__name__}: {exc}", trace=traceback.format_exc(limit=3))
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped
