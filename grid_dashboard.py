import streamlit as st
import pandas as pd
import numpy as np
import warnings

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="50Hertz Digital Twin",
    page_icon="⚡",
    layout="wide"
)

# Suppress warnings for clean UI
warnings.filterwarnings('ignore')

# --- LOGIC CLASS (Adapted for Streamlit) ---
class GridAutomationToolkit:
    """
    Adapted version of the Toolkit that accepts dynamic inputs
    and returns data for the dashboard.
    """
    def __init__(self):
        self.net = None
        self.results = pd.DataFrame()

    def create_grid(self, wind_mw, load_mw, hvdc_enabled):
        try:
            import pandapower as pp
        except ImportError:
            st.error("Pandapower not found. Please install it using `pip install pandapower`.")
            return

        # Create network
        net = pp.create_empty_network()

        # Nodes (Simplified without Geodata)
        b_north = pp.create_bus(net, vn_kv=380, name="Substation North (Wind)")
        b_central = pp.create_bus(net, vn_kv=380, name="Substation Central")
        b_south = pp.create_bus(net, vn_kv=380, name="Substation South (Ind.)")

        # Generation & Load (Dynamic Inputs)
        pp.create_ext_grid(net, bus=b_north, vm_pu=1.02, name="European Interconnection")
        pp.create_sgen(net, bus=b_north, p_mw=wind_mw, q_mvar=0, name="Offshore Wind Park")
        pp.create_load(net, bus=b_south, p_mw=load_mw, q_mvar=load_mw*0.2, name="Industry Cluster")

        # Lines (OHL)
        line_params = {"r_ohm_per_km": 0.03, "x_ohm_per_km": 0.32, "c_nf_per_km": 11.5, "max_i_ka": 2.0}
        pp.create_line_from_parameters(net, b_north, b_central, length_km=150, name="AC Line North-Central A", **line_params)
        pp.create_line_from_parameters(net, b_north, b_central, length_km=150, name="AC Line North-Central B", **line_params)
        pp.create_line_from_parameters(net, b_central, b_south, length_km=200, name="AC Line Central-South", **line_params)

        # HVDC SuedOstLink (Toggleable)
        if hvdc_enabled:
            pp.create_dcline(net, from_bus=b_north, to_bus=b_south, p_mw=1000, loss_mw=20, 
                             loss_percent=0, vm_from_pu=1.02, vm_to_pu=1.02, name="SuedOstLink HVDC")

        self.net = net

    def run_n_minus_1(self):
        # Safety check: if grid wasn't created, return empty
        if self.net is None:
            return pd.DataFrame()

        try:
            import pandapower as pp
        except ImportError:
            return pd.DataFrame()
        
        lines = self.net.line.index
        results_list = []

        # Base Case
        try:
            pp.runpp(self.net)
            base_loading = self.net.res_line.loading_percent.max()
            results_list.append({"Event": "Base Case (All Lines In)", "Status": "OK", "Max Loading %": round(base_loading, 2)})
        except:
             results_list.append({"Event": "Base Case", "Status": "DIVERGED", "Max Loading %": 0})

        # N-1 Loop
        for line_idx in lines:
            line_name = self.net.line.at[line_idx, 'name']
            self.net.line.at[line_idx, 'in_service'] = False # Trip
            
            try:
                pp.runpp(self.net)
                max_loading = self.net.res_line.loading_percent.max()
                
                status = "✅ Secure"
                if max_loading > 100: status = "🔴 CRITICAL"
                elif max_loading > 90: status = "⚠️ Warning"
                
                results_list.append({
                    "Event": f"Trip {line_name}",
                    "Status": status,
                    "Max Loading %": round(max_loading, 2)
                })
            except:
                 # Use np.nan instead of "N/A" string to prevent Arrow serialization errors in Streamlit
                 results_list.append({"Event": f"Trip {line_name}", "Status": "💥 COLLAPSE", "Max Loading %": np.nan})
            
            self.net.line.at[line_idx, 'in_service'] = True # Restore

        return pd.DataFrame(results_list)

# --- DASHBOARD LAYOUT ---
st.title("⚡ 50Hertz Grid Planning Digital Twin")
st.markdown("**Automated N-1 Contingency Analysis & SuedOstLink Integration**")

# Sidebar Controls
st.sidebar.header("Simulation Parameters")
wind_input = st.sidebar.slider("North Wind Generation (MW)", 0, 4000, 2000)
load_input = st.sidebar.slider("South Industrial Load (MW)", 0, 4000, 2300)
hvdc_active = st.sidebar.checkbox("Activate SuedOstLink (HVDC)", value=True)

# Run Simulation Button
if st.button("Run Simulation"):
    with st.spinner('Calculating Power Flow & N-1 Contingencies...'):
        toolkit = GridAutomationToolkit()
        toolkit.create_grid(wind_input, load_input, hvdc_active)
        
        # Stop if grid creation failed (e.g. missing library)
        if toolkit.net is None:
            st.stop()

        df_results = toolkit.run_n_minus_1()
        
        # Metrics
        st.markdown("### 📊 System Health Overview")
        col1, col2, col3 = st.columns(3)
        
        # Calculate stats
        n_critical = len(df_results[df_results['Status'].str.contains("CRITICAL") | df_results['Status'].str.contains("COLLAPSE")])
        n_warning = len(df_results[df_results['Status'].str.contains("Warning")])
        base_load = df_results.iloc[0]['Max Loading %']

        col1.metric("Base Case Loading", f"{base_load}%", delta_color="inverse")
        col2.metric("Critical Contingencies", n_critical, delta_color="inverse")
        col3.metric("Warnings", n_warning, delta_color="inverse")

        # Detailed Table
        st.markdown("### 📋 N-1 Analysis Results")
        
        # Style the dataframe
        def color_status(val):
            color = 'green'
            if 'CRITICAL' in val or 'COLLAPSE' in val: color = 'red'
            elif 'Warning' in val: color = 'orange'
            return f'color: {color}; font-weight: bold'

        # Updated to use width='stretch' as per future API warning
        st.dataframe(df_results.style.applymap(color_status, subset=['Status']), width="stretch")

        # Strategic Advice Logic
        if n_critical > 0:
            st.error("🚨 **STRATEGIC ACTION REQUIRED:** System violates N-1 Security criteria. Immediate Redispatch or Grid Expansion needed.")
        elif n_warning > 0:
            st.warning("⚠️ **NOTICE:** System is secure but operating near thermal limits. Monitor closely.")
        else:
            st.success("✅ **SECURE:** System is fully N-1 compliant.")

else:
    st.info("Adjust parameters in the sidebar and click **Run Simulation**.")