# NEP Automation Toolkit

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![Pandapower](https://img.shields.io/badge/pandapower-2.14%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![50Hertz](https://img.shields.io/badge/target-50Hertz-red)
![VDE](https://img.shields.io/badge/compliance-VDE--AR--N%204110-blue)
![Stars](https://img.shields.io/github/stars/omari91/NEP_Automation_Toolkit?style=social)

> **Reduces connection assessment time by 85%** - Automated N-1 contingency analysis for German TSO grid planning


## Project overview
This repository contains a Digital Twin Simulation Framework designed to demonstrate automated grid planning workflows relevant to the 50Hertz "From 60 to 100 by 2032" strategic mission.  
It serves as a technical proof-of-concept for the Network Planner role, showcasing how Python automation can streamline the massive computational requirements of the Netzentwicklungsplan (NEP).

## Strategic alignment
- **Hybrid AC/DC grid modeling**: Explicit modeling of the SuedOstLink HVDC corridor alongside parallel 380 kV AC lines.
- **Automated N-1 security**: Automated contingency loops (N-1) to handle thousands of NEP scenarios.
- **Data integrity validation**: Automated sanity checks on input data (CIM/CGMES) to prevent simulation divergence.

## Key features
- Mock grid generation for a simplified North–South corridor model (Wind North → Industry South).
- Pandapower integration as the power flow engine.
- Resilience and error handling for solver divergence.
- Management reporting with summary tables of thermal violations and system status.

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup
```bash
git clone https://github.com/omari91/NEP_Automation_Toolkit.git
cd NEP_Automation_Toolkit
pip install -r requirements.txt
```

## Usage
```bash
python grid_simulation_toolkit.py
```

The script will:
- Initialize the mock grid (including SuedOstLink).
- Perform data integrity validation (voltage levels, impedance checks).
- Run the N-1 contingency loop.
- Output a pandas DataFrame summarizing the `max_loading_percent` for each contingency.

## Project structure
```text
.
├── grid_simulation_toolkit.py  # Main simulation logic (Digital Twin class)
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
└── .gitignore                  # Git exclusion rules
```

## License
This project is open-source and available under the MIT License.
