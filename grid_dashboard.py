import logging
from typing import Optional, Tuple

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import warnings

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="TSO Digital Twin",
    page_icon="⚡",
    layout="wide"
)

# Suppress warnings for clean UI
warnings.filterwarnings('ignore')

# --- Logging (lightweight) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GridAutomationToolkit")

# --- CONSTANTS / CONFIG ---
DEFAULT_WIND_MW = 2000
DEFAULT_LOAD_MW = 2300
MAX_GEN_MW = 4000
MAX_LOAD_MW = 4000
HVDC_DEFAULT_P_MW = 1000
HVDC_DEFAULT_LOSS_MW = 20

# --- HELPERS ---
def safe_import_pandapower():
    """Attempt to import pandapower and return module or None."""
    try:
        import pandapower as pp  # type: ignore
        return pp
    except Exception as exc:
        logger.warning("pandapower import failed: %s", exc)
        return None

# --- LOGIC CLASS (Adapted for Streamlit) ---
class GridAutomationToolkit:
    """
    Toolkit for building a simplified grid, running N-1 screening,
    and returning both summary and per-line loading results.
    """

    def __init__(self):
        self.net = None
        self.results = pd.DataFrame()

    def create_grid(self, wind_mw: float, load_mw: float, hvdc_enabled: bool) -> bool:
        """
        Create a simplified 3-bus network with optional HVDC link.
        Returns True on success, False on failure (e.g., missing pandapower).
        """
        pp = safe_import_pandapower()
        if pp is None:
            st.error("Pandapower not found. Please install it using `pip install pandapower`.")
            return False

        # Input validation
        wind_mw = float(max(0, min(wind_mw, MAX_GEN_MW)))
        load_mw = float(max(0, min(load_mw, MAX_LOAD_MW)))

        # Create network
        net = pp.create_empty_network()

        # Buses
        b_north = pp.create_bus(net, vn_kv=380, name="Substation North (Wind)")
        b_central = pp.create_bus(net, vn_kv=380, name="Substation Central")
        b_south = pp.create_bus(net, vn_kv=380, name="Substation South (Ind.)")

        # Generation & Load
        pp.create_ext_grid(net, bus=b_north, vm_pu=1.02, name="European Interconnection")
        pp.create_sgen(net, bus=b_north, p_mw=wind_mw, q_mvar=0, name="Offshore Wind Park")
        pp.create_load(net, bus=b_south, p_mw=load_mw, q_mvar=load_mw * 0.2, name="Industry Cluster")

        # Lines (OHL)
        line_params = {"r_ohm_per_km": 0.03, "x_ohm_per_km": 0.32, "c_nf_per_km": 11.5, "max_i_ka": 2.0}
        pp.create_line_from_parameters(net, b_north, b_central, length_km=150, name="AC Line North-Central A", **line_params)
        pp.create_line_from_parameters(net, b_north, b_central, length_km=150, name="AC Line North-Central B", **line_params)
        pp.create_line_from_parameters(net, b_central, b_south, length_km=200, name="AC Line Central-South", **line_params)

        # HVDC SuedOstLink (Toggleable)
        if hvdc_enabled:
            try:
                pp.create_dcline(
                    net,
                    from_bus=b_north,
                    to_bus=b_south,
                    p_mw=HVDC_DEFAULT_P_MW,
                    loss_mw=HVDC_DEFAULT_LOSS_MW,
                    loss_percent=0,
                    vm_from_pu=1.02,
                    vm_to_pu=1.02,
                    name="SuedOstLink HVDC",
                )
            except Exception as exc:
                # Some pandapower versions may not support dcline creation in the same way
                logger.warning("Failed to create DC line: %s", exc)

        self.net = net
        return True

    def run_n_minus_1(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Run base case and N-1 contingencies.
        Returns:
            df_summary: DataFrame with Event, Status, Max Loading %
            df_per_line: DataFrame indexed by Event with per-line loading %
        """
        if self.net is None:
            logger.info("Network not initialized.")
            return pd.DataFrame(), pd.DataFrame()

        pp = safe_import_pandapower()
        if pp is None:
            return pd.DataFrame(), pd.DataFrame()

        lines = list(self.net.line.index)
        results_list = []
        per_line_records = []

        # Helper to capture per-line loading safely
        def capture_loading(event_name: str):
            try:
                loading_series = self.net.res_line.loading_percent.copy()
                # Convert to dict keyed by line index for later renaming
                per_line_records.append({"Event": event_name, **loading_series.to_dict()})
                return loading_series.max()
            except Exception as exc:
                logger.warning("Failed to capture loading for %s: %s", event_name, exc)
                per_line_records.append({"Event": event_name, **{idx: np.nan for idx in lines}})
                return np.nan

        # Base Case
        try:
            pp.runpp(self.net)
            base_max = capture_loading("Base Case (All Lines In)")
            results_list.append({"Event": "Base Case (All Lines In)", "Status": "OK", "Max Loading %": round(float(base_max), 2)})
        except pp.LoadflowNotConverged as lf_exc:  # type: ignore
            logger.error("Power flow diverged for base case: %s", lf_exc)
            results_list.append({"Event": "Base Case", "Status": "DIVERGED", "Max Loading %": np.nan})
        except Exception as exc:
            logger.exception("Unexpected error during base case run: %s", exc)
            results_list.append({"Event": "Base Case", "Status": "ERROR", "Max Loading %": np.nan})

        # N-1 Loop
        for line_idx in lines:
            line_name = self.net.line.at[line_idx, "name"]
            # Trip the line
            self.net.line.at[line_idx, "in_service"] = False

            try:
                pp.runpp(self.net)
                max_loading = capture_loading(f"Trip {line_name}")

                status = "✅ Secure"
                if pd.isna(max_loading):
                    status = "💥 COLLAPSE"
                else:
                    if max_loading > 100:
                        status = "🔴 CRITICAL"
                    elif max_loading > 90:
                        status = "⚠️ Warning"

                results_list.append({"Event": f"Trip {line_name}", "Status": status, "Max Loading %": round(float(max_loading), 2) if not pd.isna(max_loading) else np.nan})
            except pp.LoadflowNotConverged as lf_exc:  # type: ignore
                logger.warning("Loadflow diverged for trip %s: %s", line_name, lf_exc)
                results_list.append({"Event": f"Trip {line_name}", "Status": "💥 COLLAPSE", "Max Loading %": np.nan})
                per_line_records.append({"Event": f"Trip {line_name}", **{idx: np.nan for idx in lines}})
            except Exception as exc:
                logger.exception("Unexpected error during trip %s: %s", line_name, exc)
                results_list.append({"Event": f"Trip {line_name}", "Status": "ERROR", "Max Loading %": np.nan})
                per_line_records.append({"Event": f"Trip {line_name}", **{idx: np.nan for idx in lines}})
            finally:
                # Restore the line
                self.net.line.at[line_idx, "in_service"] = True

        df_summary = pd.DataFrame(results_list)
        if per_line_records:
            df_per_line = pd.DataFrame(per_line_records).set_index("Event")
            # Rename columns from line indices to line names for readability
            try:
                df_per_line.columns = [self.net.line.at[int(idx), "name"] for idx in df_per_line.columns]
            except Exception:
                # If renaming fails, keep numeric indices
                logger.debug("Could not rename per-line columns to names; keeping indices.")
        else:
            df_per_line = pd.DataFrame()

        # Store results for potential reuse
        self.results = df_summary.copy()
        return df_summary, df_per_line

# --- CACHING / RESOURCE MANAGEMENT ---
@st.cache_resource
def get_toolkit() -> GridAutomationToolkit:
    """Return a toolkit instance cached for the session to reduce rebuilds."""
    return GridAutomationToolkit()

# --- DASHBOARD LAYOUT ---
st.title("⚡ Transmission System Operator (TSO) Grid Planning Digital Twin")
st.markdown("**Automated N-1 Contingency Analysis & HVDC Integration**")

# Sidebar Controls
st.sidebar.header("Simulation Parameters")
wind_input = st.sidebar.slider("North Wind Generation (MW)", 0, MAX_GEN_MW, DEFAULT_WIND_MW)
load_input = st.sidebar.slider("South Industrial Load (MW)", 0, MAX_LOAD_MW, DEFAULT_LOAD_MW)
hvdc_active = st.sidebar.checkbox("Activate SuedOstLink (HVDC)", value=True)

# Run Simulation Button
if st.button("Run Simulation"):
    with st.spinner("Calculating Power Flow & N-1 Contingencies..."):
        toolkit = get_toolkit()
        created = toolkit.create_grid(wind_input, load_input, hvdc_active)

        # Stop if grid creation failed (e.g. missing library)
        if not created or toolkit.net is None:
            st.stop()

        df_results, df_per_line = toolkit.run_n_minus_1()

        # Metrics
        st.markdown("### 📊 System Health Overview")
        col1, col2, col3 = st.columns(3)

        # Defensive checks for empty results
        if df_results.empty:
            st.warning("No results available. Check pandapower installation and input parameters.")
            st.stop()

        # Calculate stats
        n_critical = int(df_results["Status"].str.contains("CRITICAL").sum() + df_results["Status"].str.contains("COLLAPSE").sum())
        n_warning = int(df_results["Status"].str.contains("Warning").sum())
        base_load = df_results.iloc[0]["Max Loading %"] if not df_results.empty else np.nan

        col1.metric("Base Case Loading", f"{base_load}%", delta_color="inverse")
        col2.metric("Critical Contingencies", n_critical, delta_color="inverse")
        col3.metric("Warnings", n_warning, delta_color="inverse")

        # Detailed Table
        st.markdown("### 📋 N-1 Analysis Results")

        # Style the dataframe
        def color_status(val: str) -> str:
            color = "green"
            if "CRITICAL" in val or "COLLAPSE" in val:
                color = "red"
            elif "Warning" in val:
                color = "orange"
            return f"color: {color}; font-weight: bold"

        st.dataframe(df_results.style.applymap(color_status, subset=["Status"]), width="stretch")

        # --- VISUALIZATIONS ---
        # Bar chart: Max Loading % per event
        try:
            plot_df = df_results.dropna(subset=["Max Loading %"]).copy()
            plot_df["Max Loading %"] = pd.to_numeric(plot_df["Max Loading %"], errors="coerce")
            if not plot_df.empty:
                fig = px.bar(
                    plot_df,
                    x="Event",
                    y="Max Loading %",
                    color="Status",
                    color_discrete_map={
                        "✅ Secure": "green",
                        "⚠️ Warning": "orange",
                        "🔴 CRITICAL": "red",
                        "💥 COLLAPSE": "darkred",
                        "OK": "green",
                        "DIVERGED": "gray",
                        "ERROR": "gray",
                    },
                    title="N-1 Contingency Max Line Loading",
                    labels={"Max Loading %": "Max Loading (%)", "Event": ""},
                )
                fig.update_layout(xaxis_tickangle=-45, margin=dict(t=50, b=150))
                st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            logger.exception("Failed to render bar chart: %s", exc)

        # Heatmap: per-line loading across events (if available)
        if not df_per_line.empty:
            try:
                # Transpose so lines are rows and events are columns for readability
                heatmap_df = df_per_line.T
                fig2 = px.imshow(
                    heatmap_df,
                    labels=dict(x="Event", y="Line", color="Loading %"),
                    x=heatmap_df.columns,
                    y=heatmap_df.index,
                    aspect="auto",
                    color_continuous_scale="RdYlGn_r",
                    title="Per-Line Loading Percent across N-1 Events",
                )
                fig2.update_layout(xaxis_tickangle=-45, margin=dict(t=50, b=150))
                st.plotly_chart(fig2, use_container_width=True)
            except Exception as exc:
                logger.exception("Failed to render heatmap: %s", exc)

        # Strategic Advice Logic
        if n_critical > 0:
            st.error("🚨 **STRATEGIC ACTION REQUIRED:** System violates N-1 Security criteria. Immediate Redispatch or Grid Expansion needed.")
        elif n_warning > 0:
            st.warning("⚠️ **NOTICE:** System is secure but operating near thermal limits. Monitor closely.")
        else:
            st.success("✅ **SECURE:** System is fully N-1 compliant.")
else:
    st.info("Adjust parameters in the sidebar and click **Run Simulation**.")
