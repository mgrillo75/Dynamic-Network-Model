from __future__ import annotations

from typing import Any

from voltagrid_tx3.models import AssetKind
from voltagrid_tx3.simulator import get_simulator


def get_site_summary() -> dict[str, Any]:
    sim = get_simulator()
    state = sim.state
    assets = state.assets.values()
    return {
        "site_id": state.site_id,
        "site_name": state.site_name,
        "tick": state.tick,
        "telemetry": state.telemetry.to_dict(),
        "reserve": state.reserve.to_dict(),
        "active_alarms": [a.to_dict() for a in state.alarms if a.active],
        "asset_counts": {
            kind.value: sum(1 for a in assets if a.kind == kind)
            for kind in AssetKind
        },
        "network_health": state.network_health.to_dict(),
    }


def get_asset_state(asset_id: str) -> dict[str, Any]:
    return get_simulator().get_asset(asset_id)


def get_mv_topology() -> dict[str, Any]:
    return get_simulator().get_topology()


def get_alarm_state(active_only: bool = True) -> dict[str, Any]:
    alarms = get_simulator().state.alarms
    if active_only:
        alarms = [a for a in alarms if a.active]
    return {"count": len(alarms), "alarms": [a.to_dict() for a in alarms]}


def get_control_modes() -> dict[str, Any]:
    state = get_simulator().state
    return {
        "settings": state.settings.to_dict(),
        "asset_modes": {
            asset.asset_id: {
                "kind": asset.kind,
                "control_mode": asset.control_mode,
                "local_remote": asset.local_remote,
                "run_state": asset.run_state,
                "breaker_state": asset.breaker_state,
            }
            for asset in state.assets.values()
            if asset.kind in {AssetKind.GENSET, AssetKind.SYNC_CONDENSER, AssetKind.MV_FEEDER}
        },
    }


def get_reserve_margin() -> dict[str, Any]:
    return get_simulator().state.reserve.to_dict()


def get_sequence_status() -> dict[str, Any]:
    return {
        name: seq.to_dict()
        for name, seq in get_simulator().state.sequences.items()
    }


def get_event_log(kind: str | None = None, limit: int = 20) -> dict[str, Any]:
    events = get_simulator().state.event_log
    if kind:
        events = [e for e in events if e.kind == kind]
    events = events[-limit:]
    return {"count": len(events), "events": [e.to_dict() for e in events]}


def propose_control_action(
    operation: str,
    target_asset_id: str | None = None,
    value: Any = None,
    reason: str = "",
    requested_by: str = "hermes",
) -> dict[str, Any]:
    return get_simulator().propose_action(
        operation=operation,
        target_asset_id=target_asset_id,
        value=value,
        requested_by=requested_by,
        reason=reason,
    )


def confirm_control_action(action_id: str, confirmed_by: str = "operator") -> dict[str, Any]:
    return get_simulator().confirm_action(action_id, confirmed_by=confirmed_by)


def step_simulation(scenario: str | None = None) -> dict[str, Any]:
    return get_simulator().step(scenario=scenario)


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_site_summary",
            "description": (
                "Get TX-3 site status, bus telemetry, reserve status, alarms, "
                "and network health."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_asset_state",
            "description": (
                "Get one asset state by asset_id, such as G01, SC01, FDR-A, "
                "EDG-01, MC-A."
            ),
            "parameters": {
                "type": "object",
                "properties": {"asset_id": {"type": "string"}},
                "required": ["asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mv_topology",
            "description": (
                "Get the simulated 34.5 kV bus topology, gensets, sync "
                "condensers, feeders, LV black-start source, and controllers."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alarm_state",
            "description": "Get active or historical simulator alarms.",
            "parameters": {
                "type": "object",
                "properties": {"active_only": {"type": "boolean"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_control_modes",
            "description": (
                "Get operator-selected modes, local/remote states, and "
                "run/breaker states."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reserve_margin",
            "description": (
                "Get IRM, online generator count, minimum-load conflict, and "
                "stop/start candidates."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sequence_status",
            "description": "Get blackout recovery and black-start sequence state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_log",
            "description": "Get recent simulator events, optionally filtered by kind.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_control_action",
            "description": (
                "Validate and stage a sandbox control action. This never mutates "
                "plant state until confirm_control_action is called."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "target_asset_id": {"type": "string"},
                    "value": {},
                    "reason": {"type": "string"},
                    "requested_by": {"type": "string"},
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_control_action",
            "description": (
                "Apply a previously proposed valid sandbox control action after "
                "operator confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                    "confirmed_by": {"type": "string"},
                },
                "required": ["action_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "step_simulation",
            "description": (
                "Advance the deterministic simulator one tick, optionally "
                "injecting a scenario event."
            ),
            "parameters": {
                "type": "object",
                "properties": {"scenario": {"type": "string"}},
            },
        },
    },
]


REGISTRY = {
    "get_site_summary": get_site_summary,
    "get_asset_state": get_asset_state,
    "get_mv_topology": get_mv_topology,
    "get_alarm_state": get_alarm_state,
    "get_control_modes": get_control_modes,
    "get_reserve_margin": get_reserve_margin,
    "get_sequence_status": get_sequence_status,
    "get_event_log": get_event_log,
    "propose_control_action": propose_control_action,
    "confirm_control_action": confirm_control_action,
    "step_simulation": step_simulation,
}


def call(name: str, **kwargs: Any) -> dict[str, Any]:
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**kwargs)
    except TypeError as e:
        return {"error": f"bad arguments to {name}: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{name} failed: {e}"}
