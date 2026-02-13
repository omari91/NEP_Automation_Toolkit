import streamlit as st
import pandapower as pp
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

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

with st.sidebar.expander("🌍 Scenario Configuration", expanded=True):
    wind_mw = st.slider("Offshore Wind Infeed (MW)", 0, 1500, 850)
    load_mw = st.slider("Regional HV Demand (MW)", 500, 2500, 1400)
    load_q_factor = st.slider("Load Q/P factor", 0.05, 0.60, 0.20, 0.01)

with st.sidebar.expander("🚀 Power Electronics (STATCOM/HVDC)"):
    hvdc_p = st.slider("HVDC P (MW)", 0, 1000, 600)
    hvdc_q = st.slider("HVDC Q support (MVAr)", -300, 300, 50)
    statcom_q = st.slider("STATCOM Q support (MVAr)", -300, 300, 0)
    hvdc_enabled = st.toggle("Enable HVDC link", value=True)
    ffr_enabled = st.toggle("Enable HVDC FFR (synthetic inertia)", value=True)

with st.sidebar.expander("🛠️ Asset Specs / Limits"):
    st.caption("Transformer OLTC")
    trafo_tap = st.slider("Tap position", -10, 10, 0)
    st.caption("380kV Thermal Limits")
    line_limit_ka = st.number_input("Max current (kA)", 1.0, 5.0, 2.5)

with st.sidebar.expander("🚨 Security Criteria (N-1)"):
    trip_line = st.toggle("Trip L1-380kV Backbone (N-1)", value=False)
    st.caption("N-1: system must remain within limits after one credible outage.")

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
def build_grid(is_n_1: bool) -> pp.pandapowerNet:
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

    return net


# -----------------------------
# 4) DYNAMIC SCREENING (illustrative)
# -----------------------------
def simulate_dynamics(duration_ms: int, h_val: float, ffr_on: bool) -> pd.DataFrame:
    """
    Screening-only. Purpose: show method + interpretability.
    Full EMT / RMS dynamic validation should be done in PSCAD / PowerFactory DSL models.
    """
    time = np.linspace(0, 3.0, 180)
    f_nom = 50.0
    h_eff = h_val + (1.5 if ffr_on else 0.0)

    # crude imbalance proxy (MW -> pu)
    p_accel = (wind_mw + (hvdc_p if hvdc_enabled else 0) - load_mw) / 1000.0
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
def pv_curve_screen(net_base: pp.pandapowerNet, load_bus_name: str, steps: int, max_scale: float) -> pd.DataFrame:
    """
    PV curve by scaling the main load and solving power flow at each step.
    We track the minimum bus voltage and the load-bus voltage (as an indicator).
    """
    net = net_base.deepcopy()
    load_idx = net.load.index[0]  # single load in this toy grid
    load_bus = net.load.at[load_idx, "bus"]

    records = []
    scales = np.linspace(1.0, max_scale, steps)

    for s in scales:
        net.load.at[load_idx, "p_mw"] = load_mw * s
        net.load.at[load_idx, "q_mvar"] = (load_mw * load_q_factor) * s

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
        net = net_base.deepcopy()
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
            net0 = build_grid(is_n_1=trip_line)
            pp.runpp(net0, enforce_q_lims=True, calculate_voltage_angles=True, init="auto")

            # Core KPIs
            max_load_pct = float(net0.res_line.loading_percent.max())
            v_min = float(net0.res_bus.vm_pu.min())
            cct = estimate_cct_ms(system_inertia, ffr_enabled)

            # Dynamic screening traces
            dyn_res = simulate_dynamics(fault_duration, system_inertia, ffr_enabled)
            f_nadir = float(dyn_res["Frequency (Hz)"].min())

            # Voltage stability screening
            pv_df = pv_curve_screen(net0, "Regional Hub (Demand)", pv_steps, pv_max_scale)
            sens = voltage_sensitivity_proxy(net0)

            status.update(label="Complete: Security + Stability Screening Generated", state="complete", expanded=False)

            # ---- Metrics row
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Max line loading", f"{max_load_pct:.1f}%")
            m2.metric("Min bus voltage", f"{v_min:.3f} pu")
            m3.metric("CCT (screening)", f"{cct:.0f} ms")
            m4.metric("Frequency nadir", f"{f_nadir:.2f} Hz")
            m5.metric("dV/dQ (proxy)", f"{sens['dVdQ_pu_per_MVAr']:.4f} pu/MVAr")

            # ---- Charts
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

                # margin estimate
                converged = pv_df[pv_df["Converged"] == True].dropna()
                if len(converged) > 0:
                    # define margin as last point before voltage floor (or last converged)
                    safe = converged[converged["V_load_bus (pu)"] >= pv_voltage_floor]
                    p_safe = float(safe["P_load (MW)"].max()) if len(safe) else float(converged["P_load (MW)"].min())
                    margin_mw = max(0.0, p_safe - load_mw)
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

            # Decision logic
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

            # Sensitivity interpretation
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


with st.expander("Briefing notes (what to say in interviews)"):
    st.markdown("""
- **N-1 security**: steady-state constraint checking (thermal + voltage) under credible outage.  
- **Voltage stability screening**: PV curve by load scaling. Interpretable as “how much headroom until voltage collapses.”  
- **Sensitivity proxy**: dV/dQ shows how “stiff” the system is; weak grids need more MVAr per pu recovery.  
- **Dynamic screening**: illustrates method and KPI framing (CCT, frequency nadir).  
- **Full validation**: for real projects, transient & control interaction is validated in **PowerFactory (RMS/EMT)** and/or **PSCAD**, using manufacturer control models.
""")
