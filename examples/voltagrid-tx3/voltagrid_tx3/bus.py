from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from voltagrid_tx3.models import PlantState

TOPICS = {
    "site": "vg/tx3/site/summary",
    "telemetry": "vg/tx3/telemetry/main_bus",
    "reserve": "vg/tx3/control/reserve",
    "alarms": "vg/tx3/alarms/active",
    "sequences": "vg/tx3/control/sequences",
    "commands": "vg/tx3/operator/commands",
    "events": "vg/tx3/events/recent",
    "network": "vg/tx3/network/health",
}


@dataclass
class MessageBus:
    """Small in-process topic store used by the simulator, tools, and UI."""

    topics: dict[str, Any] = field(default_factory=dict)

    def publish(self, topic: str, payload: Any) -> None:
        self.topics[topic] = payload

    def read(self, topic: str) -> Any:
        return self.topics.get(topic)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.topics)

    def publish_state(self, state: PlantState) -> None:
        self.publish(
            TOPICS["site"],
            {"site_id": state.site_id, "site_name": state.site_name, "tick": state.tick},
        )
        self.publish(TOPICS["telemetry"], state.telemetry.to_dict())
        self.publish(TOPICS["reserve"], state.reserve.to_dict())
        self.publish(TOPICS["alarms"], [a.to_dict() for a in state.alarms if a.active])
        self.publish(TOPICS["sequences"], {k: v.to_dict() for k, v in state.sequences.items()})
        self.publish(TOPICS["events"], [e.to_dict() for e in state.event_log[-20:]])
        self.publish(TOPICS["network"], state.network_health.to_dict())
