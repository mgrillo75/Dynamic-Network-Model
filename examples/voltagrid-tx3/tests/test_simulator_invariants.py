from __future__ import annotations

from voltagrid_tx3.models import ControlMode, RunState
from voltagrid_tx3.simulator import PlantSimulator


def test_initial_state_satisfies_irm() -> None:
    sim = PlantSimulator()

    assert sim.state.reserve.irm_shortfall is False
    assert sim.state.reserve.online_generators == 8
    assert sim.state.reserve.required_generators == 8
    assert sim.state.telemetry.bus_voltage_pu == 1.0


def test_control_action_requires_confirmation_before_state_mutates() -> None:
    sim = PlantSimulator()

    proposed = sim.propose_action("start_genset", target_asset_id="G09", requested_by="test")

    assert proposed["valid"] is True
    assert sim.state.assets["G09"].run_state == RunState.STOPPED

    applied = sim.confirm_action(proposed["action_id"], confirmed_by="operator")

    assert applied["status"] == "applied"
    assert sim.state.assets["G09"].run_state == RunState.RUNNING
    assert applied["result_delta"]["operation"] == "start_genset"


def test_blocked_genset_rejects_remote_start() -> None:
    sim = PlantSimulator()
    mode = sim.propose_action(
        "set_mode",
        target_asset_id="G09",
        value={"control_mode": "block"},
        requested_by="test",
    )
    sim.confirm_action(mode["action_id"])

    proposed = sim.propose_action("start_genset", target_asset_id="G09", requested_by="test")

    assert proposed["valid"] is False
    assert sim.state.assets["G09"].control_mode == ControlMode.BLOCK
    assert "blocked" in proposed["validation_message"]


def test_irm_prevents_generator_stop() -> None:
    sim = PlantSimulator()

    proposed = sim.propose_action("stop_genset", target_asset_id="G01", requested_by="test")

    assert proposed["valid"] is False
    assert "IRM" in proposed["validation_message"]
    assert sim.state.assets["G01"].run_state == RunState.RUNNING


def test_party_mode_starts_all_auto_remote_gensets() -> None:
    sim = PlantSimulator()

    proposed = sim.propose_action("enable_party_mode", requested_by="test")
    sim.confirm_action(proposed["action_id"], confirmed_by="operator")

    assert sim.state.settings.party_mode is True
    assert sim.state.reserve.online_generators == 12
    assert any(e.kind == "party_mode_enabled" for e in sim.state.event_log)


def test_fast_disconnect_trips_target_and_emits_alarm() -> None:
    sim = PlantSimulator()

    proposed = sim.propose_action("simulate_breaker_failure", target_asset_id="G01")
    applied = sim.confirm_action(proposed["action_id"], confirmed_by="operator")

    assert sim.state.assets["G01"].run_state == RunState.TRIPPED
    assert applied["alarms_emitted"]
    assert any(e.kind == "breaker_failure_fast_disconnect" for e in sim.state.event_log)


def test_controller_failover_does_not_blackout_plant() -> None:
    sim = PlantSimulator()

    sim.step("controller_failover")

    assert sim.state.network_health.active_master == "MC-B"
    assert sim.state.network_health.controller_failover is True
    assert sim.state.telemetry.bus_voltage_pu == 1.0
    assert sim.state.telemetry.bus_frequency_hz == 60.0
