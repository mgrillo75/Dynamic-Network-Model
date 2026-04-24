from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AssetKind(StrEnum):
    GENSET = "genset"
    SYNC_CONDENSER = "sync_condenser"
    MV_FEEDER = "mv_feeder"
    LV_BLACK_START = "lv_black_start"
    BREAKER = "breaker"
    MASTER_CONTROLLER = "master_controller"
    FEP = "fep"
    AUX_LOAD = "aux_load"


class RunState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    TRIPPED = "tripped"
    UNAVAILABLE = "unavailable"


class BreakerState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    BLOCKED = "blocked"


class ControlMode(StrEnum):
    BLOCK = "block"
    MANUAL = "manual"
    AUTO = "auto"


class LocalRemoteMode(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


class SequenceStatus(StrEnum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETE = "complete"
    ABORTED = "aborted"


class EventSeverity(StrEnum):
    INFO = "info"
    ALERT = "alert"
    ALARM = "alarm"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    APPLIED = "applied"


@dataclass
class AssetState:
    asset_id: str
    name: str
    kind: AssetKind
    run_state: RunState = RunState.STOPPED
    breaker_state: BreakerState | None = None
    control_mode: ControlMode = ControlMode.AUTO
    local_remote: LocalRemoteMode = LocalRemoteMode.REMOTE
    rated_mw: float = 0.0
    rated_mva: float = 0.0
    mvar_capacity: float = 0.0
    load_mw: float = 0.0
    priority: int = 100
    engine_hours: float = 0.0
    online: bool = False
    available: bool = True
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class TelemetryState:
    bus_voltage_pu: float = 1.0
    bus_frequency_hz: float = 60.0
    customer_load_mw: float = 0.0
    total_generation_mw: float = 0.0
    average_genset_load_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class PlantSettings:
    irm_percent: float = 110.0
    minimum_synchronized_generators: int = 6
    minimum_genset_load_pct: float = 45.0
    secondary_black_start_generators: int = 2
    party_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class ReserveState:
    online_generators: int = 0
    required_generators: int = 0
    online_capacity_mw: float = 0.0
    required_capacity_mw: float = 0.0
    reserve_margin_pct: float = 0.0
    irm_shortfall: bool = False
    minimum_load_conflict: bool = False
    min_load_stop_candidate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class SequenceState:
    name: str
    status: SequenceStatus = SequenceStatus.IDLE
    step: int = 0
    description: str = "Idle"
    paused_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class NetworkHealth:
    master_primary_online: bool = True
    master_secondary_online: bool = True
    hmi_online: bool = True
    message_bus_online: bool = True
    active_master: str = "MC-A"
    controller_failover: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class Alarm:
    alarm_id: str
    severity: EventSeverity
    source: str
    message: str
    active: bool = True
    tick: int = 0

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class PlantEvent:
    event_id: str
    kind: str
    source: str
    severity: EventSeverity
    affected_assets: list[str]
    tick: int
    summary: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class ControlAction:
    action_id: str
    operation: str
    target_asset_id: str | None
    value: Any
    requested_by: str
    reason: str
    status: ActionStatus
    valid: bool
    validation_message: str
    requires_confirmation: bool = True
    confirmed_by: str | None = None
    result_delta: dict[str, Any] = field(default_factory=dict)
    alarms_emitted: list[str] = field(default_factory=list)
    sequence_transitions: list[str] = field(default_factory=list)
    tick: int = 0

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


@dataclass
class PlantState:
    site_id: str
    site_name: str
    tick: int
    assets: dict[str, AssetState]
    telemetry: TelemetryState
    settings: PlantSettings
    reserve: ReserveState
    sequences: dict[str, SequenceState]
    network_health: NetworkHealth
    alarms: list[Alarm] = field(default_factory=list)
    event_log: list[PlantEvent] = field(default_factory=list)
    pending_actions: dict[str, ControlAction] = field(default_factory=dict)
    applied_actions: list[ControlAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return _to_plain(data)


def _to_plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value
