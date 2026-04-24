# VoltaGrid TX-3 Simulation Copilot

This example is a sibling to `examples/hermes-riverside`. It keeps the local-first
Hermes pattern, but swaps the Riverside distribution adapter for a deterministic
TX-3 core islanded-microgrid simulator.

The simulator is intentionally control-sequence focused. It models a representative
subset of the VoltaGrid documents: MV gensets, sync condensers, MV feeders, LV
black-start equipment, master controllers, FEP health, breaker state, reserve
margin, Party Mode, fast disconnect, blackout recovery, and black start.

It does not connect to plant equipment, SCADA, Ignition, RTDS, or HIL hardware.
All actions are sandbox-only and require explicit operator confirmation before
state mutates.

## Quickstart

```powershell
cd examples\voltagrid-tx3
python -m pip install -e ".[dev]"
python -m pytest
python -m voltagrid_tx3.cli summary
python -m voltagrid_tx3.cli scenario irm_shortfall
streamlit run voltagrid_tx3\ui\app.py
```

## Layout

```text
voltagrid_tx3/
  models.py       canonical PlantState, PlantEvent, ControlAction schemas
  simulator.py    deterministic controller and sequence state machine
  tools.py        Hermes tool registry over simulator state
  prompts.py      VoltaGrid HERMES.md profile loader
  bus.py          in-process message-bus topic projection
  cli.py          local operator and scenario commands
  ui/app.py       Streamlit control-room emulator
config/
  tx3-core.json   representative site seed data
fixtures/
  scenarios/      deterministic scenario inputs for tests and demos
```
