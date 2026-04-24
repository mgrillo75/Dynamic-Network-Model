from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from voltagrid_tx3 import tools
from voltagrid_tx3.llm import get_client
from voltagrid_tx3.prompts import system_message

MAX_STEPS = 8


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class Turn:
    user: str
    final_text: str
    traces: list[ToolTrace] = field(default_factory=list)
    raw_messages: list[dict[str, Any]] = field(default_factory=list)


_FALLBACK_TOOL_RE = re.compile(r"```(?:json|tool_call)?\s*(\{.*?\})\s*```", re.DOTALL)


def _message_to_dict(msg: Any) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    out: dict[str, Any] = {"role": "assistant", "content": getattr(msg, "content", "") or ""}
    calls = getattr(msg, "tool_calls", None)
    if calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in calls
        ]
    return out


def _fallback_tool_calls_from_content(content: str) -> list[dict[str, Any]]:
    candidates = [m.group(1) for m in _FALLBACK_TOOL_RE.finditer(content or "")]
    stripped = (content or "").strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        name = obj.get("tool") or obj.get("name")
        args = obj.get("arguments") or obj.get("args") or {}
        if name in tools.REGISTRY:
            out.append(
                {
                    "id": f"fallback-{len(out)}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            )
    return out


def run(
    user_text: str,
    history: list[dict[str, Any]] | None = None,
    completion: Callable[..., Any] | None = None,
    on_trace: Callable[[ToolTrace], None] | None = None,
) -> Turn:
    completion = completion or get_client()
    history = history if history is not None else [system_message()]
    history.append({"role": "user", "content": user_text})
    traces: list[ToolTrace] = []

    for _ in range(MAX_STEPS):
        resp = completion(messages=history, tools=tools.TOOL_SPECS, tool_choice="auto")
        msg = _message_to_dict(resp.choices[0].message)
        history.append(msg)
        tool_calls = msg.get("tool_calls") or _fallback_tool_calls_from_content(
            msg.get("content", "")
        )
        if not tool_calls:
            return Turn(
                user=user_text,
                final_text=msg.get("content") or "",
                traces=traces,
                raw_messages=list(history),
            )

        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            try:
                if isinstance(fn["arguments"], str):
                    args = json.loads(fn["arguments"])
                else:
                    args = fn["arguments"] or {}
            except json.JSONDecodeError:
                args = {}
            result = tools.call(name, **args)
            trace = ToolTrace(name=name, arguments=args, result=result)
            traces.append(trace)
            if on_trace:
                on_trace(trace)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": json.dumps(result)[:8000],
                }
            )

    return Turn(
        user=user_text,
        final_text="(loop exceeded max steps without final answer)",
        traces=traces,
        raw_messages=list(history),
    )
