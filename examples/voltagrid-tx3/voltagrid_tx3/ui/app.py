from __future__ import annotations

import json

import streamlit as st

from voltagrid_tx3.agent_loop import run
from voltagrid_tx3.prompts import system_message
from voltagrid_tx3.simulator import PlantSimulator
from voltagrid_tx3.ui.view_model import build_dashboard_state

st.set_page_config(page_title="VoltaGrid TX-3 Copilot", layout="wide")


def _sim() -> PlantSimulator:
    if "sim" not in st.session_state:
        st.session_state.sim = PlantSimulator()
    return st.session_state.sim


sim = _sim()
view = build_dashboard_state(sim)

st.title("VoltaGrid TX-3 Core Simulator")
st.caption(
    f"{view['site']['site_id']}  |  tick {view['site']['tick']}  |  "
    f"active master {view['network_health']['active_master']}"
)

with st.sidebar:
    scenario = st.selectbox(
        "Scenario",
        [
            "normal",
            "irm_shortfall",
            "minimum_load_conflict",
            "party_mode",
            "breaker_failure",
            "blackout",
            "sync_con_unavailable",
            "controller_failover",
        ],
    )
    if st.button("Step", use_container_width=True):
        sim.step(scenario=scenario)
        st.rerun()
    if st.button("Reset", use_container_width=True):
        st.session_state.sim = PlantSimulator()
        st.session_state.pop("history", None)
        st.session_state.pop("turns", None)
        st.rerun()

top = st.columns(5)
top[0].metric("Main Bus", f"{view['telemetry']['bus_voltage_pu']:.3f} pu")
top[1].metric("Frequency", f"{view['telemetry']['bus_frequency_hz']:.2f} Hz")
top[2].metric("Load", f"{view['telemetry']['customer_load_mw']:.1f} MW")
top[3].metric("Online", f"{view['reserve']['online_generators']} gensets")
top[4].metric("IRM", f"{view['reserve']['reserve_margin_pct']:.0f}%")

tabs = st.tabs(["Site", "MV Power", "Sequences", "Alarms", "Copilot", "Bus"])

with tabs[0]:
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Customer Feeders")
        st.dataframe(
            [
                {
                    "asset": f["asset_id"],
                    "name": f["name"],
                    "breaker": f["breaker_state"],
                    "online": f["online"],
                    "load_mw": f["load_mw"],
                }
                for f in view["feeders"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.subheader("Network")
        st.json(view["network_health"])

with tabs[1]:
    st.subheader("MV Gensets")
    st.dataframe(
        [
            {
                "asset": g["asset_id"],
                "priority": g["priority"],
                "state": g["run_state"],
                "breaker": g["breaker_state"],
                "mode": g["control_mode"],
                "remote": g["local_remote"],
                "hours": g["engine_hours"],
            }
            for g in view["gensets"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        target = st.selectbox("Genset", [g["asset_id"] for g in view["gensets"]])
    with c2:
        operation = st.selectbox(
            "Operation",
            ["start_genset", "stop_genset", "simulate_breaker_failure"],
        )
    with c3:
        if st.button("Propose", use_container_width=True):
            sim.propose_action(
                operation,
                target_asset_id=target,
                requested_by="hmi",
                reason="operator panel",
            )
            st.rerun()

    st.subheader("Pending Actions")
    for action in view["pending_actions"]:
        cols = st.columns([2, 2, 2, 1])
        cols[0].write(action["action_id"])
        cols[1].write(action["operation"])
        cols[2].write(action["validation_message"])
        if cols[3].button("Confirm", key=f"confirm-{action['action_id']}"):
            sim.confirm_action(action["action_id"], confirmed_by="hmi")
            st.rerun()

with tabs[2]:
    seq_cols = st.columns(2)
    for idx, (name, seq) in enumerate(view["sequences"].items()):
        with seq_cols[idx % 2]:
            st.subheader(name)
            st.json(seq)
    b1, b2, b3 = st.columns(3)
    if b1.button("Continue Sequence", use_container_width=True):
        action = sim.propose_action(
            "continue_sequence",
            requested_by="hmi",
            reason="sequence panel",
        )
        sim.confirm_action(action["action_id"], confirmed_by="hmi")
        st.rerun()
    if b2.button("Initiate Black Start", use_container_width=True):
        sim.propose_action("initiate_black_start", requested_by="hmi", reason="sequence panel")
        st.rerun()
    if b3.button("Abort Sequence", use_container_width=True):
        sim.propose_action("abort_sequence", requested_by="hmi", reason="sequence panel")
        st.rerun()

with tabs[3]:
    st.subheader("Active Alarms")
    st.dataframe(view["alarms"], use_container_width=True, hide_index=True)
    st.subheader("Recent Events")
    st.dataframe(view["events"], use_container_width=True, hide_index=True)

with tabs[4]:
    if "history" not in st.session_state:
        st.session_state.history = [system_message()]
    if "turns" not in st.session_state:
        st.session_state.turns = []
    for user_text, final_text, traces in st.session_state.turns:
        with st.chat_message("user"):
            st.write(user_text)
        with st.chat_message("assistant"):
            st.write(final_text)
        with st.expander("Tool trace", expanded=False):
            st.json([trace.__dict__ for trace in traces])

    prompt = st.chat_input("TX-3 event or operating question")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        traces = []
        with st.chat_message("assistant"):
            turn = run(prompt, history=st.session_state.history, on_trace=traces.append)
            st.write(turn.final_text)
        st.session_state.turns.append((prompt, turn.final_text, traces))
        st.rerun()

with tabs[5]:
    st.subheader("Message Bus Topics")
    st.json(view["bus_topics"])
    st.code(json.dumps(view["bus_topics"], indent=2), language="json")
