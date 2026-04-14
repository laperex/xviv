# xviv

[![PyPI](https://img.shields.io/pypi/v/xviv)](https://pypi.org/project/xviv/)
[![Python](https://img.shields.io/pypi/pyversions/xviv)](https://pypi.org/project/xviv/)
[![License](https://img.shields.io/pypi/l/xviv)](https://pypi.org/project/xviv/)

**A Python-based CLI controller for Xilinx Vivado and Vitis workflows.**

`xviv` drives Vivado in non-project (batch) mode via a single `project.toml` configuration file and a set of TCL scripts. It covers the full FPGA development lifecycle: IP packaging, Block Design, synthesis, implementation, bitstream generation, BSP/platform creation, and embedded application build/program.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Project Configuration](#project-configuration)
- [Commands](#commands)
  - [IP Management](#ip-management)
  - [Block Design](#block-design)
  - [Synthesis](#synthesis)
  - [Simulation](#simulation)
  - [Embedded (Vitis / xsct)](#embedded-vitis--xsct)
  - [Programming](#programming)
- [Hooks System](#hooks-system)
- [Out-of-Context (OOC) Synthesis](#out-of-context-ooc-synthesis)
- [Interface Inference Tool (xviv_infer)](#interface-inference-tool-xviv_infer)
- [Wrapper Generator](#wrapper-generator)
- [Shell Completion](#shell-completion)
- [Directory Layout](#directory-layout)

---

## Features

- **Single config file** — all project settings live in `project.toml`
- **Non-project / batch mode** — no `.xpr` file, no stale GUI state
- **IP packaging** — scaffold, edit, and version custom IPs with a hooks API
- **Block Design** — create, edit, generate, and export BDs as re-runnable TCL
- **OOC synthesis** — out-of-context per-IP synthesis with automatic DCP caching and incremental builds
- **Synthesis -> Implementation -> Bitstream** — single command with optional reports and netlists
- **Git-tagged bitstreams** — SHA embeds in USR_ACCESS for traceability
- **Embedded workflow** — BSP generation, app scaffolding, build, and JTAG program via `xsct`
- **xsim integration** — compile, elaborate, run, and live-reload waveforms via a FIFO control channel
- **Shell completion** — `argcomplete`-powered tab completion for all commands and arguments
- **Interface inference** — `pyslang`-based SV parser auto-generates Vivado IP-XACT TCL for bus interface registration

---

## Installation

```bash
pip install xviv
```

Or from source:

```bash
git clone https://github.com/laperex/xviv
cd xviv
pip install -e .
```

**Requirements**

| Dependency | Notes |
|---|---|
| Python ≥ 3.11 | Uses `tomllib`, `match` statements |
| Vivado 2024.1 | Tested version; 2023.x likely works |
| Vitis 2024.1 | Required only for embedded (`xsct`) commands |
| `pyslang` | Required for `wrapper` and `inference` features |
| `argcomplete` | Shell completion |

Activate shell completion once:

```bash
activate-global-python-argcomplete
# or for a single shell session:
eval "$(register-python-argcomplete xviv)"
```

---

## Project Configuration

All project settings are declared in `project.toml`, placed at the root of your project. `xviv` automatically `chdir`s to the directory containing the config file before any command runs.

```toml
# ── FPGA target ────────────────────────────────────────────────
[fpga]
part       = "xc7z020clg400-1"
board_part = "tul.com.tw:pynq-z2:part0:1.0"
board_repo = "/path/to/board_files"   # optional

# Named targets (select with  fpga = "artix7"  in a [[synthesis]] entry)
[fpga.artix7]
part = "xc7a35tcpg236-1"

# ── Tool paths ─────────────────────────────────────────────────
[vivado]
path        = "/opt/Xilinx/Vivado/2024.1"
mode        = "batch"        # batch | tcl
max_threads = 8
hw_server   = "localhost:3121"

[vitis]
path = "/opt/Xilinx/Vitis/2024.1"

# ── Build output directories ───────────────────────────────────
[build]
dir         = "build"
ip_repo     = "build/ip"
bd_dir      = "build/bd"
wrapper_dir = "build/wrapper"

# ── Global RTL sources (applied to every top-level synthesis) ──
[sources]
rtl = ["srcs/rtl/**/*.sv", "srcs/rtl/**/*.v"]
xdc = ["srcs/xdc/*.xdc"]
sim = ["srcs/sim/**/*.sv"]

# ── Custom IPs ─────────────────────────────────────────────────
[[ip]]
name    = "my_accelerator"
vendor  = "myorg.com"
library = "user"
version = "1.0"
top     = "my_accelerator"
rtl     = ["srcs/ip/my_accelerator/**/*.sv"]

[[ip]]
name           = "axi_wrapper"
top            = "axi_wrapper"
rtl            = ["srcs/ip/axi_wrapper/**/*.sv"]
create_wrapper = true   # auto-generate SV wrapper flattening interfaces

# ── Block Designs ──────────────────────────────────────────────
[[bd]]
name       = "system"
xdc        = ["srcs/xdc/system.xdc"]
export_tcl = "scripts/bd/system.tcl"

# ── Top-level synthesis runs ───────────────────────────────────
[[synthesis]]
top              = "system_wrapper"
fpga             = "pynqz2"          # selects [fpga.pynqz2] target
xdc              = ["srcs/xdc/system.xdc"]
report_synth     = true
report_place     = true
report_route     = true
generate_netlist = false

[[synthesis]]
top             = "my_module"
rtl             = ["srcs/rtl/my_module.sv"]
out_of_context  = true

# ── Platform / BSP ─────────────────────────────────────────────
[[platform]]
name      = "pynqz2_bsp"
cpu       = "ps7_cortexa9_0"
os        = "standalone"
synth_top = "system_wrapper"   # derive XSA from a synthesis run

# ── Embedded applications ──────────────────────────────────────
[[app]]
name     = "hello_world"
platform = "pynqz2_bsp"
template = "hello_world"
src_dir  = "srcs/sw/hello_world"
```

---

## Commands

All commands accept `--config <path>` (default: `project.toml`) and `--log-file <path>`.

### IP Management

#### `xviv create --ip <name>`

Scaffolds a new custom IP in the IP repository (`build/ip/`).

1. Reads `[[ip]]` config for `<name>`.
2. If `create_wrapper = true`, parses your RTL with `pyslang` and auto-generates a SystemVerilog wrapper that flattens interface ports.
3. Launches Vivado, creates the IP skeleton, strips the default AXI-Lite scaffold, adds your RTL, infers bus interfaces (AXI-Stream, AXI-MM), exposes HDL parameters in the GUI, and saves `component.xml`.

```bash
xviv create --ip my_accelerator
```

Hooks file is auto-generated at `scripts/ip/my_accelerator_1.0.tcl` on first run. Customize it to control interface inference, parameter layout, and memory maps.

#### `xviv edit --ip <name>`

Opens an existing IP in the Vivado IP Packager GUI for interactive editing.

```bash
xviv edit --ip my_accelerator
```

#### `xviv config --ip <name>`

Generates a starter hooks TCL file for the IP without launching Vivado.

```bash
xviv config --ip my_accelerator
# Edit: scripts/ip/my_accelerator_1.0.tcl
```

---

### Block Design

#### `xviv create --bd <name>`

Creates a new Block Design. If a hooks file with an exported BD TCL exists, the BD is recreated automatically. Otherwise Vivado opens the GUI for interactive design.

```bash
xviv create --bd system
```

#### `xviv edit --bd <name>`

Opens an existing BD in the Vivado GUI for interactive editing.

```bash
xviv edit --bd system
```

#### `xviv generate --bd <name>`

Generates all BD output products (synthesis, simulation, implementation targets) and copies the BD wrapper Verilog to `build/wrapper/`.

```bash
xviv generate --bd system
```

#### `xviv export --bd <name>`

Exports the BD as a versioned, re-runnable TCL script tagged with the current git SHA. A symlink `scripts/bd/system.tcl` always points to the latest export.

```bash
xviv export --bd system
# Exported : scripts/bd/system_abc1234.tcl
# Symlink  : scripts/bd/system.tcl -> system_abc1234.tcl
```

#### `xviv config --bd <name>`

Generates a starter hooks file that sources the exported TCL on `create-bd`, enabling fully automated BD recreation from version control.

```bash
xviv config --bd system
```

---

### Synthesis

#### `xviv synth --top <module>`

Runs the complete flow: Synthesis -> Placement -> Routing -> Bitstream + XSA.

```bash
xviv synth --top system_wrapper
```

Output in `build/synth/system_wrapper/`:

| File | Description |
|---|---|
| `post_synth.dcp` | Post-synthesis checkpoint |
| `post_place.dcp` | Post-placement checkpoint |
| `post_route.dcp` | Post-routing checkpoint |
| `system_wrapper_abc1234.bit` | Tagged bitstream |
| `system_wrapper_abc1234.xsa` | Hardware platform for Vitis |
| `system_wrapper.bit` -> symlink | Always points to latest |
| `build.json` | Build manifest (Vivado version, part, SHA, timing) |

#### `xviv synth --bd <name>`

Synthesises a BD wrapper. With `--ooc-run`, performs per-IP out-of-context synthesis first (see [OOC Synthesis](#out-of-context-ooc-synthesis)).

```bash
xviv synth --bd system
xviv synth --bd system --ooc-run
```

#### `xviv open --dcp post_synth --top system_wrapper`

Opens a saved checkpoint in the Vivado GUI for inspection.

```bash
xviv open --dcp post_route --top system_wrapper
```

---

### Simulation

#### `xviv elab --top <sim_top> [--run <time>]`

Compiles (`xvlog`), elaborates (`xelab`), and optionally runs (`xsim`) a simulation.

```bash
xviv elab --top tb_my_module --run 1000ns
```

#### `xviv open --snapshot --top <sim_top>`

Opens the simulation snapshot in the xsim GUI with a live FIFO control channel.

```bash
xviv open --snapshot --top tb_my_module
```

#### `xviv reload --snapshot --top <sim_top>`

Re-runs the simulation and reloads the waveform without closing xsim.

```bash
xviv reload --snapshot --top tb_my_module
```

#### `xviv open --wdb --top <sim_top>` / `xviv reload --wdb --top <sim_top>`

Open or reload a static WDB waveform file.

---

### Embedded (Vitis / xsct)

#### `xviv create --platform <name>`

Generates a Board Support Package (BSP) from the XSA produced by a synthesis run.

```bash
xviv create --platform pynqz2_bsp
```

#### `xviv build --platform <name>`

Compiles the BSP (`make -j<nproc>`).

```bash
xviv build --platform pynqz2_bsp
```

#### `xviv create --app <name> [--platform <name>] [--template <template>]`

Scaffolds an embedded application from a Vitis template.

```bash
xviv create --app hello_world
xviv create --app hello_world --template empty_application
```

Common templates: `empty_application`, `hello_world`, `lwip_echo_server`, `zynq_fsbl`

#### `xviv build --app <name> [--info]`

Compiles the application. `--info` prints ELF size and section layout.

```bash
xviv build --app hello_world --info
```

---

### Programming

#### `xviv program --platform <name> [--app <name>]`

Downloads the bitstream and optionally the ELF to the connected FPGA via JTAG.

```bash
xviv program --platform pynqz2_bsp --app hello_world
xviv program --bitstream build/synth/system_wrapper/system_wrapper.bit
```

#### `xviv processor --reset | --status`

Soft-reset the MicroBlaze or print JTAG target state and registers.

```bash
xviv processor --reset
xviv processor --status
```

---

## Hooks System

Every major command supports a TCL hooks file that is sourced inside the Vivado session. Hooks are generated by `xviv config` and live under `scripts/`.

**IP hooks** (`scripts/ip/<name>_<version>.tcl`):

| Proc | When called |
|---|---|
| `ipx_add_files` | After opening the edit project |
| `ipx_merge_changes` | After `ipx::merge_project_changes` |
| `ipx_infer_bus_interfaces` | After default AXI-Stream / AXI-MM inference |
| `ipx_add_params` | After HDL parameters are exposed in the GUI |
| `ipx_add_memory_map` | After memory maps are wired |
| `synth_pre` / `synth_post` | Before/after synthesis |
| `place_post` / `route_post` / `bitstream_post` | After each implementation stage |

**BD hooks** (`scripts/bd/<name>_hooks.tcl`):

| Proc | When called |
|---|---|
| `bd_design_config parentCell` | Main BD creation hook; sources exported TCL if present |
| `synth_pre` / `synth_post` / `place_post` / `route_post` / `bitstream_post` | Implementation stages |

**Synthesis hooks** (`scripts/synth/<top>.tcl`):

Same `synth_pre` / `synth_post` / `place_post` / `route_post` / `bitstream_post` procs.

---

## Out-of-Context (OOC) Synthesis

OOC synthesis pre-compiles each leaf IP independently, then links the DCPs into the BD wrapper synthesis. This dramatically reduces iteration time for large BDs — only changed IPs are re-synthesised.

```bash
xviv synth --bd system --ooc-run
```

DCPs are cached in `build/synth/<bd_wrapper>/ooc/<ip_name>/post_synth.dcp`. A DCP is skipped when it is newer than the IP's `component.xml`. The BD wrapper synthesis uses black-box stubs and `read_checkpoint -cell` to link everything together.

An incremental reference DCP (`post_route_reference.dcp`) is saved after each successful route and used automatically on the next run to speed up placement.

---

## Interface Inference Tool (xviv_infer)

`inference.py` parses a SystemVerilog module with `pyslang` and emits a Vivado IP-XACT TCL script that registers every port group as a named bus interface.

```bash
python -m xviv.inference my_ip.sv --verbose
python -m xviv.inference my_ip.sv --dry-run
python -m xviv.inference my_ip.sv -o my_ip_interfaces.tcl --vlnv-v2
```

**Supported interfaces:** AXI4, AXI4-Lite, AXI-Stream, AXI3, APB, AHB-Lite, BRAM, FIFO-Write, FIFO-Read, IIC, SPI, UART, CAN, GPIO, Differential Clock, MII, GMII, RGMII, SGMII, XGMII, Clock signal, Reset signal, Interrupt signal.

Port groups are inferred from name prefixes (`s_axi_*`, `m_axis_*`, etc.) and suffix matching. The generated TCL is designed to be sourced from the `ipx_infer_bus_interfaces` hook.

---

## Wrapper Generator

`wrapper.py` / `xviv create --ip` with `create_wrapper = true` auto-generates a SystemVerilog wrapper that flattens interface ports (e.g., AXI interface bundles) into individual scalar ports for IP packaging.

```bash
# Standalone usage
python -m xviv.wrapper --top my_module -o build/wrapper srcs/rtl/my_module.sv
```

---

## Shell Completion

```bash
# Bash (add to ~/.bashrc)
eval "$(register-python-argcomplete xviv)"

# Zsh (add to ~/.zshrc)
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete xviv)"
```

Tab-completing `--ip`, `--bd`, `--top`, `--platform`, `--app`, and `--dcp` arguments reads live from `project.toml`.

---

## Directory Layout

```
project-root/
├── project.toml              # Single source of truth
├── srcs/
│   ├── rtl/                  # RTL sources (globbed by [sources] rtl)
│   ├── sim/                  # Simulation sources
│   ├── xdc/                  # Constraint files
│   ├── ip/                   # IP-specific RTL
│   └── sw/                   # Embedded application sources
├── scripts/
│   ├── ip/
│   │   └── my_ip_1.0.tcl     # IP hooks (generated by xviv config --ip)
│   ├── bd/
│   │   ├── system_hooks.tcl  # BD hooks (generated by xviv config --bd)
│   │   └── system.tcl        # Exported BD TCL (symlink to versioned file)
│   └── synth/
│       └── system_wrapper.tcl
└── build/                    # All generated artifacts (gitignore this)
    ├── ip/                   # Packaged IP repository
    ├── bd/                   # Block Design files
    ├── wrapper/              # Auto-generated BD wrappers
    ├── synth/                # Synthesis / implementation outputs
    ├── elab/                 # xsim elaboration directories
    ├── bsp/                  # Vitis BSP platforms
    └── app/                  # Embedded application build trees
```
