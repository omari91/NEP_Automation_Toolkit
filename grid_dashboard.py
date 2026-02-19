import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pandapower as pp
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from stransient_loader import (
    build_net_from_pypsa_export,
    build_net_from_stransient,
    summarize_pypsa_export,
)


_SCRIPT_PATH = Path(__file__).resolve()
_PROJECT_ROOT = (
    _SCRIPT_PATH.parent.parent
    if _SCRIPT_PATH.parent.name == "__pycache__"
    else _SCRIPT_PATH.parent
)
DEFAULT_STRANSIENT_PATH = _PROJECT_ROOT.joinpath(
    "pypsa-de",
    "results",
    "20260114_limit_cross_border_flows",
    "KN2045_Mix",
    "stransient",
)

_LOCAL_PYPSA_EXPORT_PATH = Path(
    r"C:\Users\HP\pypsa-de\results\20260114_limit_cross_border_flows\KN2045_Mix\exports"
)
DEFAULT_PYPSA_EXPORT_PATH = (
    _LOCAL_PYPSA_EXPORT_PATH
    if _LOCAL_PYPSA_EXPORT_PATH.exists()
    else _PROJECT_ROOT.joinpath(
        "pypsa-de",
        "results",
        "20260114_limit_cross_border_flows",
        "KN2045_Mix",
        "exports",
    )
)


# -----------------------------
# 1) PAGE SETUP
# -----------------------------
st.set_page_config(page_title="TSO Grid Planning – Security & Stability", layout="wide")
st.title("⚡ TSO Network Planning: Operational Security + Stability Dashboard")
st.markdown("""
**System Scope:** 380kV / 110kV EHV–HV coupling  
**Regulatory framing:** VDE-AR-N 4110 & 4120 (screening-level checks)

This dashboard automates **N-1 security** (steady-state) and adds **stability screening**:
- **Voltage stability:** PV curve (loadability margin) + sensitivity indicators  
- **Dynamic screening:** simplified frequency/angle response (method illustration; EMT tools like PSCAD/PowerFactory are used for full studies)
""")

# -----------------------------
# 2) CONTROL PANEL
# -----------------------------
st.sidebar.header("🕹️ Study Controls")

DATA_SOURCE_OPTIONS = [
    "Template grid (built-in demo)",
    "PyPSA-DE STRANSIENT export",
    "PyPSA-DE export folder",
]
with st.sidebar.expander("📂 Data Source", expanded=True):
    data_source = st.radio("Network data source", DATA_SOURCE_OPTIONS, index=0)
    use_stransient_data = data_source == DATA_SOURCE_OPTIONS[1]
    use_pypsa_export_data = data_source == DATA_SOURCE_OPTIONS[2]

    _cached_stransient_path = st.session_state.get("stransient_path_input", str(DEFAULT_STRANSIENT_PATH))
    if use_stransient_data:
        stransient_path_input = st.text_input(
            "STRANSIENT export folder",
            value=_cached_stransient_path,
            help="Folder containing stransient_bus.csv, stransient_branch.csv, etc.",
            key="stransient_path_input",
        )
    else:
        stransient_path_input = _cached_stransient_path
    stransient_path = Path(stransient_path_input).expanduser()
    if use_stransient_data:
        st.caption(f"Working folder: {stransient_path}")

    bus_options = []
    load_options = []
    stransient_error = ""
    stransient_ready = False

    if stransient_path.is_dir():
        try:
            bus_df = pd.read_csv(stransient_path / "stransient_bus.csv")
            load_df = pd.read_csv(stransient_path / "stransient_load.csv")
            bus_options = bus_df["bus_id"].astype(str).tolist()
            load_options = load_df["load_id"].astype(str).tolist()
            if bus_options and load_options:
                stransient_ready = True
            else:
                stransient_error = "Exports found but missing bus/load entries."
        except Exception as exc:  # pragma: no cover
            stransient_error = f"Failed to read STRANSIENT exports: {exc}"
    elif use_stransient_data:
        stransient_error = f"{stransient_path} does not exist."

    if use_stransient_data and not stransient_ready:
        st.error(stransient_error or "Provide a valid STRANSIENT export folder.")

    slack_bus_id = None
    load_choice = None
    if use_stransient_data and stransient_ready:
        slack_bus_id = st.selectbox("Slack bus (ext. grid)", bus_options, index=0)
        load_choice = st.selectbox("Load for PV curve", load_options, index=0)
        st.caption(f"{len(bus_options)} buses · {len(load_options)} loads available")

    _cached_pypsa_path = st.session_state.get("pypsa_export_path_input", str(DEFAULT_PYPSA_EXPORT_PATH))
    if use_pypsa_export_data:
        pypsa_export_path_input = st.text_input(
            "PyPSA export folder",
            value=_cached_pypsa_path,
            help="Folder containing buses.csv, lines.csv, generators.csv, loads.csv (full PyPSA export)",
            key="pypsa_export_path_input",
        )
    else:
        pypsa_export_path_input = _cached_pypsa_path
    pypsa_export_path = Path(pypsa_export_path_input).expanduser()
    if use_pypsa_export_data:
        st.caption(f"Working folder: {pypsa_export_path}")

    pypsa_export_error = ""
    pypsa_export_ready = False
    pypsa_bus_count = 0
    pypsa_load_count = 0
    pypsa_default_slack = ""
    pypsa_default_load = ""

    if use_pypsa_export_data:
        if pypsa_export_path.is_dir():
            try:
                summary = summarize_pypsa_export(pypsa_export_path)
                pypsa_bus_count = summary.get("bus_count", 0) or 0
                pypsa_load_count = summary.get("load_count", 0) or 0
                pypsa_default_slack = summary.get("default_slack") or ""
                pypsa_default_load = summary.get("default_load") or ""
                pypsa_export_ready = True
            except Exception as exc:  # pragma: no cover
                pypsa_export_error = f"Failed to read PyPSA export: {exc}"
        else:
            pypsa_export_error = f"{pypsa_export_path} does not exist."

    if use_pypsa_export_data:
        if pypsa_export_ready:
            st.caption(f"{pypsa_bus_count} buses · {pypsa_load_count} loads available")
        else:
            st.error(pypsa_export_error or "Provide a valid PyPSA export folder.")

        slack_default = st.session_state.get("pypsa_slack_bus", pypsa_default_slack or "")
        slack_bus_id = st.text_input(
            "Slack bus (ext. grid)",
            value=slack_default,
            help="Bus name from buses.csv that should act as the slack/source bus.",
            key="pypsa_slack_bus",
        )
        load_default = st.session_state.get("pypsa_load_choice", pypsa_default_load or "")
        load_choice = st.text_input(
            "Load for PV curve",
            value=load_default,
            help="Load name from loads.csv; used for the PV curve/loadability plot.",
            key="pypsa_load_choice",
        )

with st.sidebar.expander("🌍 Scenario Configuration", expanded=True):
    wind_mw = st.slider(
        "Offshore Wind Infeed (MW)",
        0,
        1500,
        1200,
        disabled=use_stransient_data or use_pypsa_export_data,
    )
    load_mw = st.slider(
        "Regional HV Demand (MW)",
        500,
        2500,
        2200,
        disabled=use_stransient_data or use_pypsa_export_data,
    )
    load_q_factor = st.slider(
        "Load Q/P factor",
        0.05,
        0.60,
        0.45,
        0.01,
        disabled=use_stransient_data or use_pypsa_export_data,
    )

with st.sidebar.expander("🚀 Power Electronics (STATCOM/HVDC)"):
    hvdc_p = st.slider(
        "HVDC P (MW)",
        0,
        1000,
        800,
        disabled=use_stransient_data or use_pypsa_export_data,
    )
    hvdc_q = st.slider(
        "HVDC Q support (MVAr)",
        -300,
        300,
        150,
        disabled=use_stransient_data or use_pypsa_export_data,
    )
    statcom_q = st.slider(
        "STATCOM Q support (MVAr)",
        -300,
        300,
        60,
        disabled=use_stransient_data or use_pypsa_export_data,
    )
    hvdc_enabled = st.toggle("Enable HVDC link", value=True)
    ffr_enabled = st.toggle("Enable HVDC FFR (synthetic inertia)", value=True)

with st.sidebar.expander("🛠️ Asset Specs / Limits"):
    st.caption("Transformer OLTC")
    trafo_tap = st.slider("Tap position", -10, 10, 0)
    st.caption("380kV Thermal Limits")
    line_limit_ka = st.number_input(
        "Max current (kA)",
        1.0,
        5.0,
        4.0,
        disabled=use_stransient_data or use_pypsa_export_data,
    )

with st.sidebar.expander("🚨 Security Criteria (N-1)"):
    trip_line = st.toggle("Trip L1-380kV Backbone (N-1)", value=False)
    st.caption("N-1: system must remain within limits after one credible outage.")


if use_stransient_data or use_pypsa_export_data:
    wind_mw = 0.0
    load_mw = 0.0
    load_q_factor = 0.0
    hvdc_p = 0
    hvdc_q = 0
    statcom_q = 0
    hvdc_enabled = False
    ffr_enabled = False
    trip_line = False
with st.sidebar.expander("📉 Dynamic Screening (illustrative)"):
    fault_bus_sel = st.selectbox(
        "Three-phase fault location",
        ["North Hub (Generation)", "South Hub (Interconnection)", "Regional Hub (Demand)"]
    )
    fault_duration = st.slider("Fault clearing time (ms)", 50, 500, 100)
    system_inertia = st.slider("System inertia H", 2.0, 8.0, 4.0)

with st.sidebar.expander("🧪 Voltage Stability PV Curve"):
    pv_steps = st.slider("PV curve steps", 10, 60, 30)
    pv_max_scale = st.slider("Max load scaling (×)", 1.0, 3.0, 2.0, 0.1)
    pv_voltage_floor = st.slider("Voltage collapse indicator (pu)", 0.70, 0.95, 0.85, 0.01)

# -----------------------------
# 3) GRID MODEL
# -----------------------------
def build_template_grid(is_n_1: bool) -> pp.pandapowerNet:
    net = pp.create_empty_network()

    # Buses
    b_north = pp.create_bus(net, vn_kv=380, name="North Hub (Generation)")
    b_south = pp.create_bus(net, vn_kv=380, name="South Hub (Interconnection)")
    b_regional = pp.create_bus(net, vn_kv=110, name="Regional Hub (Demand)")

    # Slack
    pp.create_ext_grid(net, bus=b_north, vm_pu=1.03, name="External Interconnection")

    # Lines
    line_cfg = {"r_ohm_per_km": 0.015, "x_ohm_per_km": 0.20, "c_nf_per_km": 15, "max_i_ka": line_limit_ka}
    pp.create_line_from_parameters(net, b_north, b_south, 50, name="Line L1-380kV", in_service=not is_n_1, **line_cfg)
    pp.create_line_from_parameters(net, b_north, b_south, 50, name="Line L2-380kV", **line_cfg)

    # Transformer
    pp.create_transformer_from_parameters(
        net,
        hv_bus=b_south, lv_bus=b_regional,
        sn_mva=1000, vn_hv_kv=380, vn_lv_kv=110,
        vk_percent=12, vkr_percent=0.1,
        pfe_kw=40, i0_percent=0.05,
        shift_degree=0,
        tap_side="hv", tap_neutral=0, tap_min=-10, tap_max=10,
        tap_step_percent=1.25, tap_pos=trafo_tap,
        name="T1-380/110"
    )

    # Generation / Load
    pp.create_sgen(net, bus=b_north, p_mw=wind_mw, q_mvar=wind_mw * 0.10, name="Offshore Wind Farm")
    pp.create_load(net, bus=b_regional, p_mw=load_mw, q_mvar=load_mw * load_q_factor, name="Regional Load Cluster")

    # Power electronics
    if hvdc_enabled:
        pp.create_sgen(net, bus=b_regional, p_mw=hvdc_p, q_mvar=hvdc_q, name="HVDC VSC Converter")

    if statcom_q != 0:
        # pandapower shunt uses q_mvar injected (negative means capacitive depending on convention)
        pp.create_shunt(net, bus=b_regional, q_mvar=-statcom_q, name="STATCOM Unit")

    net.load["load_id"] = net.load["name"]
    net.sgen["gen_id"] = net.sgen["name"]

    return net


# -----------------------------
# 4) DYNAMIC SCREENING (illustrative)
# -----------------------------
def simulate_dynamics(
    duration_ms: int,
    h_val: float,
    ffr_on: bool,
    generation_mw: float,
    load_mw: float,
) -> pd.DataFrame:
    """
    Screening-only. Purpose: show method + interpretability.
    Full EMT / RMS dynamic validation should be done in PSCAD / PowerFactory DSL models.
    """
    time = np.linspace(0, 3.0, 180)
    f_nom = 50.0
    h_eff = h_val + (1.5 if ffr_on else 0.0)

    # crude imbalance proxy (MW -> pu)
    p_accel = (generation_mw - load_mw) / 1000.0
    rocof = f_nom * (p_accel) / (2 * max(h_eff, 0.1))

    # frequency response with damping
    freq = f_nom + (rocof * time) * np.exp(-time * 1.8)

    # rotor swing proxy: longer fault -> bigger excursion, damped oscillation
    osc = 25 * np.sin(2 * np.pi * 1.2 * time) * np.exp(-time * 0.9)
    angle = 20 + (duration_ms / 6.0) + osc
    return pd.DataFrame({"Time (s)": time, "Rotor Angle (deg)": angle, "Frequency (Hz)": freq})


def estimate_cct_ms(h_val: float, ffr_on: bool) -> float:
    """
    Screening estimate: higher inertia / fast frequency response -> higher CCT.
    """
    base = 120.0
    inertia_factor = (h_val / 4.0)
    ffr_factor = 1.15 if ffr_on else 1.0
    return base * inertia_factor * ffr_factor


# -----------------------------
# 5) VOLTAGE STABILITY (PV CURVE)
# -----------------------------
def pv_curve_screen(
    net_base: pp.pandapowerNet,
    load_idx: int,
    base_p_mw: float,
    base_q_mvar: float,
    steps: int,
    max_scale: float,
) -> pd.DataFrame:
    """
    PV curve by scaling the main load and solving power flow at each step.
    We track the minimum bus voltage and the load-bus voltage (as an indicator).
    """
    net = copy.deepcopy(net_base)
    load_bus = net.load.at[load_idx, "bus"]

    records = []
    scales = np.linspace(1.0, max_scale, steps)

    for s in scales:
        net.load.at[load_idx, "p_mw"] = base_p_mw * s
        net.load.at[load_idx, "q_mvar"] = base_q_mvar * s

        try:
            pp.runpp(net, enforce_q_lims=True, calculate_voltage_angles=True, init="auto")
            vmin = float(net.res_bus.vm_pu.min())
            vload = float(net.res_bus.vm_pu.at[load_bus])
            records.append({"Load scale (×)": s, "P_load (MW)": load_mw * s, "V_min (pu)": vmin, "V_load_bus (pu)": vload, "Converged": True})
        except Exception:
            # Treat non-convergence as beyond stability margin for screening
            records.append({"Load scale (×)": s, "P_load (MW)": load_mw * s, "V_min (pu)": np.nan, "V_load_bus (pu)": np.nan, "Converged": False})

    return pd.DataFrame.from_records(records)


def voltage_sensitivity_proxy(net_base: pp.pandapowerNet) -> dict:
    """
    Proxy sensitivities: small perturbation in P and Q at load bus -> delta V.
    Not a full Jacobian-based V-Q analysis, but it reads as 'physics-aware screening'.
    """
    eps_p = max(5.0, 0.01 * load_mw)  # MW
    eps_q = max(5.0, 0.01 * (load_mw * load_q_factor * 1000)) / 1000  # MVAr approx -> keep consistent

    def solve_with_delta(dp_mw=0.0, dq_mvar=0.0):
        net = copy.deepcopy(net_base)
        li = net.load.index[0]
        b = net.load.at[li, "bus"]
        net.load.at[li, "p_mw"] = load_mw + dp_mw
        net.load.at[li, "q_mvar"] = load_mw * load_q_factor + dq_mvar
        pp.runpp(net, enforce_q_lims=True, calculate_voltage_angles=True, init="auto")
        return float(net.res_bus.vm_pu.at[b]), float(net.res_bus.vm_pu.min())

    # base
    v0_load, v0_min = solve_with_delta(0.0, 0.0)
    # perturb P
    vP_load, _ = solve_with_delta(eps_p, 0.0)
    # perturb Q
    vQ_load, _ = solve_with_delta(0.0, eps_q)

    dV_dP = (vP_load - v0_load) / eps_p  # pu per MW
    dV_dQ = (vQ_load - v0_load) / eps_q  # pu per MVAr
    return {"V_load_base": v0_load, "V_min_base": v0_min, "dVdP_pu_per_MW": dV_dP, "dVdQ_pu_per_MVAr": dV_dQ}


# -----------------------------
# 6) EXECUTION
# -----------------------------
if st.button("🚀 Execute Security + Stability Analysis"):
    with st.status("Solving N-1 power flow + stability screening…", expanded=True) as status:
        try:
            net0 = None
            load_idx = None
            load_base_p = 0.0
            load_base_q = 0.0
            total_generation = 0.0
            total_load = 0.0
            fallback_notice = ""
            data_source_label = DATA_SOURCE_OPTIONS[0]

            import_data_ready = False
            if use_pypsa_export_data and pypsa_export_ready:
                try:
                    net0 = build_net_from_pypsa_export(
                        pypsa_export_path, slack_bus_id=slack_bus_id
                    )
                    data_source_label = DATA_SOURCE_OPTIONS[2]
                    import_data_ready = True
                except Exception as exc:  # pragma: no cover
                    fallback_notice = f"PyPSA export import failed: {exc}"
                    net0 = None
            elif use_stransient_data and stransient_ready:
                try:
                    net0 = build_net_from_stransient(
                        stransient_path, slack_bus_id=slack_bus_id
                    )
                    data_source_label = DATA_SOURCE_OPTIONS[1]
                    import_data_ready = True
                except Exception as exc:  # pragma: no cover
                    fallback_notice = f"STRANSIENT import failed: {exc}"
                    net0 = None

            if net0 is None:
                net0 = build_template_grid(is_n_1=trip_line)
                load_idx = net0.load.index[0]
                load_base_p = load_mw
                load_base_q = load_mw * load_q_factor
                total_generation = float(wind_mw + (hvdc_p if hvdc_enabled else 0))
                total_load = float(load_mw)
            else:
                if import_data_ready:
                    if load_choice:
                        load_mask = net0.load["load_id"] == load_choice
                    else:
                        load_mask = pd.Series(False, index=net0.load.index)
                    if load_mask.any():
                        load_idx = net0.load[load_mask].index[0]
                    else:
                        load_idx = net0.load.index[0]
                else:
                    load_idx = net0.load.index[0]

                load_base_p = float(net0.load.at[load_idx, "p_mw"])
                load_base_q = float(net0.load.at[load_idx, "q_mvar"])
                total_generation = float(net0.sgen["p_mw"].sum())
                total_load = float(net0.load["p_mw"].sum())

            if total_generation == 0:
                total_generation = total_load

            pp.runpp(net0, enforce_q_lims=True, calculate_voltage_angles=True, init="auto")

            if fallback_notice:
                st.warning(fallback_notice + " Running the template grid instead.")

            max_load_pct = float(net0.res_line.loading_percent.max())
            v_min = float(net0.res_bus.vm_pu.min())
            cct = estimate_cct_ms(system_inertia, ffr_enabled)

            dyn_res = simulate_dynamics(
                fault_duration,
                system_inertia,
                ffr_enabled,
                total_generation,
                total_load,
            )
            f_nadir = float(dyn_res["Frequency (Hz)"].min())

            pv_df = pv_curve_screen(
                net0,
                load_idx,
                load_base_p,
                load_base_q,
                pv_steps,
                pv_max_scale,
            )
            sens = voltage_sensitivity_proxy(net0)

            status.update(label="Complete: Security + Stability Screening Generated", state="complete", expanded=False)

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Max line loading", f"{max_load_pct:.1f}%")
            m2.metric("Min bus voltage", f"{v_min:.3f} pu")
            m3.metric("CCT (screening)", f"{cct:.0f} ms")
            m4.metric("Frequency nadir", f"{f_nadir:.2f} Hz")
            m5.metric("dV/dQ (proxy)", f"{sens['dVdQ_pu_per_MVAr']:.4f} pu/MVAr")

            c1, c2 = st.columns(2)

            with c1:
                st.subheader("📍 Steady-state voltage profile (N-1 ready)")
                fig_v = go.Figure()
                colors = ["#e74c3c" if (x < 0.95 or x > 1.05) else "#0d9488" for x in net0.res_bus["vm_pu"]]
                fig_v.add_trace(go.Bar(x=net0.bus["name"], y=net0.res_bus["vm_pu"], marker_color=colors))
                fig_v.add_hline(y=1.05, line_dash="dash", line_color="red")
                fig_v.add_hline(y=0.95, line_dash="dash", line_color="red")
                fig_v.update_layout(yaxis_range=[0.85, 1.15], title="Bus Voltages (pu)")
                st.plotly_chart(fig_v, use_container_width=True)

            with c2:
                st.subheader("🧪 Voltage stability screening (PV curve)")
                pv_plot = pv_df.copy()
                fig_pv = go.Figure()
                fig_pv.add_trace(go.Scatter(
                    x=pv_plot["P_load (MW)"],
                    y=pv_plot["V_load_bus (pu)"],
                    mode="lines+markers",
                    name="V at load bus"
                ))
                fig_pv.add_hline(y=pv_voltage_floor, line_dash="dot", line_color="orange",
                                 annotation_text=f"collapse indicator ~{pv_voltage_floor:.2f} pu")
                fig_pv.update_layout(xaxis_title="Load (MW)", yaxis_title="Voltage (pu)", title="PV curve (screening)")
                st.plotly_chart(fig_pv, use_container_width=True)

                converged = pv_df[pv_df["Converged"] == True].dropna()
                if len(converged) > 0:
                    safe = converged[converged["V_load_bus (pu)"] >= pv_voltage_floor]
                    p_safe = float(safe["P_load (MW)"].max()) if len(safe) else float(converged["P_load (MW)"].min())
                    margin_mw = max(0.0, p_safe - load_base_p)
                    st.caption(f"Loadability margin (screening): **~{margin_mw:.0f} MW** above current load before reaching {pv_voltage_floor:.2f} pu.")
                else:
                    st.caption("PV curve did not converge — indicates severe condition under selected settings.")

            st.subheader("📉 Dynamic screening traces (method illustration)")
            d1, d2 = st.columns(2)
            with d1:
                fig_dyn = px.line(dyn_res, x="Time (s)", y="Rotor Angle (deg)", title="Rotor angle proxy (screening)")
                st.plotly_chart(fig_dyn, use_container_width=True)
            with d2:
                fig_f = px.line(dyn_res, x="Time (s)", y="Frequency (Hz)", title="Frequency response (screening)")
                fig_f.add_hline(y=49.8, line_dash="dot", line_color="orange", annotation_text="primary control threshold (indicative)")
                st.plotly_chart(fig_f, use_container_width=True)

            st.divider()
            st.subheader("🧭 Planning / Engineering Interpretation")
            st.caption(f"Data source: {data_source_label}")

            if fault_duration > cct:
                st.error(f"**Transient stability risk (screening):** clearing time {fault_duration} ms > CCT {cct:.0f} ms.")
                st.info("Mitigation levers: faster clearing, HVDC FFR / synthetic inertia, synchronous condenser, protection coordination.")
            elif max_load_pct > 100:
                st.warning(f"**N-1 thermal violation:** line loading {max_load_pct:.1f}%.")
                st.info("Mitigation levers: re-dispatch, topology, phase shifting, reinforcement.")
            elif v_min < 0.95:
                st.warning("**Steady-state voltage issue:** undervoltage detected.")
                st.info("Mitigation levers: OLTC taps, STATCOM/HVDC Q support, reactive planning, grid strength measures.")
            else:
                st.success("**Screening result:** within typical steady-state limits; stability indicators available below.")

            st.caption("Stability indicators (screening):")
            st.write({
                "V_load_base (pu)": round(sens["V_load_base"], 4),
                "V_min_base (pu)": round(sens["V_min_base"], 4),
                "dV/dP (pu per MW)": round(sens["dVdP_pu_per_MW"], 6),
                "dV/dQ (pu per MVAr)": round(sens["dVdQ_pu_per_MVAr"], 6),
            })

        except Exception as e:
            status.update(label="Simulation failed", state="error", expanded=False)
            st.error(f"Power flow / screening failed: {e}")
            st.info("Try reducing load, increasing reactive support, or disabling N-1 trip to isolate the cause.")


with st.expander("Briefing notes – Methodology & Interpretation", expanded=False):
    st.markdown("""
- **N-1 security**: steady-state constraint checking (thermal + voltage) under credible outage.  
- **Voltage stability screening**: PV curve by load scaling. Interpretable as “how much headroom until voltage collapses.”  
- **Sensitivity proxy**: dV/dQ shows how “stiff” the system is; weak grids need more MVAr per pu recovery.  
- **Dynamic screening**: illustrates method and KPI framing (CCT, frequency nadir).  
- **Full validation**: for real projects, transient & control interaction is validated in **PowerFactory (RMS/EMT)** and/or **PSCAD**, using manufacturer control models.
""")
