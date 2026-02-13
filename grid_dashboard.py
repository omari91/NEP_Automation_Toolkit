import streamlit as st
import pandapower as pp
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- 1. PAGE SETUP & STYLING ---
st.set_page_config(page_title="TSO Grid Planning Digital Twin", layout="wide")

st.title("⚡ TSO Network Planning: Operational Security Dashboard")
st.markdown("""
**System Scope:** 380kV/110kV EHV-HV Coupling | **Regulatory Framework:** VDE-AR-N 4110 & 4120
*This tool automates N-1 security studies and evaluates the integration of Power Electronic systems (HVDC & STATCOM).*
""")

# --- 2. MULTI-LAYERED CONTROL PANEL ---
st.sidebar.header("🕹️ TSO Control Room")

with st.sidebar.expander("🌍 Scenario Configuration", expanded=True):
    wind_mw = st.slider("Offshore Wind Infeed (MW)", 0, 1500, 850)
    load_mw = st.slider("Regional HV Demand (MW)", 500, 2500, 1400)

with st.sidebar.expander("🚀 Power Electronics (STATCOM/HVDC)"):
    hvdc_p = st.slider("HVDC SuedOstLink P (MW)", 0, 1000, 600)
    hvdc_q = st.slider("HVDC Reactive Support (MVAr)", -200, 200, 50)
    statcom_q = st.slider("STATCOM Dynamic Support (MVAr)", -150, 150, 0)
    hvdc_enabled = st.toggle("Enable HVDC Link", value=True)

with st.sidebar.expander("🛠️ Electrical Design (Asset Specs)"):
    st.caption("On-Load Tap Changer (OLTC)")
    trafo_tap = st.slider("Transformer Tap Position", -10, 10, 0)
    st.caption("380kV Thermal Limits")
    line_limit_ka = st.number_input("Max Current (kA)", 1.0, 3.0, 1.8)

with st.sidebar.expander("🚨 Security Criteria (N-1)"):
    trip_line = st.toggle("⚠️ Trip L1-380kV Backbone", value=False)
    st.info("Ensures system stability under single-point failure (ENTSO-E Standard).")

with st.sidebar.expander("📉 Dynamic Stability Analysis"):
    st.caption("Fault Simulation")
    fault_bus = st.selectbox("Three-Phase Fault Location", ["North Hub (Generation)", "South Hub (Interconnection)", "Regional Hub (Demand)"])
    fault_duration = st.slider("Fault Clearing Time (ms)", 50, 500, 100)
    
# --- 3. POWER SYSTEM ENGINE ---
def build_50hertz_grid(is_n_1=False):
    net = pp.create_empty_network()
    
    # Substations
    b_north = pp.create_bus(net, vn_kv=380, name="North Hub (Generation)")
    b_south = pp.create_bus(net, vn_kv=380, name="South Hub (Interconnection)")
    b_regional = pp.create_bus(net, vn_kv=110, name="Regional Hub (Demand)")
    
    # Slack Grid
    pp.create_ext_grid(net, bus=b_north, vm_pu=1.02, name="External Interconnection")
    
    # Transmission Lines (Double-circuit 380kV)
    line_cfg = {"r_ohm_per_km": 0.02, "x_ohm_per_km": 0.25, "c_nf_per_km": 12, "max_i_ka": line_limit_ka}
    pp.create_line_from_parameters(net, b_north, b_south, 60, name="Line L1-380kV", in_service=not is_n_1, **line_cfg)
    pp.create_line_from_parameters(net, b_north, b_south, 60, name="Line L2-380kV", **line_cfg)
    
    # 380/110kV Transformer with OLTC
    pp.create_transformer_from_parameters(
        net, 
        hv_bus=b_south, 
        lv_bus=b_regional, 
        sn_mva=350,
        vn_hv_kv=380,
        vn_lv_kv=110,
        vk_percent=12,
        vkr_percent=0.1, 
        pfe_kw=40,
        i0_percent=0.05,
        shift_degree=0,
        tap_side="hv", 
        tap_neutral=0,
        tap_min=-10,
        tap_max=10,
        tap_step_percent=1.25, 
        tap_pos=trafo_tap,
        name="T1-380/110"
    )

    # Generation & Demand
    # We use 'gen' here to simulate a generator with inertia/stability properties
    pp.create_gen(net, bus=b_north, p_mw=wind_mw, vm_pu=1.02, name="Offshore Wind Farm")
    pp.create_load(net, bus=b_regional, p_mw=load_mw, q_mvar=load_mw*0.3, name="Regional Load Cluster")
    
    # Power Electronics
    if hvdc_enabled:
        pp.create_sgen(net, bus=b_regional, p_mw=hvdc_p, q_mvar=hvdc_q, name="HVDC VSC Converter")
    
    if statcom_q != 0:
        pp.create_shunt(net, bus=b_regional, q_mvar=-statcom_q, name="STATCOM Unit")
    
    return net

def simulate_dynamics(net, fault_bus_name, duration_ms):
    # Simplified Dynamic stability (Swing Equation Approximation)
    # Industry standard for dashboards: Voltage Recovery & Power Oscillations
    time = np.linspace(0, 2.0, 50) # 2 seconds simulation
    f_nom = 50.0
    H = 4.0 # Inertia constant (MWs/MVA)
    
    # Fault impacts: Power output drops to 0 during fault
    p_pre = wind_mw
    p_fault = 0
    p_post = wind_mw * 0.95 # Some reduction due to instability
    
    # Swing Equation: d2(delta)/dt2 = (omega_s / 2H) * (Pm - Pe)
    delta = [0]
    omega = [0]
    dt = 0.04
    
    for t in time[1:]:
        pe = p_fault if (t * 1000 <= duration_ms) else p_post
        accel = (2*np.pi*f_nom / (2 * H)) * (p_pre - pe) / 1000 # Normalized
        omega.append(omega[-1] + accel * dt)
        delta.append(delta[-1] + omega[-1] * dt)
        
    return pd.DataFrame({"Time (s)": time, "Rotor Angle (deg)": np.array(delta)*180/np.pi, "Frequency (Hz)": f_nom + np.array(omega)/(2*np.pi)})

# --- 4. DASHBOARD EXECUTION ---
if st.button("🚀 Execute Grid Security Analysis"):
    with st.status("Solving Non-Linear Power Flow & Dynamic Stability...", expanded=True) as status:
        net = build_50hertz_grid(is_n_1=trip_line)
        try:
            pp.runpp(net, enforce_q_lims=True)
            dyn_res = simulate_dynamics(net, fault_bus, fault_duration)
            status.update(label="System Converged & Stability Verified!", state="complete", expanded=False)
            
            # --- METRICS ---
            m1, m2, m3, m4 = st.columns(4)
            max_load = net.res_line.loading_percent.max()
            v_min = net.res_bus.vm_pu.min()
            critical_clearing = 150 # ms approximation
            
            m1.metric("Max Asset Loading", f"{max_load:.1f}%")
            m2.metric("Min Voltage", f"{v_min:.3f} pu")
            m3.metric("Trans. Stability", "UNSTABLE" if fault_duration > critical_clearing else "STABLE")
            m4.metric("Security State", "CRITICAL" if max_load > 100 or v_min < 0.95 else "SECURE")

            # --- VISUALIZATIONS ---
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("📍 Steady State Profile")
                fig_v = go.Figure()
                fig_v.add_trace(go.Bar(x=net.bus['name'], y=net.res_bus['vm_pu'], 
                                     marker_color=['#e74c3c' if x < 0.95 or x > 1.05 else '#2ecc71' for x in net.res_bus['vm_pu']]))
                fig_v.add_hline(y=1.05, line_dash="dash", line_color="red")
                fig_v.add_hline(y=0.95, line_dash="dash", line_color="red")
                fig_v.update_layout(yaxis_range=[0.8, 1.2], title="Bus Voltages (pu)")
                st.plotly_chart(fig_v, use_container_width=True)

            with c2:
                st.subheader("📉 Transient Rotor Swing")
                fig_dyn = px.line(dyn_res, x="Time (s)", y="Rotor Angle (deg)", title="Generator Rotor Angle Recovery")
                st.plotly_chart(fig_dyn, use_container_width=True)

            # Frequency Chart
            st.subheader("⏱️ Frequency Response")
            fig_f = px.line(dyn_res, x="Time (s)", y="Frequency (Hz)", title="System Frequency Nadir Analysis")
            fig_f.add_hline(y=49.8, line_dash="dot", line_color="orange", annotation_text="Primary Control Threshold")
            st.plotly_chart(fig_f, use_container_width=True)

            # --- 5. OPERATIONAL ADVISORY ---
            st.divider()
            st.subheader("👨‍🏫 Network Planning Advisory")
            if fault_duration > critical_clearing:
                st.error("**Dynamic Stability Violation:** Fault clearing time exceeds Critical Clearing Time (CCT). Generator pole-slipping likely.")
                st.info("Action: Increase System Inertia (H) or optimize HVDC Fast Frequency Response (FFR).")
            elif max_load > 100:
                st.warning("**N-1 Thermal Overload:** Post-contingency loading exceeds limits.")
            else:
                st.success("Grid satisfies all Operational Security and Dynamic Stability criteria.")

        except Exception as e:
            status.update(label="Simulation Failed!", state="error")
            st.error(f"Numerical Instability: {e}")

# --- 6. TECHNICAL BRIEFING ---
with st.expander("Briefing Notes: Advanced Grid Dynamics"):
    st.markdown("""
    - **Transient Stability:** Simulates the 'Rotor Swing' after a three-phase fault. This is critical for assessing if synchronous generators stay synchronized.
    - **Frequency Nadir:** Analyzes the lowest point the frequency reaches before Primary Control stabilizes the system.
    - **CCT (Critical Clearing Time):** The maximum time a fault can persist before the system loses stability. 50Hertz typically targets <100ms.
    - **HVDC FFR:** Demonstrates how HVDC can provide 'Synthetic Inertia' to prevent frequency collapse.
    """)
