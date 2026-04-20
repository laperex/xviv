# xviv

**xviv** is a command-line project controller for AMD/Xilinx Vivado and Vitis workflows. It replaces the manual, GUI-driven FPGA development cycle with a declarative, reproducible, version-control-friendly build system driven by a single `project.toml` (or `project.cue`) configuration file.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Commands](#commands)
- [Shell Completion](#shell-completion)
- [Project Layout](#project-layout)

---

## Features

- **Declarative project config** — FPGA part, IP cores, block designs, synthesis targets, simulation targets, and embedded platforms all defined in one file.
- **CUE or TOML** — validated CUE schemas (`project.cue`) or plain TOML (`project.toml`).
- **IP management** — create, edit, and synthesise custom IP packaged in Vivado's IP catalog format. Optional SV wrapper generation via `pyslang` for interface-port flattening.
- **Block Design (BD)** — create, edit, generate output products, export versioned TCL snapshots, and synthesise BDs without touching the GUI.
- **Full synthesis pipeline** — synth → opt → place → phys-opt → route → bitstream, with incremental synthesis and incremental implementation support and per-stage hooks.
- **Simulation** — compile with `xvlog`/`xelab`, run with `xsim`, open waveforms, and hot-reload snapshots over a FIFO control channel.
- **Embedded (MicroBlaze)** — BSP generation, app scaffolding, build, FPGA programming, processor reset and status via `xsct`.
- **IP catalog search** — full-text search across VLNV, display name, and description.
- **Shell autocompletion** — `argcomplete`-powered tab completion for every flag, including dynamic IP/BD/top names and VLNV strings from the live catalog.
- **Git-aware builds** — SHA tag and dirty-state tracking embedded in bitstream `USR_ACCESS` and output filenames; diff patches captured for dirty builds.

---

## Installation

```bash
pip install xviv
```

Requires Python 3.10+.  
Optional: install [`cue`](https://cuelang.org/docs/install/) to use `.cue` project files.  
Optional: install `pyslang` for SV wrapper generation.

Vivado/Vitis must be installed separately. Point `xviv` at them via environment variables:

```bash
export XVIV_VIVADO_DIR=/opt/Xilinx/Vivado/2024.1
export XVIV_VITIS_DIR=/opt/Xilinx/Vitis/2024.1
```

---

## Quick Start

```bash
# 1. Create project.toml in your project root
cat > project.toml <<'EOF'
[fpga.main]
part       = "xc7z020clg400-1"
board_part = "digilentinc.com:zedboard:part0:1.0"

[[synthesis]]
top = "top_design"
rtl = ["srcs/rtl/**/*.sv"]
xdc = ["constraints/top.xdc"]
EOF

# 3. Synthesise the top-level design
xviv synth --top top_design

# 4. Open the post-synthesis checkpoint
xviv open --dcp post_synth --top top_design
```

---

## Configuration

xviv reads `project.cue` first, then falls back to `project.toml`. The `--config` / `-c` flag overrides this.

### `[fpga]`

```toml
[fpga]
default = "main"          # which named target to use by default

[fpga.main]
part       = "xc7z020clg400-1"
board_part = "digilentinc.com:zedboard:part0:1.0"
board_repo = ""            # optional path to a custom board repo

[fpga.ooc]
part = "xc7z020clg400-1"  # a second named target for OOC synthesis
```

### `[vivado]`

```toml
[vivado]
mode        = "batch"          # batch | tcl
max_threads = 8
hw_server   = "localhost:3121"
```

### `[vitis]`

```toml
[vitis]
# path is read from $XVIV_VITIS_DIR; no explicit key needed
```

### `[build]`

```toml
[build]
dir         = "build"
ip_repo     = "build/ip"
bd_dir      = "build/bd"
wrapper_dir = "build/wrapper"
core_dir    = "build/core"
```

### `[[ip]]`

```toml
[[ip]]
name           = "my_ip"
vendor         = "user.org"
library        = "user"
version        = "1.0"
top            = "my_ip"          # HDL top module name
rtl            = ["srcs/rtl/**/*.sv"]
hooks          = "scripts/ip/my_ip_1.0.tcl"   # auto-generated path if omitted
create-wrapper = false            # true to auto-generate a flat SV wrapper
```

### `[[bd]]`

```toml
[[bd]]
name       = "system"
hooks      = "scripts/bd/system_hooks.tcl"    # auto-generated if omitted
export_tcl = "scripts/bd/state/system.tcl"    # auto-generated if omitted
fpga       = ""                               # override fpga target
```

### `[[synthesis]]`

```toml
[[synthesis]]
top              = "top_design"
ip               = ""              # IP name if this is an IP synth entry
bd               = ""              # BD name if this is a BD synth entry
rtl              = ["srcs/rtl/**/*.sv"]
xdc              = ["constraints/top.xdc"]
xdc_ooc          = []
fpga             = ""              # override fpga target
hooks            = "scripts/synth/top_design.tcl"

# Reporting
report_synth     = false
report_place     = false
report_route     = false
generate_netlist = false
out_of_context   = false
```

### `[[simulate]]`

```toml
[[simulate]]
top = "tb_top"
rtl = ["srcs/sim/**/*.sv", "srcs/rtl/**/*.sv"]
```

### `[[platform]]`

```toml
[[platform]]
name      = "zed_platform"
cpu       = "ps7_cortexa9_0"
os        = "standalone"
synth_top = "top_design"   # or: xsa = "path/to/manual.xsa"
```

### `[[app]]`

```toml
[[app]]
name     = "hello_world"
platform = "zed_platform"
template = "hello_world"
src_dir  = "srcs/sw/hello_world"
```

---

## Commands

### `create`

```
xviv create --ip   <name>               # scaffold and package a custom IP
xviv create --bd   <name>               # create a new Block Design project
xviv create --core <name> --vlnv <vlnv> # instantiate a catalog IP into build/core
xviv create --platform <name>           # generate a BSP from an XSA
xviv create --app  <name> [--platform <p>] [--template <t>]
```

### `search`

```
xviv search <query>     # search VLNV, display name, and description
```

### `edit`

```
xviv edit --ip <name> [--nogui]
xviv edit --bd <name> [--nogui]
```

### `config`

Generates a starter hooks TCL file for the named target. Safe to re-run only before the hooks file exists.

```
xviv config --ip  <name>
xviv config --bd  <name>
xviv config --top <name>
```

### `generate`

```
xviv generate --bd <name>   # generate output products + Verilog wrapper
```

### `export`

```
xviv export --bd <name>     # export BD as a versioned re-runnable TCL script
```

### `synth`

```
xviv synth --ip  <name>
xviv synth --bd  <name> [--ooc-run]
xviv synth --top <name>
```

### `open`

```
xviv open --dcp <stem> --top <name> [--nogui]   # open a .dcp checkpoint
xviv open --wdb        --top <name>             # open a .wdb waveform DB
```

### `elaborate`

```
xviv elaborate --top <name> [--run <time>]   # compile + optionally run sim
```

### `simulate`

```
xviv simulate --top <name> [--run <time>]
```

### `reload`

```
xviv reload   --top <name>   # reload waveform DB
```

### `build`

```
xviv build --platform <name>
xviv build --app      <name> [--info]
```

### `program`

```
xviv program [--platform <name>] [--app <name>] [--elf <path>] [--bitstream <path>]
```

### `processor`

```
xviv processor --reset
xviv processor --status
```

---

## Shell Completion

Enable `argcomplete` system-wide:

```bash
activate-global-python-argcomplete
```

Or per-shell (bash):

```bash
eval "$(register-python-argcomplete xviv)"
```

Tab completion is context-aware: IP names, BD names, top names, DCP stems, VLNV strings, and platform/app names all complete dynamically from your project config and the live Vivado IP catalog.

---

## Project Layout

A typical project using xviv looks like:

```
my_project/
├── project.toml
├── srcs/
│   ├── rtl/
│   │   └── *.sv
│   ├── sim/
│   │   └── *.sv
│   └── sw/
│       └── hello_world/
│           └── main.c
├── constraints/
│   └── top.xdc
├── scripts/
│   ├── ip/
│   │   └── my_ip_1.0.tcl     # generated by: xviv config --ip my_ip
│   ├── bd/
│   │   ├── system_hooks.tcl  # generated by: xviv config --bd system
│   │   └── state/
│   │       └── system.tcl    # generated by: xviv export --bd system
│   └── synth/
│       └── top_design.tcl    # generated by: xviv config --top top_design
└── build/                    # all outputs; safe to gitignore
    ├── ip/                   # packaged custom IPs
    ├── bd/                   # block design files
    ├── wrapper/              # generated SV wrappers
    ├── core/                 # instantiated catalog IP cores
    ├── elab/                 # simulation elaboration outputs
    ├── synth/                # synthesis checkpoints + bitstreams
    ├── bsp/                  # embedded BSPs
    ├── app/                  # embedded application builds
    └── xviv/                 # xviv logs and control FIFOs
```

---

## License

See `LICENSE` for details.