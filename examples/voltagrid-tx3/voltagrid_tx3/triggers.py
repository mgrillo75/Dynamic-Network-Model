from __future__ import annotations

from typing import Any

from voltagrid_tx3.prompts import action_message
from voltagrid_tx3.simulator import get_simulator

EVENT_CATALOG = {
    "irm_shortfall",
    "minimum_load_conflict",
    "party_mode_enabled",
    "breaker_failure_fast_disconnect",
    "blackout_detected",
    "blackout_recovery_paused",
    "black_start_ready",
    "black_start_paused",
    "sync_con_unavailable",
    "controller_failover",
}


def latest_action_message() -> dict[str, str] | dict[str, Any]:
    events = [event for event in get_simulator().state.event_log if event.kind in EVENT_CATALOG]
    if not events:
        return {"error": "no dispatchable simulator events"}
    event = events[-1]
    return action_message(event.kind, **event.to_dict())


def action_message_for_event(event_id: str) -> dict[str, str] | dict[str, Any]:
    for event in get_simulator().state.event_log:
        if event.event_id == event_id:
            if event.kind not in EVENT_CATALOG:
                return {"error": f"event kind '{event.kind}' is not dispatchable"}
            return action_message(event.kind, **event.to_dict())
    return {"error": f"unknown event '{event_id}'"}
