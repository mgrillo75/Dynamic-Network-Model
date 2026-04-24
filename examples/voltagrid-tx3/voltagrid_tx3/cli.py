from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from voltagrid_tx3.agent_loop import ToolTrace, run
from voltagrid_tx3.prompts import system_message
from voltagrid_tx3.simulator import get_simulator, reset_simulator

app = typer.Typer(help="VoltaGrid TX-3 core islanded microgrid simulation copilot.")
console = Console()


@app.command()
def summary() -> None:
    sim = get_simulator()
    state = sim.state
    console.print(
        Panel.fit(
            f"{state.site_name}\n"
            f"bus={state.telemetry.bus_voltage_pu:.3f} pu  "
            f"freq={state.telemetry.bus_frequency_hz:.2f} Hz  "
            f"load={state.telemetry.customer_load_mw:.1f} MW\n"
            f"online={state.reserve.online_generators}  "
            f"required={state.reserve.required_generators}  "
            f"IRM={state.reserve.reserve_margin_pct:.1f}%",
            title=state.site_id,
        )
    )
    tbl = Table(title="Sequences")
    for col in ("name", "status", "step", "description"):
        tbl.add_column(col)
    for name, seq in state.sequences.items():
        tbl.add_row(name, seq.status, str(seq.step), seq.description)
    console.print(tbl)


@app.command()
def scenario(name: str = typer.Argument(..., help="Scenario name to inject")) -> None:
    sim = get_simulator()
    result = sim.step(scenario=name)
    console.print_json(
        json.dumps(
            {"tick": result["tick"], "events": result["state"]["event_log"][-5:]}
        )
    )


@app.command()
def propose(
    operation: str,
    target_asset_id: str | None = None,
    value: str | None = None,
    reason: str = "",
) -> None:
    sim = get_simulator()
    parsed_value = _parse_value(value)
    console.print_json(
        json.dumps(
            sim.propose_action(
                operation=operation,
                target_asset_id=target_asset_id,
                value=parsed_value,
                requested_by="cli",
                reason=reason,
            )
        )
    )


@app.command()
def confirm(action_id: str) -> None:
    console.print_json(json.dumps(get_simulator().confirm_action(action_id, confirmed_by="cli")))


@app.command()
def reset() -> None:
    reset_simulator()
    console.print("TX-3 simulator reset")


@app.command()
def bus() -> None:
    console.print_json(json.dumps(get_simulator().bus.snapshot()))


@app.command()
def chat() -> None:
    history: list[dict] = [system_message()]
    console.print(
        Panel.fit(
            "Ask about TX-3 reserve margin, Party Mode, blackout recovery, "
            "black start, or alarms.\n"
            "Ctrl-D to exit.",
            title="VoltaGrid TX-3 copilot",
        )
    )
    while True:
        try:
            user_text = console.input("[bold green]you>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not user_text:
            continue

        def on_trace(trace: ToolTrace) -> None:
            console.print(f"[dim]tool: {trace.name}({trace.arguments})[/dim]")

        turn = run(user_text, history=history, on_trace=on_trace)
        console.print(Panel(turn.final_text or "(no content)", title="hermes"))


def _parse_value(value: str | None):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return float(value)
        except ValueError:
            return value


if __name__ == "__main__":
    app()
