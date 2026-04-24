from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from voltagrid_tx3.agent_loop import run
from voltagrid_tx3.prompts import system_message
from voltagrid_tx3.simulator import PlantSimulator, reset_simulator
from voltagrid_tx3.ui.view_model import build_dashboard_state


def test_dashboard_state_matches_message_bus() -> None:
    sim = PlantSimulator()
    sim.step("irm_shortfall")

    view = build_dashboard_state(sim)

    assert view["reserve"]["irm_shortfall"] is True
    assert view["bus_topics"]["vg/tx3/control/reserve"]["irm_shortfall"] is True
    assert view["events"][-1]["kind"] == "irm_shortfall"


def test_agent_loop_calls_tool_then_returns_final_text() -> None:
    reset_simulator()

    completion = _CompletionStub()
    turn = run("what is the reserve margin?", history=[system_message()], completion=completion)

    assert turn.final_text == "Reserve margin checked."
    assert [trace.name for trace in turn.traces] == ["get_reserve_margin"]


class _CompletionStub:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **kwargs: Any):
        self.calls += 1
        if self.calls == 1:
            return _Response(
                _Message(
                    content="",
                    tool_calls=[
                        _ToolCall(
                            id="call-1",
                            function=_Function(
                                name="get_reserve_margin",
                                arguments="{}",
                            ),
                        )
                    ],
                )
            )
        return _Response(_Message(content="Reserve margin checked."))


@dataclass
class _Function:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Function


@dataclass
class _Message:
    content: str
    tool_calls: list[_ToolCall] | None = None


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Response:
    def __init__(self, message: _Message) -> None:
        self.choices = [_Choice(message)]
