# xviv

FPGA project controller for Vivado. Drives Xilinx Vivado in non-project mode from a single `project.toml` configuration file — no GUI clicks, no `.xpr` files, no state drift.

Manages the full development lifecycle:

- IP packaging with automatic AXI interface inference
- Block Design creation and wrapper generation
- Synthesis → placement → routing → bitstream in one command
- Standalone simulation via `xvlog` / `xelab` / `xsim` with live waveform reloading
- SystemVerilog interface flattening for Vivado BD compatibility

---

## Requirements

- Python 3.11+
- Xilinx Vivado 2024.1 (other versions likely work, set path in `project.toml`)
- `pyslang` — only required for `xviv_wrap_top`

---

## Installation

```bash
pip install git+https://github.com/you/xviv
```

This installs two commands: `xviv` and `xviv_wrap_top`.

For local development:

```bash
git clone https://github.com/you/xviv
pip install -e ./xviv
```

---

## Quick Start

Create a `project.toml` in your project root:

```toml
[vivado]
path        = "/opt/Xilinx/Vivado/2024.1"
max_threads = 20
mode        = "batch"

[fpga]
part        = "xc7z020clg400-1"
board_part  = "tul.com.tw:pynq-z2:part0:1.0"
board_repo  = "/path/to/vivado-boards/new/board_files"

[build]
dir         = "build"
ip_repo     = "build/ip"
bd_dir      = "build/bd"
wrapper_dir = "srcs/rtl"

[sources]
rtl = ["srcs/rtl/**/*.sv", "srcs/rtl/**/*.v"]
sim = ["srcs/rtl/**/*.sv", "srcs/sim/**/*.sv"]

[[synthesis]]
top     = "my_top"
hooks   = "scripts/synth/my_top.tcl"
constrs = ["srcs/constrs/**/*.xdc"]

[[ip]]
name    = "my_ip"
vendor  = "user.org"
library = "user"
version = "1.0"
top     = "my_ip"
hooks   = "scripts/ip/my_ip_1.0.tcl"

[[bd]]
name  = "my_bd"
hooks = "scripts/bd/my_bd_1.0.tcl"
```

---

## Workflows

### IP Packaging

```bash
# Generate a hook file with stubs for all customisation points
xviv ip-config --ip my_ip

# Edit scripts/ip/my_ip_1.0.tcl, then package the IP
xviv create-ip --ip my_ip

# Reopen an existing IP in the Vivado GUI
xviv edit-ip --ip my_ip
```

The generated hook file exposes five procs you fill in:

| Proc | Purpose |
|---|---|
| `ipx_add_files` | Add your RTL sources to the IP edit project |
| `ipx_merge_changes` | Post-merge fixups |
| `ipx_infer_bus_interfaces` | Infer non-AXI bus standards |
| `ipx_add_params` | Reorder / group HDL parameters in the IP GUI |
| `ipx_add_memory_map` | Add custom memory maps |

AXI-Stream and AXI-MM interfaces are inferred automatically.

---

### Block Design

```bash
# Generate a hook file
xviv bd-config --bd my_bd

# Edit scripts/bd/my_bd_1.0.tcl, then create the BD
xviv create-bd --bd my_bd

# Open an existing BD in the GUI for further edits
xviv edit-bd --bd my_bd

# Generate output products and copy the wrapper to wrapper_dir
xviv generate-bd --bd my_bd
```

---

### Synthesis & Implementation

```bash
# Generate a hook file with lifecycle and report-flag procs
xviv synth-config --top my_top

# Full flow: synth → place → route → bitstream → XSA
xviv synthesis --top my_top

# Open any intermediate checkpoint in the GUI
xviv open-dcp --top my_top --dcp post_synth
xviv open-dcp --top my_top --dcp post_route
```

Outputs land in `build/<top>/`:

```
post_synth.dcp
post_place.dcp
post_route.dcp
my_top.bit
my_top.xsa
reports/
netlists/
```

The synthesis hook file lets you skip report groups (useful during early development) and inject TCL at each stage:

```tcl
proc report_synth  {} { return 0 }  # skip — speeds up iteration
proc report_place  {} { return 1 }
proc report_route  {} { return 1 }
proc report_netlists {} { return 0 }

proc synth_pre   {} { }  # before synth_design
proc synth_post  {} { }  # after synthesis, before placement
proc place_post  {} { }  # after placement, before routing
proc route_post  {} { }  # after routing, before bitstream
proc bitstream_post {} { }
```

---

### Simulation

```bash
# Compile, elaborate, and optionally run headlessly
xviv elaborate --top my_tb
xviv elaborate --top my_tb --run "1000ns"

# With a DPI shared library
xviv elaborate --top my_tb --so my_dpi --dpi-lib ./build/libs

# Open the waveform database in the xsim GUI
xviv open-wdb --top my_tb

# Hot-reload waveform into an already-open xsim window (no window close)
xviv reload-wdb --top my_tb
```

Simulation artifacts land in `build/xviv/<top>/`.

---

### Snapshots

A snapshot is the compiled simulation binary produced by `xelab`. You can open it directly for interactive simulation:

```bash
xviv open-snapshot --top my_tb

# Re-elaborate and reload into the open xsim window
xviv reload-snapshot --top my_tb
```

---

## xviv_wrap_top

Vivado Block Design does not accept SystemVerilog interface ports. `xviv_wrap_top` parses your SV module with `pyslang` and generates a flat wrapper that expands every interface port into individual signals, suitable for IP packaging and BD instantiation.

```bash
xviv_wrap_top \
    --top my_ip \
    --wrapper-dir srcs/rtl \
    srcs/rtl/my_ip.sv \
    srcs/rtl/axi_stream_if.sv
```

Given a module with interface ports:

```systemverilog
module my_ip (
    input  logic           clk,
    axi_stream_if.slave    s_axis,
    axi_stream_if.master   m_axis
);
```

It generates `my_ip_wrapper.sv` with all interface signals flattened to plain ports and `assign` statements wiring them through. Use the wrapper as the IP top module in your `[[ip]]` config.

---

## project.toml Reference

### `[vivado]`

| Key | Default | Description |
|---|---|---|
| `path` | `/opt/Xilinx/Vivado/2024.1` | Vivado installation root |
| `max_threads` | `8` | `general.maxThreads` Vivado parameter |
| `mode` | `batch` | `batch` for scripted, `tcl` for interactive |

### `[fpga]`

| Key | Required | Description |
|---|---|---|
| `part` | yes | FPGA part string e.g. `xc7z020clg400-1` |
| `board_part` | no | Board part string for board presets |
| `board_repo` | no | Path to custom board files directory |

### `[build]`

| Key | Default | Description |
|---|---|---|
| `dir` | `build` | Root build output directory |
| `ip_repo` | `build/ip` | Where packaged IPs are stored |
| `bd_dir` | `build/bd` | Where Block Design outputs land |
| `wrapper_dir` | `srcs/rtl` | Where `generate-bd` copies the BD wrapper |

### `[sources]`

| Key | Description |
|---|---|
| `rtl` | Glob list of RTL sources added to synthesis and IP edit projects |
| `sim` | Glob list of sources added to simulation (compiled by `xvlog`) |

### `[[ip]]`

| Key | Default | Description |
|---|---|---|
| `name` | required | IP name |
| `vendor` | `user.org` | IP vendor string |
| `library` | `user` | IP library string |
| `version` | `1.0` | IP version string |
| `top` | same as `name` | Top-level HDL module name |
| `hooks` | `scripts/ip/<name>_<version>.tcl` | Path to the hook TCL file |

### `[[bd]]`

| Key | Default | Description |
|---|---|---|
| `name` | required | Block Design name |
| `hooks` | `scripts/bd/<name>_<version>.tcl` | Path to the hook TCL file |

### `[[synthesis]]`

| Key | Description |
|---|---|
| `top` | Top module name |
| `hooks` | Path to the synthesis hook TCL file |
| `constrs` | Glob list of XDC constraint files for this target |

---

## Command Reference

### IP

| Command | Arguments | Description |
|---|---|---|
| `ip-config` | `--ip <n>` | Generate a starter hook file |
| `create-ip` | `--ip <n>` | Package the IP |
| `edit-ip` | `--ip <n>` | Open IP in the Vivado GUI |

### Block Design

| Command | Arguments | Description |
|---|---|---|
| `bd-config` | `--bd <n>` | Generate a starter hook file |
| `create-bd` | `--bd <n>` | Create the Block Design |
| `edit-bd` | `--bd <n>` | Open BD in the Vivado GUI |
| `generate-bd` | `--bd <n>` | Generate output products and copy wrapper |

### Synthesis

| Command | Arguments | Description |
|---|---|---|
| `synth-config` | `--top <module>` | Generate a starter hook file |
| `synthesis` | `--top <module>` | Full implementation flow |
| `open-dcp` | `--top <module>` `[--dcp post_synth]` | Open a checkpoint in the GUI |

### Simulation

| Command | Arguments | Description |
|---|---|---|
| `elaborate` | `--top <sim_top>` `[--run <time>]` `[--so <lib>]` `[--dpi-lib <dir>]` | Compile, elaborate, optionally run |
| `open-wdb` | `--top <sim_top>` | Open waveform database in xsim GUI |
| `reload-wdb` | `--top <sim_top>` | Hot-reload waveform into open xsim window |
| `open-snapshot` | `--top <sim_top>` | Open simulation snapshot in xsim GUI |
| `reload-snapshot` | `--top <sim_top>` | Re-run and reload into open xsim window |

### Global Options

| Option | Default | Description |
|---|---|---|
| `--config` / `-c` | `project.toml` | Project configuration file |
| `--log-file` | `build/xviv/xviv.log` | Append debug log to file |

---
