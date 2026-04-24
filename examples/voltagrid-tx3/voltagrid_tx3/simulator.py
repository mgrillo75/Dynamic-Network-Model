from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from voltagrid_tx3.bus import MessageBus
from voltagrid_tx3.config import load_site_config
from voltagrid_tx3.models import (
    ActionStatus,
    Alarm,
    AssetKind,
    AssetState,
    BreakerState,
    ControlAction,
    ControlMode,
    EventSeverity,
    LocalRemoteMode,
    NetworkHealth,
    PlantEvent,
    PlantSettings,
    PlantState,
    ReserveState,
    RunState,
    SequenceState,
    SequenceStatus,
    TelemetryState,
)


class PlantSimulator:
    """Deterministic TX-3 core plant simulator.

    The simulator models controller-visible state and sequence logic. It is not
    an EMT solver and intentionally keeps all control actions sandbox-local.
    """

    def __init__(self, config: dict[str, Any] | None = None, bus: MessageBus | None = None):
        self.config = deepcopy(config or load_site_config())
        self.bus = bus or MessageBus()
        self._next_event = 1
        self._next_alarm = 1
        self._next_action = 1
        self._active_event_kinds: set[str] = set()
        self.state = self._build_initial_state()
        self._recompute()
        self._publish()

    def _build_initial_state(self) -> PlantState:
        assets: dict[str, AssetState] = {}

        for raw in self.config["gensets"]:
            running = bool(raw.get("running", False))
            assets[raw["asset_id"]] = AssetState(
                asset_id=raw["asset_id"],
                name=raw["name"],
                kind=AssetKind.GENSET,
                run_state=RunState.RUNNING if running else RunState.STOPPED,
                breaker_state=BreakerState.CLOSED if running else BreakerState.OPEN,
                rated_mw=3.3,
                rated_mva=3.845,
                priority=int(raw["priority"]),
                engine_hours=float(raw["engine_hours"]),
                online=running,
                tags={"operator_panel": "auto_remote_synch_auto"},
            )

        for raw in self.config["sync_cons"]:
            available = bool(raw.get("available", True))
            assets[raw["asset_id"]] = AssetState(
                asset_id=raw["asset_id"],
                name=raw["name"],
                kind=AssetKind.SYNC_CONDENSER,
                run_state=RunState.RUNNING if available else RunState.UNAVAILABLE,
                breaker_state=BreakerState.CLOSED if available else BreakerState.OPEN,
                mvar_capacity=float(raw["mvar_capacity"]),
                online=available,
                available=available,
            )

        for raw in self.config["feeders"]:
            assets[raw["asset_id"]] = AssetState(
                asset_id=raw["asset_id"],
                name=raw["name"],
                kind=AssetKind.MV_FEEDER,
                breaker_state=BreakerState.CLOSED,
                load_mw=float(raw["load_mw"]),
                online=True,
            )

        assets["EDG-01"] = AssetState(
            asset_id="EDG-01",
            name="VG E-House 1.5 MVA EDG",
            kind=AssetKind.LV_BLACK_START,
            run_state=RunState.STOPPED,
            breaker_state=BreakerState.OPEN,
            rated_mw=1.2,
            rated_mva=1.5,
            available=True,
        )
        assets["MC-A"] = AssetState(
            asset_id="MC-A",
            name="Primary SEL Master Controller",
            kind=AssetKind.MASTER_CONTROLLER,
            run_state=RunState.RUNNING,
            online=True,
        )
        assets["MC-B"] = AssetState(
            asset_id="MC-B",
            name="Secondary SEL Master Controller",
            kind=AssetKind.MASTER_CONTROLLER,
            run_state=RunState.RUNNING,
            online=True,
        )
        assets["FEP-AUX-A"] = AssetState(
            asset_id="FEP-AUX-A",
            name="Feeder/Auxiliary FEP A",
            kind=AssetKind.FEP,
            run_state=RunState.RUNNING,
            online=True,
        )
        assets["FEP-AUX-B"] = AssetState(
            asset_id="FEP-AUX-B",
            name="Feeder/Auxiliary FEP B",
            kind=AssetKind.FEP,
            run_state=RunState.RUNNING,
            online=True,
        )

        settings_raw = self.config["settings"]
        return PlantState(
            site_id=self.config["site_id"],
            site_name=self.config["site_name"],
            tick=0,
            assets=assets,
            telemetry=TelemetryState(
                bus_voltage_pu=1.0,
                bus_frequency_hz=60.0,
                customer_load_mw=float(self.config["customer_load_mw"]),
            ),
            settings=PlantSettings(
                irm_percent=float(settings_raw["irm_percent"]),
                minimum_synchronized_generators=int(settings_raw["minimum_synchronized_generators"]),
                minimum_genset_load_pct=float(settings_raw["minimum_genset_load_pct"]),
                secondary_black_start_generators=int(
                    settings_raw["secondary_black_start_generators"]
                ),
            ),
            reserve=ReserveState(),
            sequences={
                "blackout_recovery": SequenceState(name="blackout_recovery"),
                "black_start": SequenceState(name="black_start"),
            },
            network_health=NetworkHealth(),
        )

    def snapshot(self) -> dict[str, Any]:
        return self.state.to_dict()

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        asset = self.state.assets.get(asset_id)
        return asset.to_dict() if asset else {"error": f"unknown asset '{asset_id}'"}

    def get_topology(self) -> dict[str, Any]:
        gensets = [a.asset_id for a in self._gensets()]
        sync_cons = [a.asset_id for a in self._sync_cons()]
        feeders = [a.asset_id for a in self._feeders()]
        return {
            "site_id": self.state.site_id,
            "mv_bus": {
                "nominal_kv": self.config["nominal_bus_kv"],
                "voltage_pu": self.state.telemetry.bus_voltage_pu,
                "frequency_hz": self.state.telemetry.bus_frequency_hz,
            },
            "generation": gensets,
            "sync_condensers": sync_cons,
            "customer_feeders": feeders,
            "lv_black_start": ["EDG-01"],
            "critical_aux_loads": list(self.config["critical_aux_loads"]),
            "controllers": ["MC-A", "MC-B", "FEP-AUX-A", "FEP-AUX-B"],
        }

    def propose_action(
        self,
        operation: str,
        target_asset_id: str | None = None,
        value: Any = None,
        requested_by: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        valid, message = self._validate(operation, target_asset_id, value)
        action = ControlAction(
            action_id=f"ACT-{self._next_action:05d}",
            operation=operation,
            target_asset_id=target_asset_id,
            value=value,
            requested_by=requested_by,
            reason=reason,
            status=ActionStatus.PROPOSED if valid else ActionStatus.REJECTED,
            valid=valid,
            validation_message=message,
            tick=self.state.tick,
        )
        self._next_action += 1
        self.state.pending_actions[action.action_id] = action
        self.bus.publish(
            "vg/tx3/operator/commands",
            [a.to_dict() for a in self.state.pending_actions.values()],
        )
        return action.to_dict()

    def confirm_action(self, action_id: str, confirmed_by: str = "operator") -> dict[str, Any]:
        action = self.state.pending_actions.get(action_id)
        if not action:
            return {"error": f"unknown pending action '{action_id}'"}
        if not action.valid:
            return action.to_dict()

        action.status = ActionStatus.CONFIRMED
        action.confirmed_by = confirmed_by
        before_events = len(self.state.event_log)
        before_alarms = len(self.state.alarms)
        before_sequences = self._sequence_marker()

        self._apply_action(action)
        self._recompute()

        action.status = ActionStatus.APPLIED
        action.result_delta = self._build_action_delta(action)
        action.alarms_emitted = [a.alarm_id for a in self.state.alarms[before_alarms:]]
        after_sequences = self._sequence_marker()
        if before_sequences != after_sequences:
            action.sequence_transitions.append(after_sequences)
        if len(self.state.event_log) > before_events:
            action.result_delta["events_emitted"] = [
                e.kind for e in self.state.event_log[before_events:]
            ]

        self.state.applied_actions.append(action)
        self.state.pending_actions.pop(action_id, None)
        self._publish()
        return action.to_dict()

    def step(self, scenario: str | None = None) -> dict[str, Any]:
        self.state.tick += 1
        if scenario:
            self._apply_scenario(scenario)

        self._advance_active_sequences()
        self._recompute()
        self._evaluate_events()
        self._publish()
        return {
            "tick": self.state.tick,
            "scenario": scenario,
            "state": self.snapshot(),
        }

    def _validate(
        self, operation: str, target_asset_id: str | None, value: Any
    ) -> tuple[bool, str]:
        if operation in {"start_genset", "stop_genset", "simulate_breaker_failure"}:
            asset = self.state.assets.get(target_asset_id or "")
            if not asset or asset.kind != AssetKind.GENSET:
                return False, "target must be a known MV genset"
            if asset.control_mode == ControlMode.BLOCK:
                return False, f"{asset.asset_id} is blocked at the Control Room HMI"
            if asset.local_remote != LocalRemoteMode.REMOTE:
                return False, f"{asset.asset_id} is not in remote mode"
            if operation == "stop_genset" and not self._can_stop_genset(asset):
                return False, "stop would violate IRM or minimum synchronized generator requirement"
            return True, "valid; operator confirmation required"

        if operation == "set_mode":
            if target_asset_id not in self.state.assets:
                return False, "target asset does not exist"
            if not isinstance(value, dict):
                return False, "set_mode value must be an object"
            return True, "valid; operator confirmation required"

        if operation in {
            "enable_party_mode",
            "disable_party_mode",
            "induce_blackout",
            "continue_sequence",
            "initiate_black_start",
            "abort_sequence",
            "reset_sequence",
            "simulate_sync_con_unavailable",
            "simulate_controller_failover",
        }:
            if not self._master_available():
                return False, "no master controller is available to validate the request"
            return True, "valid; operator confirmation required"

        if operation == "set_load":
            try:
                float(value)
            except (TypeError, ValueError):
                return False, "set_load value must be numeric MW"
            return True, "valid; operator confirmation required"

        return False, f"unsupported operation '{operation}'"

    def _apply_action(self, action: ControlAction) -> None:
        op = action.operation
        target = self.state.assets.get(action.target_asset_id or "")

        if op == "start_genset" and target:
            self._start_genset(target)
            return
        if op == "stop_genset" and target:
            self._stop_genset(target)
            return
        if op == "set_mode" and target:
            self._set_mode(target, action.value)
            return
        if op == "enable_party_mode":
            self._set_party_mode(True)
            return
        if op == "disable_party_mode":
            self._set_party_mode(False)
            return
        if op == "simulate_breaker_failure" and target:
            self._fast_disconnect(target)
            return
        if op == "induce_blackout":
            self._apply_blackout()
            return
        if op == "continue_sequence":
            self._advance_active_sequences(force=True)
            return
        if op == "initiate_black_start":
            self._initiate_black_start()
            return
        if op == "abort_sequence":
            self._abort_sequences()
            return
        if op == "reset_sequence":
            self._reset_sequences()
            return
        if op == "simulate_sync_con_unavailable":
            self._set_sync_con_unavailable()
            return
        if op == "simulate_controller_failover":
            self._failover_controller()
            return
        if op == "set_load":
            self.state.telemetry.customer_load_mw = float(action.value)

    def _apply_scenario(self, scenario: str) -> None:
        if scenario == "normal":
            return
        if scenario == "irm_shortfall":
            self.state.telemetry.customer_load_mw = 34.0
            return
        if scenario == "minimum_load_conflict":
            for asset in self._gensets():
                if asset.asset_id in {"G07", "G08"}:
                    self._stop_genset(asset, force=True)
            self.state.telemetry.customer_load_mw = 8.0
            return
        if scenario == "party_mode":
            self._set_party_mode(True)
            return
        if scenario == "breaker_failure":
            self._fast_disconnect(self.state.assets["G01"])
            return
        if scenario == "blackout":
            self._apply_blackout()
            return
        if scenario == "sync_con_unavailable":
            self._set_sync_con_unavailable()
            return
        if scenario == "controller_failover":
            self._failover_controller()
            return
        self._emit_event(
            kind="unknown_scenario",
            source="simulator",
            severity=EventSeverity.ALERT,
            assets=[],
            summary=f"Unknown simulator scenario '{scenario}' requested.",
        )

    def _start_genset(self, asset: AssetState) -> None:
        asset.run_state = RunState.RUNNING
        asset.breaker_state = BreakerState.CLOSED
        asset.online = True

    def _stop_genset(self, asset: AssetState, force: bool = False) -> None:
        if force or self._can_stop_genset(asset):
            asset.run_state = RunState.STOPPED
            asset.breaker_state = BreakerState.OPEN
            asset.online = False

    def _set_mode(self, asset: AssetState, value: dict[str, Any]) -> None:
        if "control_mode" in value:
            asset.control_mode = ControlMode(str(value["control_mode"]))
        if "local_remote" in value:
            asset.local_remote = LocalRemoteMode(str(value["local_remote"]))

    def _set_party_mode(self, enabled: bool) -> None:
        self.state.settings.party_mode = enabled
        if enabled:
            for asset in self._gensets():
                if (
                    asset.available
                    and asset.control_mode == ControlMode.AUTO
                    and asset.local_remote == LocalRemoteMode.REMOTE
                ):
                    self._start_genset(asset)
            self._emit_event(
                kind="party_mode_enabled",
                source="control_room_hmi",
                severity=EventSeverity.INFO,
                assets=[a.asset_id for a in self._gensets()],
                summary="Party Mode enabled; all auto/remote gensets demanded online.",
            )
        else:
            self._emit_event(
                kind="party_mode_disabled",
                source="control_room_hmi",
                severity=EventSeverity.INFO,
                assets=[],
                summary="Party Mode disabled; IRM and minimum-load management resumed.",
            )

    def _fast_disconnect(self, asset: AssetState) -> None:
        asset.run_state = RunState.TRIPPED
        asset.breaker_state = BreakerState.OPEN
        asset.online = False
        asset.tags["fast_disconnect"] = True
        alarm = self._add_alarm(
            EventSeverity.ALARM,
            asset.asset_id,
            f"Fast disconnect asserted for {asset.asset_id} after breaker failure.",
        )
        self._emit_event(
            kind="breaker_failure_fast_disconnect",
            source="SEL-700G/DIANE",
            severity=EventSeverity.ALARM,
            assets=[asset.asset_id],
            summary=alarm.message,
        )

    def _apply_blackout(self) -> None:
        self.state.telemetry.bus_voltage_pu = 0.0
        self.state.telemetry.bus_frequency_hz = 0.0
        for asset in self._gensets():
            asset.online = False
            asset.run_state = RunState.STOPPED
            asset.breaker_state = BreakerState.OPEN
        for asset in self._feeders():
            asset.online = False
            asset.breaker_state = BreakerState.OPEN
        recovery = self.state.sequences["blackout_recovery"]
        recovery.status = SequenceStatus.IN_PROGRESS
        recovery.step = 0
        recovery.description = "Blackout detected; confirming dead bus and opening ICBs."
        recovery.paused_reason = None
        self._add_alarm(EventSeverity.ALARM, "main_bus", "System-wide blackout detected.")
        self._emit_event(
            kind="blackout_detected",
            source="master_controller",
            severity=EventSeverity.ALARM,
            assets=["main_bus"],
            summary="Main bus and VG E-House bus are de-energized.",
        )

    def _initiate_black_start(self) -> None:
        recovery = self.state.sequences["blackout_recovery"]
        black_start = self.state.sequences["black_start"]
        if recovery.status != SequenceStatus.COMPLETE:
            black_start.status = SequenceStatus.PAUSED
            black_start.paused_reason = "Blackout recovery is not complete."
            self._emit_event(
                kind="black_start_paused",
                source="master_controller",
                severity=EventSeverity.ALERT,
                assets=[],
                summary=black_start.paused_reason,
            )
            return
        black_start.status = SequenceStatus.IN_PROGRESS
        black_start.step = 0
        black_start.description = "Operator initiated black start; verifying dead bus."
        black_start.paused_reason = None
        self._emit_event(
            kind="black_start_ready",
            source="control_room_hmi",
            severity=EventSeverity.INFO,
            assets=[],
            summary="Black start initiated after successful blackout recovery.",
        )

    def _advance_active_sequences(self, force: bool = False) -> None:
        recovery = self.state.sequences["blackout_recovery"]
        if recovery.status == SequenceStatus.IN_PROGRESS and (force or recovery.step < 2):
            self._advance_blackout_recovery()
            return
        black_start = self.state.sequences["black_start"]
        if black_start.status == SequenceStatus.IN_PROGRESS and (force or black_start.step < 3):
            self._advance_black_start()

    def _advance_blackout_recovery(self) -> None:
        seq = self.state.sequences["blackout_recovery"]
        edg = self.state.assets["EDG-01"]
        if seq.step == 0:
            seq.step = 1
            seq.description = "All ICBs and VG E-House feeder breakers commanded open."
            return
        if seq.step == 1:
            if not edg.available:
                seq.status = SequenceStatus.PAUSED
                seq.paused_reason = "EDG did not become available."
                self._emit_event(
                    kind="blackout_recovery_paused",
                    source="master_controller",
                    severity=EventSeverity.ALERT,
                    assets=["EDG-01"],
                    summary=seq.paused_reason,
                )
                return
            edg.run_state = RunState.RUNNING
            edg.breaker_state = BreakerState.CLOSED
            edg.online = True
            seq.step = 2
            seq.description = "EDG online; closing VG E-House feeder breakers."
            return
        if seq.step == 2:
            seq.step = 3
            seq.status = SequenceStatus.COMPLETE
            seq.description = "Critical AUX loads energized; blackout recovery complete."
            self._emit_event(
                kind="blackout_recovery_complete",
                source="master_controller",
                severity=EventSeverity.INFO,
                assets=["EDG-01"],
                summary=seq.description,
            )

    def _advance_black_start(self) -> None:
        seq = self.state.sequences["black_start"]
        if seq.step == 0:
            available_sync = [a for a in self._sync_cons() if a.available]
            if not available_sync:
                seq.status = SequenceStatus.PAUSED
                seq.paused_reason = "No synchronous condenser is available for black start."
                self._emit_event(
                    kind="black_start_paused",
                    source="master_controller",
                    severity=EventSeverity.ALERT,
                    assets=[],
                    summary=seq.paused_reason,
                )
                return
            for asset in available_sync:
                asset.run_state = RunState.RUNNING
                asset.breaker_state = BreakerState.CLOSED
                asset.online = True
            seq.step = 1
            seq.description = "Synchronous condenser ICBs closed."
            return
        if seq.step == 1:
            lead = self._next_start_candidates(1)
            if not lead:
                self._pause_black_start("No auto/remote genset is available for lead start.")
                return
            self._start_genset(lead[0])
            self.state.telemetry.bus_voltage_pu = 1.0
            self.state.telemetry.bus_frequency_hz = 60.0
            seq.step = 2
            seq.description = f"Lead black-start genset {lead[0].asset_id} online."
            return
        if seq.step == 2:
            candidates = self._next_start_candidates(
                self.state.settings.secondary_black_start_generators
            )
            for asset in candidates:
                self._start_genset(asset)
            seq.step = 3
            seq.description = "Secondary black-start gensets online."
            return
        if seq.step == 3:
            edg = self.state.assets["EDG-01"]
            edg.run_state = RunState.STOPPED
            edg.breaker_state = BreakerState.OPEN
            edg.online = False
            for feeder in self._feeders():
                feeder.breaker_state = BreakerState.CLOSED
                feeder.online = True
            seq.step = 4
            seq.status = SequenceStatus.COMPLETE
            seq.description = (
                "Black start complete; normal IRM and minimum-load management "
                "reenabled."
            )
            self._emit_event(
                kind="black_start_complete",
                source="master_controller",
                severity=EventSeverity.INFO,
                assets=[a.asset_id for a in self._online_gensets()],
                summary=seq.description,
            )

    def _pause_black_start(self, reason: str) -> None:
        seq = self.state.sequences["black_start"]
        seq.status = SequenceStatus.PAUSED
        seq.paused_reason = reason
        self._emit_event(
            kind="black_start_paused",
            source="master_controller",
            severity=EventSeverity.ALERT,
            assets=[],
            summary=reason,
        )

    def _abort_sequences(self) -> None:
        for seq in self.state.sequences.values():
            if seq.status in {SequenceStatus.IN_PROGRESS, SequenceStatus.PAUSED}:
                seq.status = SequenceStatus.ABORTED
                seq.description = "Aborted by operator."

    def _reset_sequences(self) -> None:
        for seq in self.state.sequences.values():
            seq.status = SequenceStatus.IDLE
            seq.step = 0
            seq.description = "Idle"
            seq.paused_reason = None

    def _set_sync_con_unavailable(self) -> None:
        asset = self.state.assets["SC01"]
        asset.available = False
        asset.online = False
        asset.run_state = RunState.UNAVAILABLE
        asset.breaker_state = BreakerState.OPEN
        self._add_alarm(EventSeverity.ALERT, asset.asset_id, "Synchronous condenser unavailable.")
        self._emit_event(
            kind="sync_con_unavailable",
            source="sync_con_ccp",
            severity=EventSeverity.ALERT,
            assets=[asset.asset_id],
            summary="SC01 unavailable; voltage support redundancy reduced.",
        )

    def _failover_controller(self) -> None:
        health = self.state.network_health
        health.master_primary_online = False
        health.active_master = "MC-B"
        health.controller_failover = True
        self.state.assets["MC-A"].online = False
        self.state.assets["MC-A"].run_state = RunState.UNAVAILABLE
        self._emit_event(
            kind="controller_failover",
            source="control_network",
            severity=EventSeverity.ALERT,
            assets=["MC-A", "MC-B"],
            summary="Primary master controller offline; secondary is active.",
        )

    def _recompute(self) -> None:
        online = self._online_gensets()
        rated_mw = self._rated_genset_mw()
        online_capacity = len(online) * rated_mw
        load = self.state.telemetry.customer_load_mw
        required_capacity = load * self.state.settings.irm_percent / 100.0
        required_generators = max(
            self.state.settings.minimum_synchronized_generators,
            math.ceil(required_capacity / rated_mw) if rated_mw else 0,
        )
        avg_load_pct = (load / online_capacity * 100.0) if online_capacity else 0.0

        candidate = self._lowest_priority_online_genset()
        can_stop_candidate = bool(candidate and self._can_stop_genset(candidate))
        min_load_wants_stop = bool(
            online
            and avg_load_pct < self.state.settings.minimum_genset_load_pct
            and not self.state.settings.party_mode
        )

        self.state.telemetry.total_generation_mw = round(min(load, online_capacity), 3)
        self.state.telemetry.average_genset_load_pct = round(avg_load_pct, 2)
        if online and self.state.telemetry.bus_voltage_pu > 0:
            self.state.telemetry.bus_frequency_hz = 60.0
            self.state.telemetry.bus_voltage_pu = 1.0

        self.state.reserve = ReserveState(
            online_generators=len(online),
            required_generators=required_generators,
            online_capacity_mw=round(online_capacity, 3),
            required_capacity_mw=round(required_capacity, 3),
            reserve_margin_pct=round((online_capacity / load * 100.0), 2) if load else 0.0,
            irm_shortfall=len(online) < required_generators or online_capacity < required_capacity,
            minimum_load_conflict=min_load_wants_stop and not can_stop_candidate,
            min_load_stop_candidate=candidate.asset_id
            if min_load_wants_stop and can_stop_candidate
            else None,
        )

    def _evaluate_events(self) -> None:
        if self.state.reserve.irm_shortfall:
            self._emit_once(
                "irm_shortfall",
                "master_controller",
                EventSeverity.ALERT,
                [a.asset_id for a in self._online_gensets()],
                "Online gensets do not satisfy island reserve margin.",
                self.state.reserve.to_dict(),
            )
        else:
            self._active_event_kinds.discard("irm_shortfall")

        if self.state.reserve.minimum_load_conflict:
            self._emit_once(
                "minimum_load_conflict",
                "master_controller",
                EventSeverity.ALERT,
                [a.asset_id for a in self._online_gensets()],
                "Minimum load management wants to unload a unit, but IRM/min-sync "
                "settings prevent it.",
                self.state.reserve.to_dict(),
            )
        else:
            self._active_event_kinds.discard("minimum_load_conflict")

    def _emit_once(
        self,
        kind: str,
        source: str,
        severity: EventSeverity,
        assets: list[str],
        summary: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        if kind in self._active_event_kinds:
            return
        self._active_event_kinds.add(kind)
        self._emit_event(kind, source, severity, assets, summary, context)

    def _emit_event(
        self,
        kind: str,
        source: str,
        severity: EventSeverity,
        assets: list[str],
        summary: str,
        context: dict[str, Any] | None = None,
    ) -> PlantEvent:
        event = PlantEvent(
            event_id=f"EVT-{self._next_event:05d}",
            kind=kind,
            source=source,
            severity=severity,
            affected_assets=assets,
            tick=self.state.tick,
            summary=summary,
            context=context or {},
        )
        self._next_event += 1
        self.state.event_log.append(event)
        return event

    def _add_alarm(self, severity: EventSeverity, source: str, message: str) -> Alarm:
        alarm = Alarm(
            alarm_id=f"ALM-{self._next_alarm:05d}",
            severity=severity,
            source=source,
            message=message,
            tick=self.state.tick,
        )
        self._next_alarm += 1
        self.state.alarms.append(alarm)
        return alarm

    def _can_stop_genset(self, asset: AssetState) -> bool:
        if not asset.online:
            return True
        online_after = max(0, len(self._online_gensets()) - 1)
        rated_mw = self._rated_genset_mw()
        load = self.state.telemetry.customer_load_mw
        required_capacity = load * self.state.settings.irm_percent / 100.0
        required_generators = max(
            self.state.settings.minimum_synchronized_generators,
            math.ceil(required_capacity / rated_mw) if rated_mw else 0,
        )
        return online_after >= required_generators and online_after * rated_mw >= required_capacity

    def _master_available(self) -> bool:
        return (
            self.state.network_health.master_primary_online
            or self.state.network_health.master_secondary_online
        )

    def _gensets(self) -> list[AssetState]:
        return [a for a in self.state.assets.values() if a.kind == AssetKind.GENSET]

    def _sync_cons(self) -> list[AssetState]:
        return [a for a in self.state.assets.values() if a.kind == AssetKind.SYNC_CONDENSER]

    def _feeders(self) -> list[AssetState]:
        return [a for a in self.state.assets.values() if a.kind == AssetKind.MV_FEEDER]

    def _online_gensets(self) -> list[AssetState]:
        return [a for a in self._gensets() if a.online and a.run_state == RunState.RUNNING]

    def _rated_genset_mw(self) -> float:
        gensets = self._gensets()
        return gensets[0].rated_mw if gensets else 0.0

    def _lowest_priority_online_genset(self) -> AssetState | None:
        online = self._online_gensets()
        if not online:
            return None
        return sorted(online, key=lambda a: (a.priority, -a.engine_hours), reverse=True)[0]

    def _next_start_candidates(self, count: int) -> list[AssetState]:
        candidates = [
            a
            for a in self._gensets()
            if not a.online
            and a.available
            and a.control_mode == ControlMode.AUTO
            and a.local_remote == LocalRemoteMode.REMOTE
            and a.run_state != RunState.TRIPPED
        ]
        return sorted(candidates, key=lambda a: (a.priority, a.engine_hours))[:count]

    def _sequence_marker(self) -> str:
        return "|".join(
            f"{name}:{seq.status}:{seq.step}:{seq.description}"
            for name, seq in sorted(self.state.sequences.items())
        )

    def _build_action_delta(self, action: ControlAction) -> dict[str, Any]:
        return {
            "operation": action.operation,
            "target_asset_id": action.target_asset_id,
            "reserve": self.state.reserve.to_dict(),
            "telemetry": self.state.telemetry.to_dict(),
        }

    def _publish(self) -> None:
        self.bus.publish_state(self.state)


_SIMULATOR: PlantSimulator | None = None


def get_simulator() -> PlantSimulator:
    global _SIMULATOR
    if _SIMULATOR is None:
        _SIMULATOR = PlantSimulator()
    return _SIMULATOR


def reset_simulator() -> PlantSimulator:
    global _SIMULATOR
    _SIMULATOR = PlantSimulator()
    return _SIMULATOR
