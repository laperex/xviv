# xviv

[![PyPI](https://img.shields.io/pypi/v/xviv)](https://pypi.org/project/xviv/)
[![Python](https://img.shields.io/pypi/pyversions/xviv)](https://pypi.org/project/xviv/)
[![License](https://img.shields.io/pypi/l/xviv)](https://pypi.org/project/xviv/)

FPGA project controller for Vivado. Drives Xilinx Vivado in non-project mode from a single `project.toml` - no GUI clicks, no `.xpr` files, no state drift.

- IP packaging with automatic AXI interface inference
- Block Design creation and wrapper generation
- Synthesis -> placement -> routing -> bitstream in one command
- Standalone simulation via `xvlog` / `xelab` / `xsim` with live waveform reloading
- SystemVerilog interface flattening for Vivado BD compatibility

---

## Requirements

- Python 3.11+
- Xilinx Vivado 2024.1
- `pyslang` - only required for `xviv_wrap_top`

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install xviv
```

---

## Quick Start

```bash
# IP management
xviv ip-config  --ip  <name>
xviv create-ip  --ip  <name>
xviv edit-ip    --ip  <name>

# Block Design
xviv bd-config   --bd  <name>
xviv create-bd   --bd  <name>
xviv edit-bd     --bd  <name>
xviv generate-bd --bd  <name>

# Synthesis
xviv synth-config --top <module>
xviv synthesis    --top <module>
xviv open-dcp     --top <module> [--dcp post_synth,post_place,post_route]

# Simulation
xviv elaborate       --top <sim_top> [--run <time>,all]
xviv open-wdb        --top <sim_top>
xviv reload-wdb      --top <sim_top>
xviv open-snapshot   --top <sim_top>
xviv reload-snapshot --top <sim_top>
```

---

## Documentation

Full documentation is on the [Wiki](https://github.com/laperex/xviv/wiki):

- [Installation & Setup](https://github.com/laperex/xviv/wiki/Installation)
- [project.toml Reference](https://github.com/laperex/xviv/wiki/project.toml-Reference)
- [IP Packaging](https://github.com/laperex/xviv/wiki/IP-Packaging)
- [Block Design](https://github.com/laperex/xviv/wiki/Block-Design)
- [Synthesis & Implementation](https://github.com/laperex/xviv/wiki/Synthesis)
- [Simulation](https://github.com/laperex/xviv/wiki/Simulation)
- [xviv_wrap_top](https://github.com/laperex/xviv/wiki/xviv_wrap_top)
- [Command Reference](https://github.com/laperex/xviv/wiki/Command-Reference)

---
