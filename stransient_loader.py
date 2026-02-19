from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import pandapower as pp
except ImportError as exc:  # pragma: no cover - fallback for environments without pandapower
    raise ImportError("pandapower is required to build a STRANSIENT grid but is not installed.") from exc


def _safe_per_km(value: float, length_km: float) -> float:
    return float(value) / max(float(length_km), 1e-6)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_net_from_stransient(
    folder: Path,
    slack_bus_id: Optional[str] = None,
    vm_pu: float = 1.02,
) -> pp.pandapowerNet:
    """
    Translate exported STRANSIENT CSVs into a runnable pandapower network.
    """
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"STRANSIENT folder not found: {folder}")

    # Required files
    files = {
        "buses": folder / "stransient_bus.csv",
        "branches": folder / "stransient_branch.csv",
        "generators": folder / "stransient_gen.csv",
        "loads": folder / "stransient_load.csv",
    }

    for name, path in files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {name} export at {path}")

    bus_df = pd.read_csv(files["buses"])
    line_df = pd.read_csv(files["branches"])
    gen_df = pd.read_csv(files["generators"])
    load_df = pd.read_csv(files["loads"])

    net = pp.create_empty_network()
    bus_map: dict[str, int] = {}
    for _, row in bus_df.iterrows():
        bus_id = row["bus_id"]
        bus_map[bus_id] = pp.create_bus(net, vn_kv=row["vn_kv"], name=bus_id)

    slack_bus_id = slack_bus_id or (bus_df["bus_id"].iloc[0] if len(bus_df) else None)
    if slack_bus_id and slack_bus_id in bus_map:
        pp.create_ext_grid(net, bus=bus_map[slack_bus_id], vm_pu=vm_pu, name="STRANSIENT slack")
    elif bus_map:
        first_bus = next(iter(bus_map.values()))
        pp.create_ext_grid(net, bus=first_bus, vm_pu=vm_pu, name="STRANSIENT slack (default)")

    for _, row in gen_df.iterrows():
        bus_name = row["bus"]
        if bus_name not in bus_map:
            continue
        pp.create_sgen(
            net,
            bus=bus_map[bus_name],
            p_mw=row.get("p_max_mw", 0.0),
            q_mvar=row.get("q_max_mvar", 0.0),
            name=row.get("gen_id", f"sgen-{bus_name}"),
        )

    for _, row in load_df.iterrows():
        bus_name = row["bus"]
        if bus_name not in bus_map:
            continue
        pp.create_load(
            net,
            bus=bus_map[bus_name],
            p_mw=row.get("p_mw", 0.0),
            q_mvar=row.get("q_mvar", 0.0),
            name=row.get("load_id", f"load-{bus_name}"),
        )

    for _, row in line_df.iterrows():
        bus0 = row["bus0"]
        bus1 = row["bus1"]
        if bus0 not in bus_map or bus1 not in bus_map:
            continue
        length_km = float(row.get("length", 1.0))
        pp.create_line_from_parameters(
            net,
            bus_map[bus0],
            bus_map[bus1],
            length_km=length_km,
            r_ohm_per_km=_safe_per_km(row.get("r", 0.0), length_km),
            x_ohm_per_km=_safe_per_km(row.get("x", 0.0), length_km),
            c_nf_per_km=float(row.get("c_nf_per_km", 0.0)),
            max_i_ka=float(row.get("i_nom", 1.0)),
            name=row.get("branch_id", f"branch-{bus0}-{bus1}"),
        )

    net.load["load_id"] = net.load["name"]
    net.sgen["gen_id"] = net.sgen["name"]

    return net


def summarize_pypsa_export(folder: Path) -> dict[str, Any]:
    """
    Return PyPSA export metadata so the UI can show default selections.
    """
    folder = Path(folder)
    paths = {
        "buses": folder / "buses.csv",
        "loads": folder / "loads.csv",
    }
    for label, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {label} export at {path}")

    bus_df = pd.read_csv(paths["buses"], usecols=["name", "control"], dtype=str)
    load_df = pd.read_csv(paths["loads"], usecols=["name"], dtype=str)

    slack_candidates = bus_df[bus_df["control"].fillna("").str.lower() == "slack"]
    slack_bus = (
        slack_candidates["name"].iat[0]
        if not slack_candidates.empty
        else (bus_df["name"].iat[0] if not bus_df.empty else None)
    )
    load_id = load_df["name"].iat[0] if not load_df.empty else None

    return {
        "bus_count": len(bus_df),
        "load_count": len(load_df),
        "default_slack": slack_bus,
        "default_load": load_id,
    }


def build_net_from_pypsa_export(
    folder: Path,
    slack_bus_id: Optional[str] = None,
    vm_pu: float = 1.02,
) -> pp.pandapowerNet:
    """
    Translate PyPSA export CSVs into a runnable pandapower network.
    """
    folder = Path(folder)
    files = {
        "buses": folder / "buses.csv",
        "lines": folder / "lines.csv",
        "generators": folder / "generators.csv",
        "loads": folder / "loads.csv",
    }

    for label, path in files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {label} export at {path}")

    bus_df = pd.read_csv(files["buses"])
    gen_df = pd.read_csv(files["generators"])
    load_df = pd.read_csv(files["loads"])
    line_df = pd.read_csv(files["lines"])

    net = pp.create_empty_network()
    bus_map: dict[str, int] = {}
    for _, row in bus_df.iterrows():
        bus_name = str(row["name"])
        bus_map[bus_name] = pp.create_bus(
            net,
            vn_kv=_safe_float(row.get("v_nom", 380.0), 380.0),
            name=bus_name,
        )

    slack_bus_id = slack_bus_id or next(
        (
            str(row["name"])
            for _, row in bus_df.iterrows()
            if str(row.get("control", "")).lower() == "slack"
        ),
        None,
    ) or (bus_df["name"].iat[0] if not bus_df.empty else None)

    if slack_bus_id and slack_bus_id in bus_map:
        pp.create_ext_grid(net, bus=bus_map[slack_bus_id], vm_pu=vm_pu, name="PyPSA slack")
    elif bus_map:
        first_bus = next(iter(bus_map.values()))
        pp.create_ext_grid(net, bus=first_bus, vm_pu=vm_pu, name="PyPSA slack (default)")

    for _, row in gen_df.iterrows():
        bus_name = row["bus"]
        if bus_name not in bus_map:
            continue
        p_nom = _safe_float(row.get("p_nom_opt"), _safe_float(row.get("p_nom")))
        q_mvar = _safe_float(row.get("q_set"))
        if p_nom == 0 and q_mvar == 0:
            continue
        pp.create_sgen(
            net,
            bus=bus_map[bus_name],
            p_mw=p_nom,
            q_mvar=q_mvar,
            name=row.get("name", f"sgen-{bus_name}"),
        )

    for _, row in load_df.iterrows():
        bus_name = row["bus"]
        if bus_name not in bus_map:
            continue
        p_mw = abs(_safe_float(row.get("p_set")))
        q_mvar = abs(_safe_float(row.get("q_set")))
        pp.create_load(
            net,
            bus=bus_map[bus_name],
            p_mw=p_mw,
            q_mvar=q_mvar,
            name=row.get("name", f"load-{bus_name}"),
        )

    for _, row in line_df.iterrows():
        bus0 = row["bus0"]
        bus1 = row["bus1"]
        if bus0 not in bus_map or bus1 not in bus_map:
            continue
        length_km = max(_safe_float(row.get("length"), 1.0), 0.001)
        pp.create_line_from_parameters(
            net,
            bus_map[bus0],
            bus_map[bus1],
            length_km=length_km,
            r_ohm_per_km=_safe_per_km(row.get("r", 0.0), length_km),
            x_ohm_per_km=_safe_per_km(row.get("x", 0.0), length_km),
            c_nf_per_km=_safe_float(row.get("c_nf_per_km")),
            max_i_ka=_safe_float(row.get("i_nom"), 1.0),
            name=row.get("name", f"branch-{bus0}-{bus1}"),
        )

    if not net.load.empty:
        net.load["load_id"] = net.load["name"]
    if not net.sgen.empty:
        net.sgen["gen_id"] = net.sgen["name"]
    if not net.line.empty:
        net.line["line_id"] = net.line["name"]

    return net
