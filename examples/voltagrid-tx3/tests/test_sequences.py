from __future__ import annotations

from voltagrid_tx3.models import SequenceStatus
from voltagrid_tx3.simulator import PlantSimulator


def _confirm(sim: PlantSimulator, operation: str):
    action = sim.propose_action(operation, requested_by="test")
    return sim.confirm_action(action["action_id"], confirmed_by="operator")


def test_blackout_recovery_reaches_complete_after_operator_continues() -> None:
    sim = PlantSimulator()

    sim.step("blackout")
    seq = sim.state.sequences["blackout_recovery"]
    assert seq.status == SequenceStatus.IN_PROGRESS
    assert any(e.kind == "blackout_detected" for e in sim.state.event_log)

    _confirm(sim, "continue_sequence")
    _confirm(sim, "continue_sequence")

    seq = sim.state.sequences["blackout_recovery"]
    assert seq.status == SequenceStatus.COMPLETE
    assert sim.state.assets["EDG-01"].online is True


def test_black_start_waits_for_blackout_recovery_completion() -> None:
    sim = PlantSimulator()
    sim.step("blackout")

    action = sim.propose_action("initiate_black_start", requested_by="test")
    result = sim.confirm_action(action["action_id"], confirmed_by="operator")

    assert result["status"] == "applied"
    assert sim.state.sequences["black_start"].status == SequenceStatus.PAUSED
    assert "not complete" in (sim.state.sequences["black_start"].paused_reason or "")


def test_black_start_sequence_completes_after_recovery() -> None:
    sim = PlantSimulator()
    sim.step("blackout")
    _confirm(sim, "continue_sequence")
    _confirm(sim, "continue_sequence")

    start = sim.propose_action("initiate_black_start", requested_by="test")
    sim.confirm_action(start["action_id"], confirmed_by="operator")
    _confirm(sim, "continue_sequence")
    _confirm(sim, "continue_sequence")
    _confirm(sim, "continue_sequence")
    _confirm(sim, "continue_sequence")

    assert sim.state.sequences["black_start"].status == SequenceStatus.COMPLETE
    assert sim.state.assets["EDG-01"].online is False
    assert sim.state.telemetry.bus_voltage_pu == 1.0
    assert any(e.kind == "black_start_complete" for e in sim.state.event_log)
