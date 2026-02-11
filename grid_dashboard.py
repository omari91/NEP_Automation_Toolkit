import streamlit as st
import pandapower as pp
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- 1. PAGE CONFIG & THEMING ---
st.set_page_config(page_title="TSO Digital Twin - VDE 4110", layout="wide")

st.title("⚡ TSO Digital Twin: Operational Security Dashboard")
st.markdown("""
**Author:** Clifford Omari | **Context:** 380kV/110kV Transmission Planning 
This platform evaluates grid stability based on **VDE-AR-N 4110** and **ENTSO-E N-1 Security** standards.
""")

# --- 2. SIDEBAR: SCENARIO & ASSET PARAMETERS ---
st.sidebar.header("🕹️ Grid Control Room")
with st.sidebar.expander("🌍 Scenario Configuration", expanded=True):
    wind_mw = st.slider("Wind Farm Output (MW)", 0, 1500, 600)
    load_mw = st.slider("Regional Load (MW)", 100, 2000, 1100)
    hvdc_p = st.slider("HVDC SuedOstLink Injection (MW)", 0, 1000, 400)
    hvdc_active = st.toggle("Enable HVDC Link", value=True)

with st.sidebar.expander("🚨 Contingency Analysis (N-1)"):
    trip_line = st.toggle("⚠️ Trip Line L1-380kV", value=False)
    st.caption("Simulates a single-circuit failure on the 380kV backbone.")

with st.sidebar.expander("🛠️ Advanced Asset Parameters"):
    st.info("Technical specs for 50Hertz-standard 380kV assets.")
    v_target = st.number_input("Target Voltage (pu)", 0.9, 1.1, 1.02)
    line_limit = st.number_input("Line Limit (kA)", 1.0, 3.0, 1.8)
    trafo_sn = st.number_input("Trafo Rating (MVA)", 100, 500, 160)

# --- 3. BACKEND: THE POWER SYSTEM ENGINE ---
def build_grid(is_n_1=False):
    net = pp.create_empty_network()
    
    # 3.1 Nodes (Substations)
    b1 = pp.create_bus(net, vn_kv=380, name="Substation North (Wind)")
    b2 = pp.create_bus(net, vn_kv=380, name="Substation South (EHV)")
    b3 = pp.create_bus(net, vn_kv=110, name="Regional Hub (110kV)")
    
    # 3.2 Grid Slack (European Interconnection)
    pp.create_ext_grid(net, bus=b1, vm_pu=v_target, name="Slack Bus")
    
    # 3.3 Lines (Redundant 380kV Backbone)
    line_data = {"r_ohm_per_km": 0.02, "x_ohm_per_km": 0.25, "c_nf_per_km": 12, "max_i_ka": line_limit}
    pp.create_line_from_parameters(net, b1, b2, 60, name="Line L1-380kV", in_service=not is_n_1, **line_data)
    pp.create_line_from_parameters(net, b1, b2, 60, name="Line L2-380kV", **line_data)
    
    # 3.4 Transformer (380/110kV Coupling)
    pp.create_transformer_from_parameters(net, hv_bus=b2, lv_bus=b3, sn_mva=trafo_sn, 
                                          vn_hv_kv=380, vn_lv_kv=110, vk_percent=12, vkr_percent=0.1, 
                                          pfe_kw=40, i0_percent=0.05, name="T1-380/110")
    
    # 3.5 Generation & Demand
    # Using 'gen' instead of 'sgen' for active voltage control modeling
    pp.create_gen(net, bus=b1, p_mw=wind_mw, vm_pu=v_target, name="Wind Infeed", 
                  min_p_mw=0, max_p_mw=2000, min_q_mvar=-500, max_q_mvar=500)
    
    pp.create_load(net, bus=b3, p_mw=load_mw, q_mvar=load_mw*0.2, name="Regional Load")
    
    if hvdc_active:
        pp.create_sgen(net, bus=b3, p_mw=hvdc_p, q_mvar=hvdc_p*0.1, name="HVDC Terminal")
        
    return net

# --- 4. EXECUTION & VISUALIZATION ---
if st.button("🚀 Execute Grid Security Analysis"):
    with st.status("Solving Non-Linear Power Flow Equations...", expanded=True) as status:
        net = build_grid(is_n_1=trip_line)
        try:
            # Newton-Raphson Solver with Q-Limit enforcement
            pp.runpp(net, algorithm="nr", init_vm_pu="flat", enforce_q_lims=True)
            status.update(label="System State Converged!", state="complete", expanded=False)
            
            # --- DASHBOARD METRICS ---
            m1, m2, m3 = st.columns(3)
            max_load = net.res_line.loading_percent.max()
            v_min = net.res_bus.vm_pu.min()
            
            m1.metric("Max Line Loading", f"{max_load:.1f}%", delta=f"{max_load-100:.1f}%" if max_load > 100 else None, delta_color="inverse")
            m2.metric("Min Voltage", f"{v_min:.3f} pu", delta=f"{v_min-0.95:.3f}" if v_min < 0.95 else None, delta_color="normal")
            m3.metric("System Health", "CRITICAL" if max_load > 100 or v_min < 0.95 else "SECURE")

            # --- VISUALIZATION: VOLTAGE & LOADING ---
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("📍 Voltage Stability Profile")
                v_res = net.res_bus[['vm_pu']].copy()
                v_res.index = net.bus['name']
                
                fig_v = go.Figure()
                fig_v.add_trace(go.Bar(x=v_res.index, y=v_res['vm_pu'], marker_color=['#e74c3c' if x < 0.95 or x > 1.05 else '#2ecc71' for x in v_res['vm_pu']]))
                fig_v.add_hline(y=1.05, line_dash="dash", line_color="red", annotation_text="Limit High")
                fig_v.add_hline(y=0.95, line_dash="dash", line_color="red", annotation_text="Limit Low")
                fig_v.update_layout(yaxis_range=[0.85, 1.1], title="Bus Voltages (VDE 4110)")
                st.plotly_chart(fig_v, use_container_width=True)

            with c2:
                st.subheader("🔗 Thermal Loading Analysis")
                l_res = net.res_line[['loading_percent']].copy()
                l_res.index = net.line['name']
                
                fig_l = px.bar(l_res.reset_index(), x='name', y='loading_percent', 
                               color='loading_percent', color_continuous_scale='RdYlGn_r', range_color=[0, 120])
                fig_l.add_hline(y=100, line_dash="dot", line_color="black", annotation_text="Thermal Limit")
                st.plotly_chart(fig_l, use_container_width=True)

            # --- 5. REDISPATCH ADVISORY (THE "ENGINEER" FEATURE) ---
            st.divider()
            st.subheader("👨‍🏫 Operational Redispatch Advisory")
            if max_load > 100:
                st.error(f"**N-1 Violation Detected!** Line overloading at {max_load:.1f}%.")
                st.info(f"**Recommended Action:** Reduce Wind Infeed by {int(wind_mw * 0.2)} MW or increase HVDC support to stabilize the corridor.")
            elif v_min < 0.95:
                st.warning(f"**Voltage Instability!** Minimum bus voltage is {v_min:.3f} pu. Consider increasing Reactive Power (Q) from the HVDC converter.")
            else:
                st.success("Grid is compliant with N-1 Security Criteria. No redispatch required.")

            # --- 6. EXPORT ---
            csv = net.res_line.to_csv().encode('utf-8')
            st.download_button("📥 Export Results for NEP Documentation", csv, "grid_report.csv", "text/csv")

        except Exception as e:
            status.update(label="System Collapse!", state="error")
            st.error(f"**Mathematical Divergence:** The grid has reached a bifurcation point (Voltage Collapse). {e}")

# --- 7. TECHNICAL BRIEFING ---
with st.expander("📖 Technical Methodology"):
    st.write("""
    - **Modeling Approach:** Newton-Raphson AC Power Flow.
    - **N-1 Philosophy:** The system is designed to survive the loss of Line L1-380kV by rerouting power through L2.
    - **HVDC Role:** Acts as a 'Virtual Power Plant' at the 110kV hub, providing Active Power (P) and Voltage Support (Q).
    - **VDE-AR-N 4110:** Compliance is verified if all bus voltages remain within the 0.95 - 1.05 pu band.
    """)
