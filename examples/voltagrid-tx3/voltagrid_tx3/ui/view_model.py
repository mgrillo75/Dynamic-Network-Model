from __future__ import annotations

from typing import Any

from voltagrid_tx3.models import AssetKind
from voltagrid_tx3.simulator import PlantSimulator


def build_dashboard_state(sim: PlantSimulator) -> dict[str, Any]:
    state = sim.state
    assets = state.assets.values()
    return {
        "site": {
            "site_id": state.site_id,
            "site_name": state.site_name,
            "tick": state.tick,
        },
        "telemetry": state.telemetry.to_dict(),
        "reserve": state.reserve.to_dict(),
        "network_health": state.network_health.to_dict(),
        "gensets": [
            a.to_dict() for a in assets if a.kind == AssetKind.GENSET
        ],
        "sync_cons": [
            a.to_dict() for a in assets if a.kind == AssetKind.SYNC_CONDENSER
        ],
        "feeders": [
            a.to_dict() for a in assets if a.kind == AssetKind.MV_FEEDER
        ],
        "alarms": [a.to_dict() for a in state.alarms if a.active],
        "sequences": {name: seq.to_dict() for name, seq in state.sequences.items()},
        "events": [e.to_dict() for e in state.event_log[-10:]],
        "pending_actions": [a.to_dict() for a in state.pending_actions.values()],
        "applied_actions": [a.to_dict() for a in state.applied_actions[-10:]],
        "bus_topics": sim.bus.snapshot(),
    }
