from __future__ import annotations

import json
from pathlib import Path

from voltagrid_tx3 import tools
from voltagrid_tx3.prompts import action_message, playbook_keys, profile_metadata
from voltagrid_tx3.simulator import reset_simulator


def test_tool_loop_propose_confirm_records_state_change() -> None:
    reset_simulator()

    proposed = tools.propose_control_action("start_genset", target_asset_id="G09")
    assert proposed["valid"] is True

    assert tools.get_asset_state("G09")["run_state"] == "stopped"

    applied = tools.confirm_control_action(proposed["action_id"], confirmed_by="operator")

    assert applied["status"] == "applied"
    assert tools.get_asset_state("G09")["run_state"] == "running"
    assert applied["result_delta"]["reserve"]["online_generators"] == 9


def test_scenario_fixtures_emit_expected_events() -> None:
    fixture_dir = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"
    for path in sorted(fixture_dir.glob("*.json")):
        reset_simulator()
        spec = json.loads(path.read_text())
        tools.step_simulation(spec["scenario"])
        if spec["expected_event"] is None:
            continue
        events = tools.get_event_log(limit=20)["events"]
        assert any(e["kind"] == spec["expected_event"] for e in events), path.name


def test_profile_declares_supported_event_kinds_and_playbooks() -> None:
    metadata = profile_metadata()
    keys = set(playbook_keys())

    assert metadata["site_profile"] == "voltagrid_tx3_core"
    assert set(metadata["supported_event_kinds"]).issubset(keys)


def test_action_message_renders_event_context() -> None:
    msg = action_message(
        "irm_shortfall",
        source="master_controller",
        tick=7,
        affected_assets=["G01"],
        context={"required_generators": 10},
    )

    assert msg["role"] == "user"
    assert "tick" in msg["content"]
    assert "G01" in msg["content"]


def test_unknown_tool_reports_error() -> None:
    assert "error" in tools.call("does_not_exist")


def test_invalid_tool_arguments_are_reported() -> None:
    result = tools.call("get_asset_state")
    assert "bad arguments" in result["error"]
