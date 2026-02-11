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

# --- 3. POWER SYSTEM ENGINE ---
def build_50hertz_grid(is_n_1=False):
    net = pp.create_empty_network()
    
    # Substations (Modeled after nodes like Wolmirstedt/Güstrow)
    b_north = pp.create_bus(net, vn_kv=380, name="North Hub (Generation)")
    b_south = pp.create_bus(net, vn_kv=380, name="South Hub (Interconnection)")
    b_regional = pp.create_bus(net, vn_kv=110, name="Regional Hub (Demand)")
    
    # Slack Grid
    pp.create_ext_grid(net, bus=b_north, vm_pu=1.02, name="External Interconnection")
    
    # Transmission Lines (Double-circuit 380kV)
    # 50Hertz standard: AL/St 240/40 or 380/50 conductors
    line_cfg = {"r_ohm_per_km": 0.02, "x_ohm_per_km": 0.25, "c_nf_per_km": 12, "max_i_ka": line_limit_ka}
    pp.create_line_from_parameters(net, b_north, b_south, 60, name="Line L1-380kV", in_service=not is_n_1, **line_cfg)
    pp.create_line_from_parameters(net, b_north, b_south, 60, name="Line L2-380kV", **line_cfg)
    
    # 380/110kV Transformer with OLTC (On-Load Tap Changer)
    # We must define neutral, min, and max positions for the solver to validate the tap_pos
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
        tap_neutral=0,      # The 'center' position
        tap_min=-10,        # Standard German TSO range
        tap_max=10,         # Standard German TSO range
        tap_step_percent=1.25, 
        tap_pos=trafo_tap,  # This now has a valid range to live in
        name="T1-380/110"
    )
    # Generation & Demand
    pp.create_gen(net, bus=b_north, p_mw=wind_mw, vm_pu=1.02, name="Offshore Wind Farm")
    pp.create_load(net, bus=b_regional, p_mw=load_mw, q_mvar=load_mw*0.3, name="Regional Load Cluster")
    
    # Power Electronics Modeling (Job focus: STATCOM & HVDC)
    if hvdc_enabled:
        pp.create_sgen(net, bus=b_regional, p_mw=hvdc_p, q_mvar=hvdc_q, name="HVDC VSC Converter")
    
    if statcom_q != 0:
        pp.create_shunt(net, bus=b_regional, q_mvar=-statcom_q, name="STATCOM Unit")
        
    return net

# --- 4. DASHBOARD EXECUTION ---
if st.button("🚀 Execute Grid Security Analysis"):
    with st.status("Solving Non-Linear Power Flow (Newton-Raphson)...", expanded=True) as status:
        net = build_50hertz_grid(is_n_1=trip_line)
        try:
            pp.runpp(net, enforce_q_lims=True)
            status.update(label="System State Converged!", state="complete", expanded=False)
            
            # --- METRICS ---
            m1, m2, m3, m4 = st.columns(4)
            max_load = net.res_line.loading_percent.max()
            v_min = net.res_bus.vm_pu.min()
            v_max = net.res_bus.vm_pu.max()
            
            m1.metric("Max Asset Loading", f"{max_load:.1f}%", delta=f"{max_load-100:.1f}%" if max_load > 100 else None, delta_color="inverse")
            m2.metric("Minimum Voltage", f"{v_min:.3f} pu")
            m3.metric("Maximum Voltage", f"{v_max:.3f} pu")
            m4.metric("Security State", "CRITICAL" if max_load > 100 or v_min < 0.95 else "SECURE")

            # --- VISUALIZATIONS ---
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("📍 Voltage Stability Profile (VDE 4110)")
                fig_v = go.Figure()
                fig_v.add_trace(go.Bar(x=net.bus['name'], y=net.res_bus['vm_pu'], 
                                       marker_color=['#e74c3c' if x < 0.95 or x > 1.05 else '#2ecc71' for x in net.res_bus['vm_pu']]))
                fig_v.add_hline(y=1.05, line_dash="dash", line_color="red", annotation_text="Limit High")
                fig_v.add_hline(y=0.95, line_dash="dash", line_color="red", annotation_text="Limit Low")
                fig_v.update_layout(yaxis_range=[0.8, 1.2], title="Bus Voltages")
                st.plotly_chart(fig_v, use_container_width=True)

            with c2:
                st.subheader("🔗 Thermal Loading Analysis")
                fig_l = px.bar(net.res_line, x=net.line['name'], y='loading_percent', 
                               color='loading_percent', color_continuous_scale='RdYlGn_r', range_color=[0, 120])
                fig_l.add_hline(y=100, line_dash="dot", line_color="black", annotation_text="Thermal Limit")
                st.plotly_chart(fig_l, use_container_width=True)

            # --- 5. OPERATIONAL ADVISORY ---
            st.divider()
            st.subheader("👨‍🏫 Network Planning Advisory")
            
            # Smart Recommendations
            if max_load > 100:
                st.error(f"**N-1 Thermal Overload:** System is insecure. Suggest increasing HVDC injection or commissioning a second transformer.")
            
            if v_min < 0.95:
                st.warning(f"**Low Voltage Detected:** Minimum bus voltage ({v_min:.3f} pu) is below VDE 4110 threshold. **Action:** Boost STATCOM Reactive Power or adjust Transformer Tap Position.")
            elif v_max > 1.05:
                st.warning(f"**High Voltage Detected:** Minimum bus voltage ({v_max:.3f} pu) exceeds threshold. **Action:** Absorb reactive power via STATCOM.")
            else:
                st.success("Grid operating within statutory limits.")

            # Data Export
            csv = net.res_bus.to_csv().encode('utf-8')
            st.download_button("📥 Export Simulation Data", csv, "50hertz_study.csv", "text/csv")

        except Exception as e:
            status.update(label="Solver Diverged!", state="error")
            st.error(f"**Mathematical Divergence:** The current grid configuration is physically unstable. {e}")

# --- 6. TECHNICAL BRIEFING ---
with st.expander("🎓 Expert Briefing: Grid Integration of Power Electronics"):
    st.markdown("""
    - **STATCOM Role:** Provides rapid, stepless reactive power compensation to stabilize voltage during transients and high load.
    - **HVDC VSC:** Models a Voltage Sourced Converter capable of independent Active (P) and Reactive (Q) power control.
    - **Tap Changer:** Simulates the 'On-Load Tap Changer' (OLTC) on the 380kV side to regulate 110kV hub voltage.
    - **Automation:** This dashboard demonstrates the **Standardization and Automation** of grid studies.
    """)
