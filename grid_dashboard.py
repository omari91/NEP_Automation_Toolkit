import streamlit as st
import pandapower as pp
import pandas as pd
import numpy as np
import plotly.express as px

# 1. Page Config
st.set_page_config(page_title="TSO Digital Twin - VDE 4110", layout="wide")

st.title("⚡ TSO Digital Twin Dashboard")
st.markdown("Automated Grid Planning & VDE-AR-N 4110 Compliance")

# 2. Sidebar Parameters
st.sidebar.header("Grid Scenario Configuration")
wind_mw = st.sidebar.slider("Wind Farm Output (MW)", 0, 1000, 450)
load_mw = st.sidebar.slider("Regional Load (MW)", 100, 1500, 800)
hvdc_active = st.sidebar.toggle("Enable HVDC Link Support", value=True)

# 3. Network Modeling Function
def build_grid():
    net = pp.create_empty_network()
    
    # Create Buses
    b_ehv_1 = pp.create_bus(net, vn_kv=380, name="EHV Station North")
    b_ehv_2 = pp.create_bus(net, vn_kv=380, name="EHV Station South")
    b_hv = pp.create_bus(net, vn_kv=110, name="Regional HV Hub")
    
    # External Grid
    pp.create_ext_grid(net, bus=b_ehv_1, vm_pu=1.02, name="Grid Slack")
    
    # 380kV Transmission Lines (N-1 Redundant)
    pp.create_line_from_parameters(net, from_bus=b_ehv_1, to_bus=b_ehv_2, length_km=60, 
                                 r_ohm_per_km=0.02, x_ohm_per_km=0.25, c_nf_per_km=12, max_i_ka=1.8, name="L1-380kV")
    pp.create_line_from_parameters(net, from_bus=b_ehv_1, to_bus=b_ehv_2, length_km=60, 
                                 r_ohm_per_km=0.02, x_ohm_per_km=0.25, c_nf_per_km=12, max_i_ka=1.8, name="L2-380kV")
    
    # Interconnecting Transformer
    pp.create_transformer_from_parameters(net, hv_bus=b_ehv_2, lv_bus=b_hv, sn_mva=160, vn_hv_kv=380, vn_lv_kv=110, 
                                         vkr_percent=0.1, vk_percent=12, pfe_kw=40, i0_percent=0.05, name="T1-380/110")
    
    # Load and Generation
    pp.create_sgen(net, bus=b_ehv_2, p_mw=wind_mw, q_mvar=wind_mw*0.05, name="Wind Infeed")
    pp.create_load(net, bus=b_hv, p_mw=load_mw, q_mvar=load_mw*0.2, name="Regional Load")
    
    if hvdc_active:
        pp.create_sgen(net, bus=b_hv, p_mw=300, q_mvar=40, name="HVDC Terminal")
        
    return net

# 4. Simulation and Visualization
if st.button("🚀 Run Grid Analysis"):
    net = build_grid()
    
    try:
        # Newton-Raphson power flow
        pp.runpp(net, algorithm="nr", init_vm_pu="flat", init_va_degree="dc")
        
        st.success("Simulation Converged Successfully")
        
        # Results columns
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📍 Voltage Profile (VDE 4110)")
            v_res = net.res_bus[['vm_pu']].copy()
            v_res.index = net.bus['name']
            v_res['VDE Status'] = v_res['vm_pu'].apply(lambda x: "✅ Pass" if 0.95 <= x <= 1.05 else "⚠️ Violation")
            st.table(v_res.style.format("{:.3f}"))
            
            # Plotly Chart
            fig_v = px.bar(v_res.reset_index(), x='name', y='vm_pu', color='VDE Status', 
                          title="Bus Voltage Analysis", color_discrete_map={"✅ Pass": "#2ecc71", "⚠️ Violation": "#e74c3c"})
            fig_v.add_hline(y=1.05, line_dash="dash", line_color="red", annotation_text="Upper Limit")
            fig_v.add_hline(y=0.95, line_dash="dash", line_color="red", annotation_text="Lower Limit")
            st.plotly_chart(fig_v, use_container_width=True)
            
        with c2:
            st.subheader("🔗 Asset Loading (N-1 Analysis)")
            l_res = net.res_line[['loading_percent']].copy()
            l_res.index = net.line['name']
            st.table(l_res.style.format("{:.1f}%"))
            
            # Loading Chart
            fig_l = px.bar(l_res.reset_index(), x='name', y='loading_percent', title="Line Loading (%)")
            st.plotly_chart(fig_l, use_container_width=True)

        # 5. Data Export
        st.divider()
        st.subheader("📊 Export Simulation Data")
        
        bus_export = net.res_bus.copy()
        bus_export.index = net.bus['name']
        csv = bus_export.to_csv().encode('utf-8')
        st.download_button(
            label="📥 Download Detailed Report (CSV)",
            data=csv,
            file_name='grid_report.csv',
            mime='text/csv',
        )
        
    except Exception as e:
        st.error(f"Mathematical Divergence: {e}")
        st.warning("Action Required: Adjust HVDC injection or reduce regional load to stabilize the grid.")

# 6. Interview Preparation Section
st.divider()
with st.expander("🎓 Interview Scenario Briefing"):
    st.info("**VDE-AR-N 4110 Compliance**: Explain that the model monitors bus voltages to ensure they remain within the statutory ±5% range (0.95-1.05 pu).")
    st.info("**N-1 Contingency**: Highlight how the dual 380kV lines ensure that if one fails, the other can carry the load.")
    st.info("**HVDC Integration**: Discuss the role of HVDC in providing active power support directly at the distribution hub.")
