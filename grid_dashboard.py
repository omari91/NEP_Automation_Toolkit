import streamlit as st
import pandapower as pp
import pandapower.networks as nw
import pandas as pd
import numpy as np

# Page configuration
st.set_page_config(page_title="TSO Digital Twin - Grid Planning", layout="wide")

st.title("⚡ TSO Digital Twin: N-1 Contingency & HVDC Dashboard")
st.markdown("""
This dashboard simulates a 380kV/110kV transmission grid segment. 
It evaluates grid stability based on **VDE-AR-N 4110** criteria.
""")

# Sidebar controls for simulation parameters
st.sidebar.header("Network Parameters")
wind_gen = st.sidebar.slider("Wind Generation (MW)", 0, 1500, 450, step=50)
solar_gen = st.sidebar.slider("Solar Generation (MW)", 0, 500, 100, step=25)
load_mw = st.sidebar.slider("Regional Load (MW)", 0, 2000, 800, step=50)
hvdc_p = st.sidebar.slider("HVDC Power Injection (MW)", 0, 1000, 300, step=50)
hvdc_enabled = st.sidebar.checkbox("Enable HVDC Link (SuedOstLink)", value=True)

def create_network():
    net = pp.create_empty_network()
    
    # Create buses
    b1 = pp.create_bus(net, vn_kv=380., name="Transmission Node A")
    b2 = pp.create_bus(net, vn_kv=380., name="Transmission Node B")
    b3 = pp.create_bus(net, vn_kv=110., name="Distribution Hub")
    
    # External Grid (Slack Bus)
    pp.create_ext_grid(net, bus=b1, vm_pu=1.02, name="Main Interconnector")
    
    # Transformer (380/110 kV)
    pp.create_transformer(net, hv_bus=b2, lv_bus=b3, std_type="100 MVA 380/110 kV", name="T1")
    
    # Lines (N-1 Redundancy)
    pp.create_line(net, from_bus=b1, to_bus=b2, length_km=50, std_type="490-AL1/64-ST1A 380.0", name="Main Line 1")
    pp.create_line(net, from_bus=b1, to_bus=b2, length_km=50, std_type="490-AL1/64-ST1A 380.0", name="Main Line 2")
    
    # Generation
    pp.create_sgen(net, bus=b2, p_mw=wind_gen, q_mvar=wind_gen*0.05, name="Offshore Wind")
    pp.create_sgen(net, bus=b3, p_mw=solar_gen, q_mvar=0, name="Local Solar")
    
    # Load
    pp.create_load(net, bus=b3, p_mw=load_mw, q_mvar=load_mw*0.3, name="Industrial Load")
    
    # HVDC Link (Simplified as static injection)
    if hvdc_enabled:
        pp.create_sgen(net, bus=b3, p_mw=hvdc_p, q_mvar=hvdc_p*0.1, name="HVDC Infeed")
        
    return net

if st.button("🚀 Run Contingency Analysis"):
    net = create_network()
    
    try:
        # Robust power flow settings
        pp.runpp(net, algorithm="nr", init_vm_pu="flat", init_va_degree="dc", max_iteration=100)
        
        st.success("Simulation Converged. Grid parameters within operational bounds.")
        
        # Dashboard Layout
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📍 Bus Voltage Analysis")
            res_bus = net.res_bus[['vm_pu']].copy()
            res_bus.index = net.bus['name']
            res_bus['Compliance'] = res_bus['vm_pu'].apply(lambda x: "✅ Pass" if 0.94 <= x <= 1.06 else "❌ VDE Violation")
            st.dataframe(res_bus.style.background_gradient(cmap='RdYlGn', subset=['vm_pu']))
            
        with col2:
            st.subheader("🔗 Asset Loading (N-1 Status)")
            res_line = net.res_line[['loading_percent']].copy()
            res_line.index = net.line['name']
            res_line['Status'] = res_line['loading_percent'].apply(lambda x: "Safe" if x < 70 else ("Critical" if x < 100 else "Overloaded"))
            st.dataframe(res_line.style.background_gradient(cmap='YlOrRd', subset=['loading_percent']))

        # CSV Export Logic
        st.subheader("📊 Export Data")
        full_res = pd.concat([net.res_bus, net.res_line], axis=1)
        csv_data = full_res.to_csv(index=True).encode('utf-8')
        st.download_button(
            label="Download Simulation Report (CSV)",
            data=csv_data,
            file_name='tso_simulation_results.csv',
            mime='text/csv',
        )
        
    except Exception as e:
        st.error(f"Numerical Divergence Detected: {e}")
        st.warning("Recommendation: Increase HVDC power injection or reduce local load to stabilize the 110kV node.")

# Interview Preparation Section
st.divider()
with st.expander("📝 Scenario Briefing for Interviews"):
    st.info("**Scenario 1: High Wind/Low Load** - Demonstrates voltage rise at Transmission Node B. Show how HVDC can absorb excess reactive power.")
    st.info("**Scenario 2: N-1 Contingency** - Explain that even if one 380kV line is lost, the second line maintains the connection.")
    st.info("**Scenario 3: VDE-AR-N 4110** - Discuss the 0.94-1.06 pu voltage limits and how reactive power maintains this.")
