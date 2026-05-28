# xviv — Usage Guide

A complete reference for using xviv: project setup, config schema, every command, recommended workflows, and development tips.

---

## Table of Contents

1. [Philosophy](#philosophy)
2. [Installation](#installation)
3. [Tool Discovery — How xviv Finds Vivado and Vitis](#tool-discovery)
4. [Project Layout](#project-layout)
5. [project.toml — Full Schema Reference](#projecttoml--full-schema-reference)
   - [[project]](#project)
   - [[[fpga]]](#fpga)
   - [[[design]]](#design)
   - [[[ip]]](#ip)
   - [[[wrapper]]](#wrapper)
   - [[[core]]](#core)
   - [[[bd]]](#bd)
   - [[[synth]]](#synth)
   - [[[simulation]]](#simulation)
   - [[[uvm]]](#uvm)
   - [[[platform]]](#platform)
   - [[[app]]](#app)
   - [[[formal]]](#formal)
6. [Command Reference](#command-reference)
   - [Global Flags](#global-flags)
   - [create](#create)
   - [edit](#edit)
   - [generate](#generate)
   - [synth](#synth-1)
   - [open](#open)
   - [reload](#reload)
   - [simulate](#simulate-1)
   - [build](#build-1)
   - [program](#program-1)
   - [processor](#processor-1)
   - [search](#search-1)
   - [formal](#formal-1)
7. [Recommended Workflows](#recommended-workflows)
   - [Bare RTL Design — First Build](#bare-rtl-design--first-build)
   - [Custom IP Development Cycle](#custom-ip-development-cycle)
   - [Block Design Workflow](#block-design-workflow)
   - [Embedded MicroBlaze Workflow](#embedded-microblaze-workflow)
   - [Simulation Workflow](#simulation-workflow)
   - [Formal Verification Workflow](#formal-verification-workflow)
   - [Incremental / Resume Builds](#incremental--resume-builds)
   - [Team / Clean-Clone Workflow](#team--clean-clone-workflow)
8. [Shell Completion](#shell-completion)
9. [Git Traceability — USR_ACCESS Embedding](#git-traceability--usr_access-embedding)
10. [Dry-Run and TCL Inspection](#dry-run-and-tcl-inspection)
11. [Logging](#logging)
12. [Lock File](#lock-file)
13. [Environment Variables](#environment-variables)
14. [Annotated Full project.toml Examples](#annotated-full-projecttoml-examples)

---

## Philosophy

xviv is a **declarative, CLI-first project controller** for Xilinx/AMD Vivado and Vitis. The entire build — FPGA target, custom IPs, block designs, RTL sources, synthesis runs, simulations, and embedded firmware — is described in a single `project.toml`. Running any command from a clean clone reproduces the project identically. The `build/` directory is fully gitignored and always regenerable.

Key design decisions:

- **Non-project / batch-mode Vivado.** xviv never creates a `.xpr` project file. It generates TCL scripts and runs Vivado in batch mode. This keeps the repository clean and makes CI trivial.
- **Block designs are TCL snapshots.** After editing a BD in the GUI, xviv writes a re-runnable TCL script under `scripts/xviv/bd/`. This file is committed and reviewed like any other source. A `create --bd` recreates the BD from scratch on any machine.
- **Git traceability.** Synthesis embeds a short git SHA into the bitstream `USR_ACCESS` field. Bit 28 is set when the working tree was dirty. Any `.bit` file can be traced back to the exact commit that produced it.
- **GUI for what actually needs it.** Block design editing and IP packaging benefit from the Vivado GUI. Everything else — synthesis, simulation, programming, BSP builds — runs from the terminal.

---

## Installation

```sh
pip install xviv
```

Requires **Python 3.11+**. Vivado and/or Vitis must be available (see [Tool Discovery](#tool-discovery)).

For development (editable install with linting/testing):

```sh
git clone https://github.com/laperex/xviv.git
cd xviv
pip install -e ".[dev]"
pre-commit install
```

`pyslang` (already a declared dependency) is used for SystemVerilog interface inference when generating IP wrappers via `[[wrapper]]`.

---

## Tool Discovery

xviv needs to locate the Vivado and Vitis installations. It resolves them in this order:

1. **PATH** — if `vivado` (or `xsct` for Vitis) is already on your PATH (e.g., you sourced `settings64.sh`), xviv uses it directly.
2. **`XVIV_VIVADO_SOURCE_SCRIPT` environment variable** — if the tool is not on PATH, xviv reads this variable and sources the script automatically before running anything.
3. **`.env` file** — a `.env` file at the project root is read before checking `XVIV_VIVADO_SOURCE_SCRIPT`. This is the recommended way to keep the path per-project without polluting your shell profile.

### Recommended setup

Create a `.env` file at the project root (add it to `.gitignore` if paths are machine-specific):

```sh
# .env
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

Or export it in your shell:

```sh
export XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

---

## Project Layout

```
myproject/
├── project.toml                  # the only file xviv requires - declare everything here
├── project.lock                  # auto-generated resolved config snapshot
├── .env                          # optional: XVIV_VIVADO_SOURCE_SCRIPT=...
├── .gitignore                    # add: build/
│
├── srcs/
│   ├── rtl/                      # synthesisable RTL (SystemVerilog / Verilog / VHDL)
│   ├── ip/                       # custom IP source trees
│   └── sim/                      # testbenches and simulation-only sources
│
├── constraints/                  # .xdc constraint files
│
├── scripts/
│   └── xviv/
│       └── bd/
│           └── system.tcl        # BD TCL snapshot - VERSION CONTROL THIS
│
└── build/                        # gitignore everything here; fully regenerable
    ├── log/
    │   └── xviv.log              # debug log
    ├── ip/                       # packaged custom IP repos
    ├── core/                     # instantiated catalog IPs (.xci)
    ├── bd/                       # generated BD output products
    ├── synth/
    │   └── <name>/
    │       ├── checkpoints/      # synth.dcp, place.dcp, route.dcp
    │       ├── reports/          # timing, utilization, DRC, power, ...
    │       ├── netlists/         # functional/timing netlists, SDF
    │       ├── <name>.bit        # bitstream
    │       └── <name>.xsa        # hardware platform for Vitis
    ├── sim/
    │   └── <name>/               # per-simulation work directory
    ├── platform/
    │   └── <name>/               # Vitis platform / BSP
    ├── app/
    │   └── <name>/               # Vitis application + ELF
    └── formal/
        └── <name>/               # SymbiYosys work directory
```

The only generated directory that belongs in version control is `scripts/xviv/`. Commit the BD TCL snapshots there. Every path under `build/` is reproducible from `project.toml` and the TCL snapshots.

---

## project.toml — Full Schema Reference

All sections except `[project]` are **arrays of tables** (`[[section]]`). You can have multiple entries of the same type. The first `[[fpga]]` is the default used by all entities that don't explicitly reference a named FPGA.

### `[project]`

Optional global settings. All keys have defaults.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `work_dir` | string | `"build"` | Root directory for all generated outputs. |
| `log_file` | string | `"<work_dir>/log/xviv.log"` | Debug log file path. |
| `board_repo` | list[string] | `[]` | Additional board repository paths (for `board_part` lookups). |
| `ip_repo` | list[string] | `[]` | Additional IP repository paths to register with Vivado. The default `build/ip` repo is always included. |

```toml
[project]
work_dir   = "build"
board_repo = ["/opt/Xilinx/board_files"]
ip_repo    = ["/opt/myorg_ip_repo"]
```

---

### `[[fpga]]`

Declares an FPGA target. At least one entry is required. The first entry is the default target for all entities that don't specify `fpga = "name"`.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | ✅ | Unique identifier. Referenced by other sections via `fpga = "name"`. |
| `fpga_part` | string | one of | Xilinx part number, e.g. `"xc7z020clg400-1"`. |
| `board_part` | string | one of | Board part string, e.g. `"tul.com.tw:pynq-z2:part0:1.0"`. |

Exactly one of `fpga_part` or `board_part` must be specified.

```toml
[[fpga]]
name      = "main"
fpga_part = "xc7z020clg400-1"

[[fpga]]
name       = "pynq"
board_part = "tul.com.tw:pynq-z2:part0:1.0"
```

---

### `[[design]]`

Declares an RTL design: a set of source files with a top module. Used by `[[synth]]` and `[[simulation]]`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `sources` | list | ✅ | | Source file globs or structured source entries. |
| `top` | string | | same as `name` | Top module name. |
| `fpga` | string | | first `[[fpga]]` | FPGA target reference. |

Sources can be bare glob strings or structured dicts with `used_in` stage control:

```toml
[[design]]
name    = "top"
top     = "top_module"
fpga    = "main"
sources = [
    "srcs/rtl/**/*.sv",
    "srcs/rtl/**/*.v",
    { files = ["srcs/rtl/debug_only.sv"], used_in = ["sim"] },
]
```

Valid `used_in` stages: `"synth"`, `"impl"`, `"ooc"`, `"sim"`. A bare glob string is included in all stages.

---

### `[[ip]]`

Declares a custom IP to be packaged by Vivado's IP Packager. xviv handles packaging and registers the resulting IP in its own IP repository under `build/ip/`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. Also the default top module name and VLNV `name` field. |
| `sources` | list | ✅ | | RTL sources for the IP (globs or structured). |
| `top` | string | | same as `name` | Top module name inside the IP. |
| `vendor` | string | | `"xviv.org"` | VLNV vendor string. |
| `library` | string | | `"xviv"` | VLNV library string. |
| `version` | string | | `"1.0"` | VLNV version string. |
| `vlnv` | string | | auto-generated | Override the full VLNV string. |
| `fpga` | string | | first `[[fpga]]` | FPGA target for packaging. |
| `repo` | string | | `"build/ip"` | Override the IP repo output path. |

```toml
[[ip]]
name    = "axi_gamma"
top     = "axi_gamma"
sources = ["srcs/ip/axi_gamma/**/*.sv"]
vendor  = "myorg"
library = "dsp"
version = "2.0"
```

---

### `[[wrapper]]`

Optional companion to `[[ip]]`. When a custom IP has interface ports (AXI, AXI-Stream, etc.) that Vivado's IP Packager cannot infer automatically, a wrapper can flatten them. Requires `pyslang`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `ip` | string | ✅ | | Name of the `[[ip]]` to wrap. |
| `sources` | list | ✅ | | Additional sources that define the interface types. |
| `wrapper_top` | string | | `<ip_top>_wrapper` | Name of the generated wrapper module. |
| `wrapper_file` | string | | `build/wrapper/<wrapper_top>.sv` | Output path for the generated wrapper. |

```toml
[[wrapper]]
ip      = "axi_gamma"
sources = ["srcs/ip/axi_gamma/**/*.sv"]
```

---

### `[[core]]`

Declares an instance of a catalog IP — either a Xilinx built-in IP or a previously packaged custom IP. Identified by a partial VLNV string.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique instance name. Used as the XCI file basename. |
| `vlnv` | string | one of | | Partial or full VLNV string. Tab completion resolves against the live catalog. |
| `ip` | string | one of | | Name of a declared `[[ip]]` to instantiate. |
| `fpga` | string | | first `[[fpga]]` | FPGA target. |
| `xci_file` | string | | `build/core/<name>/<name>.xci` | Override the XCI output path. |

```toml
[[core]]
name = "clk_wiz_0"
vlnv = "clk_wiz:6.0"

[[core]]
name = "axi_dma_0"
vlnv = "xilinx.com:ip:axi_dma:7.1"
```

> **Tip:** Use `xviv search <keyword>` to find the right VLNV string, e.g. `xviv search axi_dma`.

---

### `[[bd]]`

Declares a block design. xviv manages creation, GUI editing, TCL snapshot export/import, and output product generation.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `fpga` | string | | first `[[fpga]]` | FPGA target. |
| `save_file` | string | | `scripts/xviv/bd/<name>.tcl` | Path for the BD TCL snapshot. Commit this file. |
| `bd_file` | string | | `build/bd/<name>/<name>.bd` | Path of the generated `.bd` file. |
| `bd_wrapper_file` | string | | `build/bd/<name>/hdl/<name>_wrapper.v` | Path of the generated HDL wrapper. |

When a `.bd` file already exists, xviv automatically discovers all IP cores embedded in the BD and registers them as `[[core]]` entries with OOC synthesis configurations.

```toml
[[bd]]
name = "system"

[[bd]]
name      = "video_pipeline"
fpga      = "pynq"
save_file = "scripts/xviv/bd/video_pipeline.tcl"
```

---

### `[[synth]]`

Declares a synthesis run, tied to exactly one `design`, `bd`, or `core`. Controls the full pipeline: synth → opt → place → phys_opt → route → bitstream.

**Identity (exactly one required):**

| Key | Type | Description |
|-----|------|-------------|
| `design` | string | Name of a `[[design]]` to synthesise. |
| `bd` | string | Name of a `[[bd]]` to synthesise. |
| `core` | string | Name of a `[[core]]` to synthesise out-of-context. |

**Pipeline control:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `run_synth` | bool | `true` | Run `synth_design`. |
| `run_opt` | bool | `true` | Run `opt_design`. |
| `run_place` | bool | `true` | Run `place_design`. |
| `run_phys_opt` | bool | `true` | Run `phys_opt_design`. |
| `run_route` | bool | `true` | Run `route_design`. |
| `synth_incremental` | bool | `true` | Enable incremental synthesis if a prior synth checkpoint exists. |
| `impl_incremental` | bool | `true` | Enable incremental implementation if a prior route checkpoint exists. |

**Output artifacts** (each accepts `true` for default path, `false` to disable, or a string path to override):

| Key | Default | Description |
|-----|---------|-------------|
| `synth_dcp` | `true` | Checkpoint after `synth_design`. |
| `place_dcp` | `true` | Checkpoint after `place_design`. |
| `route_dcp` | `true` | Checkpoint after `route_design`. |
| `bitstream` | `true` (design/bd), `false` (core) | Output `.bit` file. |
| `hw_platform` | `true` (bd), `false` (design/core) | Output `.xsa` hardware platform for Vitis. |
| `synth_stub` | `false` (design/bd), `true` (core) | Stub Verilog file. |
| `synth_functional_netlist` | `false` | Post-synth functional netlist. |
| `synth_timing_netlist` | `false` | Post-synth timing netlist. |
| `impl_functional_netlist` | `false` | Post-impl functional netlist. |
| `impl_timing_netlist` | `false` | Post-impl timing netlist (SDF annotation). |
| `impl_timing_sdf` | auto | SDF file; auto-enabled when `impl_timing_netlist` is enabled. |

**Reports** (same `bool | str` semantics):

| Key | Default |
|-----|---------|
| `synth_report_timing_summary` | `false` |
| `synth_report_utilization` | `false` |
| `route_report_drc` | `false` |
| `route_report_methodology` | `false` |
| `route_report_power` | `false` |
| `route_report_route_status` | `false` |
| `route_report_timing_summary` | `false` |
| `synth_report_incremental_reuse` | `false` |
| `impl_report_incremental_reuse` | `false` |

**Directives and synthesis options:**

| Key | Default | Description |
|-----|---------|-------------|
| `synth_directive` | `"default"` | `synth_design -directive` value. |
| `synth_mode` | `"default"` | `"default"` or `"out_of_context"`. Cores are automatically `"out_of_context"`. |
| `synth_flatten_hierarchy` | `"rebuilt"` | `"rebuilt"`, `"full"`, or `"none"`. |
| `synth_fsm_extraction` | `"auto"` | FSM extraction mode. |
| `opt_directive` | `"default"` | `opt_design -directive` value. |
| `place_directive` | `"default"` | `place_design -directive` value. |
| `phys_opt_directive` | `"default"` | `phys_opt_design -directive` value. |
| `route_directive` | `"default"` | `route_design -directive` value. |
| `usr_access_value` | `nil` | Hardcode the `USR_ACCESS` value (overrides git SHA). |

**Constraints:**

| Key | Type | Description |
|-----|------|-------------|
| `constraints` | list | XDC constraint file globs. |
| `fpga` | string | Override FPGA target. |
| `top` | string | Override top module. |

```toml
[[synth]]
design      = "top"
constraints = ["constraints/top.xdc"]

run_route                   = true
route_report_timing_summary = true
route_report_drc            = true
impl_timing_netlist         = true

synth_directive  = "AreaOptimized_high"
place_directive  = "ExplorePostRoutePhysOpt"

[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
hw_platform = true

[[synth]]
core       = "clk_wiz_0"
run_place  = false
run_route  = false
```

---

### `[[simulation]]`

Declares a simulation target. Supports xsim (default) and Verilator backends.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | ✅ | Unique identifier. |
| `sources` | list | ✅ | Testbench + any additional sources. |
| `top` | string | same as `name` | Top simulation module. |
| `backend` | string | `"xsim"` | `"xsim"` or `"verilator"`. |
| `timescale` | string | `"1ns/1ps"` | Timescale string passed to xvlog/xelab. |
| `design` | string | | Link a `[[design]]`'s sources into the simulation. |
| `bd` | string | | Reserved; not yet used. |
| `plusargs` | list[str] | `[]` | Plusargs passed to xsim or the Verilated binary. |
| `defines` | list[str] | `[]` | Preprocessor defines (`-D` flags). |
| `include_dirs` | list[str] | `[]` | Include directories (`-I` flags). |
| `uvm` | list | `[]` | Inline UVM test declarations (same schema as `[[uvm]]`, minus `simulation`). |
| `uvm_version` | string | `"1.2"` | UVM library version to link (`"1.1d"` or `"1.2"`). |
| `uvm_verbosity` | string | `"UVM_MEDIUM"` | Default UVM verbosity. |
| `uvm_max_quit_count` | int | `null` | Max UVM error count before abort. |
| `sdfmax` | list[str] | `[]` | SDF max-delay back-annotation targets (for post-impl timing sim). |
| `sdfmin` | list[str] | `[]` | SDF min-delay back-annotation targets. |

**Verilator-specific:**

| Key | Default | Description |
|-----|---------|-------------|
| `threads` | `1` | Number of Verilator threads (`--threads`). |
| `trace` | `false` | Enable VCD tracing (`--trace`). |
| `trace_fst` | `false` | Enable FST tracing (`--trace-fst`). |
| `trace_depth` | `null` | Trace depth limit. |
| `verilator_args` | `[]` | Extra arguments passed directly to Verilator. |
| `uvm_pkg_dir` | `null` | Path to a Verilator-compatible UVM package root (required for UVM with Verilator). |

```toml
[[simulation]]
name    = "tb_top"
top     = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
backend = "xsim"

[[simulation]]
name       = "tb_axi_gamma"
sources    = ["srcs/sim/tb_axi_gamma.sv", "srcs/ip/axi_gamma/**/*.sv"]
backend    = "verilator"
trace      = true
trace_fst  = false
threads    = 4
defines    = ["SIM_MODE", "DUMP_WAVES"]
```

---

### `[[uvm]]`

Declares a UVM test configuration attached to a `[[simulation]]`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `test` | string | ✅ | | UVM test class name (`UVM_TESTNAME` plusarg). |
| `simulation` | string | ✅ | | Name of the `[[simulation]]` this test belongs to. |
| `top` | string | | inherited from simulation | Override the top module for this test. |
| `timescale` | string | | inherited from simulation | Override timescale. |
| `verbosity` | string | | inherited from simulation | UVM verbosity level. |
| `version` | string | | inherited from simulation | UVM library version. |
| `max_quit_count` | int | | inherited from simulation | Max error count. |

```toml
[[uvm]]
simulation  = "tb_top"
test        = "smoke_test"
verbosity   = "UVM_LOW"

[[uvm]]
simulation  = "tb_top"
test        = "stress_test"
verbosity   = "UVM_NONE"
max_quit_count = 5
```

---

### `[[platform]]`

Declares a Vitis embedded platform. Generates a BSP from the `.xsa` file produced by synthesis.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `bd` | string | one of | | Reference a `[[bd]]`'s synthesis outputs (`.xsa` + `.bit`). |
| `design` | string | one of | | Reference a `[[design]]`'s synthesis outputs. |
| `xsa` | string | one of | | Explicit path to a `.xsa` file. |
| `bitstream` | string | | auto from synth | Explicit path to a `.bit` file. |
| `cpu` | string | `"microblaze_0"` | CPU instance name in the block design. |
| `os` | string | `"standalone"` | OS type (`"standalone"`, `"freertos10_xilinx"`, etc.). |
| `properties` | dict | `{}` | Nested BSP property overrides (see below). |

**BSP properties** are specified as a nested TOML table and flattened to `CONFIG.key = value` pairs passed to `hsi`:

```toml
[[platform]]
name = "mb_platform"
bd   = "system"
cpu  = "microblaze_0"
os   = "standalone"

[platform.properties.CONFIG]
stdout = "mdm_1"
stdin  = "mdm_1"
```

---

### `[[app]]`

Declares a Vitis software application.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `platform` | string | ✅ | | Name of the `[[platform]]` to build against. |
| `template` | string | `"empty_application"` | Vitis application template. |
| `sources` | list | `[]` | C/C++ source files to copy into the application. |

The compiled ELF is placed at `build/app/<name>/executable.elf`.

```toml
[[app]]
name     = "firmware"
platform = "mb_platform"
template = "empty_application"
sources  = ["srcs/sw/main.c", "srcs/sw/drivers/**/*.c"]
```

---

### `[[formal]]`

Declares a formal verification target using **SymbiYosys**. Vivado is not required.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `top` | string | ✅ | | Top module to verify. |
| `mode` | string | ✅ | | `"bmc"` (bounded model check), `"prove"`, or `"cover"`. |
| `sources` | list[str] | ✅ | | RTL sources + property files (glob strings). |
| `depth` | int | `20` | | Verification depth (number of cycles). |
| `append` | int | `0` | | Extend cover traces by this many cycles. |
| `engine` | string | `"smtbmc yices z3"` | | SymbiYosys engine specification. |
| `defines` | list[str] | `[]` | | Preprocessor defines. |
| `include_dirs` | list[str] | `[]` | | Include directories. |
| `multiclock` | bool | `false` | | Enable multiclock mode. |
| `async2sync` | bool | `false` | | Apply `async2sync` transformation. |
| `sv` | bool | `true` | | Parse sources as SystemVerilog. |
| `extra_script` | list[str] | `[]` | | Extra lines appended to the `[script]` section of the `.sby` file. |
| `extra_opts` | list[str] | `[]` | | Extra lines appended to the `[options]` section. |

```toml
[[formal]]
name    = "axi_gamma_props"
top     = "axi_gamma"
mode    = "prove"
depth   = 40
sources = [
    "srcs/ip/axi_gamma/axi_gamma.sv",
    "srcs/formal/axi_gamma_props.sv",
]
defines = ["FORMAL"]
```

---

## Command Reference

All commands are invoked as `xviv <command> [flags]`.

The config file is resolved automatically (`project.toml` in the current directory), or specified explicitly:

```sh
xviv --config path/to/project.toml <command>
```

### Global Flags

| Flag | Description |
|------|-------------|
| `--config FILE` / `-c FILE` | Path to `project.toml`. Default: `project.toml` in the current directory. |

Every subcommand also accepts:

| Flag | Description |
|------|-------------|
| `--dry-run` | Generate and print the TCL script(s) without executing them. |
| `--check` | Check the generated TCL output (does not execute). |

---

### `create`

Create a custom IP, block design, catalog core instance, Vitis platform, or Vitis app.

```sh
xviv create --ip <name>       [--edit] [--nogui] [--regenerate]
xviv create --bd <name>       [--source-file FILE] [--generate] [--edit] [--nogui]
xviv create --core <name>     [--generate] [--edit] [--nogui]
xviv create --platform <name> [--build]
xviv create --app <name>      [--platform <name>] [--build]
```

**`--ip <name>`** — Packages the IP declared in `[[ip]]`. Opens the Vivado IP Packager.

- `--edit`: Open the IP Packager GUI after packaging.
- `--nogui`: Run in TCL-only mode without spawning a GUI.
- `--regenerate`: After packaging, regenerate all catalog core (`.xci`) instances that use this IP, in parallel. Only cores whose XCI file already exists are regenerated.

**`--bd <name>`** — Creates the block design.

- Without `--source-file`: Creates a new empty BD and opens the GUI for manual editing.
- With `--source-file <path>`: Imports the BD from the given TCL snapshot. When no path is given, defaults to `scripts/xviv/bd/<name>.tcl`.
- `--generate`: Generate output products after import. Output products are **not** generated by default.
- `--edit`: Open the GUI after import for further editing.
- `--nogui`: Import without opening the GUI.

**`--core <name>`** — Instantiates a catalog IP (creates the `.xci` file).

- `--generate`: Generate output products immediately. Not generated by default.
- `--edit`: Open the core customisation GUI.

**`--platform <name>`** — Creates the Vitis BSP. Requires the `.xsa` from synthesis to exist.

- `--build`: Also compile the BSP immediately.

**`--app <name>`** — Scaffolds a Vitis application from the declared template.

- `--platform <name>`: Override the platform (defaults to the one declared in `[[app]]`).
- `--build`: Also compile the app immediately.

---

### `edit`

Open an IP, BD, or core in Vivado for editing.

```sh
xviv edit --ip   <name> [--nogui]
xviv edit --bd   <name> [--nogui]
xviv edit --core <name> [--nogui]
```

For BDs and IPs, this opens the Vivado GUI with the relevant editor loaded. After making changes, use `generate --bd <name>` (for BDs) or `create --ip <name>` (for IPs, to re-package).

---

### `generate`

Generate or re-generate output products for a block design or catalog core.

```sh
xviv generate --bd   <name> [--force] [--reset]
xviv generate --core <name> [--force] [--reset]
```

- `--force`: Force re-generation even if products appear up to date.
- `--reset`: Reset all output products before generating. Use this if output products are stale or corrupted.

---

### `synth`

Run the synthesis and implementation pipeline.

```sh
xviv synth --design <name> [--resume STAGE] [--usr-access-type TYPE] [--parallel]
xviv synth --bd     <name> [--resume STAGE] [--usr-access-type TYPE] [--parallel]
xviv synth --core   <name> [--resume STAGE]
```

The pipeline stages that run depend on the `run_*` flags in `[[synth]]`. By default, all stages run: `synth_design` → `opt_design` → `place_design` → `phys_opt_design` → `route_design` → `write_bitstream`.

**`--resume STAGE`** — Resume from an existing checkpoint rather than starting fresh.

| Value | Resumes from |
|-------|-------------|
| `auto` | Detect the latest available checkpoint automatically. |
| `synth` | Resume from `synth.dcp` (skip `synth_design`, re-run from `opt_design`). |
| `place` | Resume from `place.dcp` (skip through `place_design`, re-run from `phys_opt`). |
| `route` | Resume from `route.dcp` (re-run only `write_bitstream`). |

**`--usr-access-type TYPE`** — Controls what gets embedded in the bitstream `USR_ACCESS` field.

| Value | Behaviour |
|-------|-----------|
| `git` (default) | Embeds the short git SHA in bits [27:0]. Bit 28 is set if the working tree was dirty. |

**`--parallel`** — Synthesize all registered sub-cores in parallel (via `ThreadPoolExecutor`) before running the top-level synthesis. The XCI for each sub-core must already exist. Per-job output includes colored status, elapsed time, and log file path.

---

### `open`

Open a synthesis checkpoint or simulation waveform database.

```sh
xviv open --dcp <path>     [--nogui]
xviv open --wdb <sim-name> [--nogui]
```

- `--dcp <path>`: Open a `.dcp` checkpoint in Vivado. Path tab-completes to known checkpoint locations.
- `--wdb <sim-name>`: Open the `.wdb` waveform from the named simulation in xsim/xwave.
- `--nogui`: Run in TCL mode (batch/headless inspection).

---

### `reload`

Hot-reload a waveform snapshot in a live xsim session without re-running the simulation.

```sh
xviv reload --target <sim-name>
```

This sends a reload command to an already-running xsim GUI via a FIFO. The waveform updates to the most recent simulation run without closing the viewer.

---

### `simulate`

Compile and run a simulation.

```sh
xviv simulate --target <name> [--mode MODE] [--run TIME] [--uvm TEST]
```

**`--mode MODE`** — Simulation source mode:

| Mode | Sources used |
|------|-------------|
| `default` | RTL sources directly. |
| `post_synth_functional` | Post-synthesis functional netlist. Requires `synth_functional_netlist = true` in `[[synth]]`. |
| `post_synth_timing` | Post-synthesis timing netlist. |
| `post_impl_functional` | Post-implementation functional netlist. |
| `post_impl_timing` | Post-implementation timing netlist with SDF back-annotation. |

**`--run TIME`** — How long to run the simulation. Default: `all` (run until `$finish`). Any Vivado-compatible time string works (e.g. `1000ns`, `2us`).

**`--uvm TEST`** — Run a specific UVM test by test class name. Passes `+UVM_TESTNAME=TEST` and settings from the matching `[[uvm]]` entry.

```sh
xviv simulate --target tb_top
xviv simulate --target tb_top --run 500ns
xviv simulate --target tb_top --mode post_impl_timing
xviv simulate --target tb_top --uvm smoke_test
```

---

### `build`

Compile a Vitis platform BSP or application. `--platform` and `--app` are mutually exclusive.

```sh
xviv build --platform <name>
xviv build --app      <name> [--info]
```

- `--platform <name>`: Runs `make` in the platform BSP directory.
- `--app <name>`: Runs `make` in the app directory, linking against the BSP. The platform must have been created and built first.
- `--info`: Print ELF section sizes (`size executable.elf`) after a successful app build.

---

### `program`

Download a bitstream and/or ELF to an FPGA over JTAG using XSCT.

```sh
# From a platform + app (recommended)
xviv program --platform <name> --app <name>

# Explicit file paths
xviv program --bitstream path/to/design.bit --elf path/to/firmware.elf

# Only program the bitstream (no soft processor)
xviv program --platform mb_platform
```

**Advanced targeting flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--fpga NAME` | `"xc7a*"` | Glob filter to select the FPGA target in the JTAG chain. |
| `--processor NAME` | `"Microblaze #0*"` | Glob filter for the soft processor target. |
| `--reset-duration MS` | `500` | Milliseconds to hold the soft reset before loading the ELF. |

---

### `processor`

Control a soft processor via JTAG (without re-programming).

```sh
xviv processor --reset
xviv processor --status
```

- `--reset`: Send a soft reset to the processor.
- `--status`: Print the processor's current state and register values.

---

### `search`

Search the Vivado IP catalog by name, partial VLNV, or keyword. `QUERY` is a **positional** argument.

```sh
xviv search <query>
```

```sh
xviv search clk_wiz
xviv search "axi dma"
xviv search fifo
```

Use this to find the correct VLNV string for `[[core]]` entries.

---

### `formal`

Run SymbiYosys formal verification targets.

```sh
xviv formal                     # run all [[formal]] targets
xviv formal --target <name>     # run a specific target
```

`--target` is optional. Without it, all declared `[[formal]]` targets run. On failure, the counterexample path and a ready-to-paste `gtkwave` command are printed.

---

## Recommended Workflows

### Bare RTL Design — First Build

```toml
# project.toml

[[fpga]]
name      = "main"
fpga_part = "xc7a35tcpg236-1"

[[design]]
name    = "top"
sources = ["srcs/rtl/**/*.sv"]

[[synth]]
design      = "top"
constraints = ["constraints/top.xdc"]
```

```sh
# Run synthesis
xviv synth --design top

# Inspect a checkpoint
xviv open --dcp build/synth/top/checkpoints/route.dcp

# Resume from a checkpoint after changing constraints
xviv synth --design top --resume route
```

---

### Custom IP Development Cycle

**1. Declare the IP:**

```toml
[[ip]]
name    = "my_filter"
sources = ["srcs/ip/my_filter/**/*.sv"]
```

**2. Package and open in IP Packager:**

```sh
xviv create --ip my_filter --edit
```

**3. Re-package after source changes:**

```sh
xviv create --ip my_filter
```

**4. Re-package and regenerate all core instances using this IP (in parallel):**

```sh
xviv create --ip my_filter --regenerate
```

**5. If the IP has AXI/AXI-Stream interfaces that need a wrapper:**

```toml
[[wrapper]]
ip      = "my_filter"
sources = ["srcs/ip/my_filter/**/*.sv"]
```

```sh
xviv create --ip my_filter
```

**6. Instantiate the IP as a catalog core:**

```toml
[[core]]
name = "my_filter_0"
vlnv = "xviv.org:xviv:my_filter:1.0"
```

```sh
xviv create --core my_filter_0 --generate
```

---

### Block Design Workflow

**1. Declare the BD:**

```toml
[[fpga]]
name       = "pynq"
board_part = "tul.com.tw:pynq-z2:part0:1.0"

[[bd]]
name = "system"

[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
```

**2. Create a new BD and open the GUI:**

```sh
xviv create --bd system
```

Build your block design in the Vivado IP Integrator. When done, export the TCL snapshot from Vivado and commit it.

**3. On another machine (or after a fresh clone), recreate the BD:**

```sh
# Import from TCL snapshot, no GUI, no generate
xviv create --bd system --nogui

# Import and generate output products
xviv create --bd system --generate
```

**4. Re-open the BD for editing:**

```sh
xviv edit --bd system
```

**5. Regenerate output products after an edit:**

```sh
xviv generate --bd system
```

**6. Synthesise the BD with parallel OOC sub-core synthesis:**

```sh
xviv synth --bd system --parallel
```

---

### Embedded MicroBlaze Workflow

```toml
[[fpga]]
name       = "arty"
board_part = "digilentinc.com:arty-a7-35:part0:1.0"

[[bd]]
name = "mb_system"

[[synth]]
bd          = "mb_system"
constraints = ["constraints/mb_system.xdc"]

[[platform]]
name = "mb_platform"
bd   = "mb_system"
cpu  = "microblaze_0"
os   = "standalone"

[platform.properties.CONFIG]
stdout = "mdm_1"
stdin  = "mdm_1"

[[app]]
name     = "firmware"
platform = "mb_platform"
template = "empty_application"
sources  = ["srcs/sw/main.c"]
```

```sh
# 1. Create/recreate the BD from the TCL snapshot
xviv create --bd mb_system --nogui

# 2. Synthesise — produces mb_system.bit and mb_system.xsa
xviv synth --bd mb_system

# 3. Create the Vitis BSP
xviv create --platform mb_platform

# 4. Compile the BSP
xviv build --platform mb_platform

# 5. Create the app workspace
xviv create --app firmware

# 6. Build the ELF
xviv build --app firmware --info

# 7. Program the board
xviv program --platform mb_platform --app firmware

# Subsequent firmware-only iterations:
# Edit srcs/sw/main.c, then:
xviv build --app firmware
xviv program --platform mb_platform --app firmware

# Or reset the processor without reprogramming the FPGA:
xviv processor --reset
```

---

### Simulation Workflow

**xsim (default):**

```toml
[[simulation]]
name    = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
```

```sh
# Run to completion
xviv simulate --target tb_top

# Run for a fixed duration
xviv simulate --target tb_top --run 2000ns

# Open the waveform
xviv open --wdb tb_top

# Hot-reload after re-running (keeps the waveform viewer open)
xviv simulate --target tb_top
xviv reload --target tb_top
```

**Post-implementation timing simulation:**

```toml
[[synth]]
design                 = "top"
constraints            = ["constraints/top.xdc"]
impl_timing_netlist    = true   # enables SDF generation too

[[simulation]]
name    = "tb_top_timing"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
sdfmax  = ["tb_top/dut"]
```

```sh
xviv synth --design top
xviv simulate --target tb_top_timing --mode post_impl_timing
```

**UVM with xsim:**

```toml
[[simulation]]
name        = "tb_axi_vip"
sources     = ["srcs/sim/tb_axi_vip.sv"]
uvm_version = "1.2"

[[uvm]]
simulation = "tb_axi_vip"
test       = "axi_write_test"
verbosity  = "UVM_MEDIUM"
```

```sh
xviv simulate --target tb_axi_vip --uvm axi_write_test
```

---

### Formal Verification Workflow

```toml
[[formal]]
name    = "counter_props"
top     = "counter"
mode    = "prove"
depth   = 30
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_props.sv"]
defines = ["FORMAL"]
```

```sv
`ifdef FORMAL
    property p_no_overflow;
        @(posedge clk) count < MAX;
    endproperty
    assert property (p_no_overflow);
`endif
```

```sh
# Run all formal targets
xviv formal

# Run a specific target
xviv formal --target counter_props

# Dry-run to inspect the generated .sby file
xviv formal --target counter_props --dry-run
```

---

### Incremental / Resume Builds

**1. Vivado incremental synthesis/implementation** (automatic):

Enabled by `synth_incremental = true` and `impl_incremental = true` in `[[synth]]` (both default to true). Happens transparently on every subsequent `xviv synth` run.

**2. Stage-level resume** (explicit):

```sh
# Detect the latest existing checkpoint automatically
xviv synth --design top --resume auto

# Restart from opt_design (synth checkpoint exists)
xviv synth --design top --resume synth

# Restart from phys_opt_design (place checkpoint exists)
xviv synth --design top --resume place

# Re-run only write_bitstream (route checkpoint exists)
xviv synth --design top --resume route
```

---

### Team / Clean-Clone Workflow

Recommended `.gitignore`:

```gitignore
build/
*.log
.env
```

What to commit:

- `project.toml` — the entire project declaration
- `project.toml` — the entire project declaration
- `scripts/xviv/bd/*.tcl` — BD TCL snapshots (**critical — do not ignore**)

After a fresh clone:

```sh
# RTL-only design
xviv synth --design top

# Design with block designs
xviv create --bd system --nogui
xviv synth --bd system

# Design with embedded firmware
xviv create --bd mb_system --nogui
xviv synth --bd mb_system
xviv create --platform mb_platform
xviv build --platform mb_platform
xviv create --app firmware
xviv build --app firmware
```

---

## Shell Completion

xviv supports dynamic tab completion via `argcomplete`:

```sh
# System-wide (bash, zsh, fish)
activate-global-python-argcomplete

# Per-shell (bash)
eval "$(register-python-argcomplete xviv)"

# Add to your .bashrc / .zshrc for persistence
echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.bashrc
```

Completions include:
- IP, BD, design, simulation, core, platform, app, and formal names from `project.toml`
- VLNV strings for `[[core]]` entries from the live Vivado IP catalog with descriptions
- DCP checkpoint paths from known synth output locations
- UVM test names filtered to the selected simulation target
- Bitstream and ELF paths from known output locations

---

## Git Traceability — USR_ACCESS Embedding

Every time you run `xviv synth` (for designs and BDs), the current git commit SHA is embedded into the bitstream's `USR_ACCESS` register:

- **Bits [27:0]**: Lower 28 bits of the short commit SHA (hex).
- **Bit 28**: Set to `1` if the working tree had uncommitted changes at build time (dirty flag).

To disable embedding: set `usr_access_value = 0` in `[[synth]]`.

xviv warns you at synthesis time if the working tree is dirty. It is **strongly recommended** to commit all changes before a production build.

---

## Dry-Run and TCL Inspection

Every command supports `--dry-run`. This generates the full TCL script(s) that would be passed to Vivado/XSCT and prints them to stdout, without executing anything.

```sh
xviv synth --design top --dry-run
xviv create --bd system --nogui --dry-run
xviv build --platform mb_platform --dry-run
xviv formal --target counter_props --dry-run
```

---

## Logging

xviv uses Python's standard `logging` module. By default, `INFO` and above is printed to stdout with coloured level names. Error, warning, and critical log message bodies are also coloured.

The debug log is written to `build/log/xviv.log` by default. Override with `log_file` in `[project]` or `--config`. The log file is overwritten each run (mode `"w"`).

Parallel job logs are written separately to `build/log/job_synth_<core>.log` per sub-core.

---

## Lock File

Every command run generates `project.lock` at the project root. This is a TOML snapshot of the fully-resolved configuration - globs expanded, defaults applied, paths made absolute then re-expressed relative to the project root. It serves as an audit trail and is useful for debugging configuration issues.

The lock file is written before any Vivado/XSCT invocations.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `XVIV_VIVADO_SOURCE_SCRIPT` | Path to the Vivado `settings64.sh` script. Read from `.env` or the shell environment. xviv sources this automatically if `vivado` is not on PATH. |

No other environment variables are read by xviv itself. Vivado and Vitis read their own standard variables from the sourced settings script.

---

## Annotated Full project.toml Examples

### Example 1: Multi-IP RTL Design with Reports

```toml
[project]
work_dir = "build"

[[fpga]]
name      = "main"
fpga_part = "xc7a200tfbg484-1"

# Custom AXI filter IP
[[ip]]
name    = "axi_filter"
sources = ["srcs/ip/axi_filter/**/*.sv"]
vendor  = "myorg"
library = "dsp"

# Wrapper for interface inference (requires pyslang)
[[wrapper]]
ip      = "axi_filter"
sources = ["srcs/ip/axi_filter/**/*.sv"]

# Instantiate a clock wizard
[[core]]
name = "clk_wiz_0"
vlnv = "clk_wiz:6.0"

# Top-level RTL design
[[design]]
name    = "top"
sources = [
    "srcs/rtl/**/*.sv",
    "srcs/rtl/**/*.v",
    { files = ["srcs/rtl/tb_only.sv"], used_in = ["sim"] },
]

# Synthesis run with reports
[[synth]]
design      = "top"
constraints = ["constraints/top.xdc", "constraints/timing.xdc"]

run_route                   = true
route_report_timing_summary = true
route_report_drc            = true
route_report_power          = true

synth_directive  = "AreaOptimized_high"
place_directive  = "ExplorePostRoutePhysOpt"

# Simulation
[[simulation]]
name    = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
backend = "xsim"
defines = ["SIM=1"]
```

---

### Example 2: PYNQ-Z2 System with Embedded MicroBlaze

```toml
[project]
work_dir = "build"

[[fpga]]
name       = "pynq"
board_part = "tul.com.tw:pynq-z2:part0:1.0"

# Custom accelerator IP
[[ip]]
name    = "systolic_array"
sources = ["srcs/ip/systolic_array/**/*.sv"]
fpga    = "pynq"

# Block design
[[bd]]
name  = "system"
fpga  = "pynq"

# Synthesis — produces .bit and .xsa
[[synth]]
bd          = "system"
fpga        = "pynq"
constraints = ["constraints/system.xdc"]

route_report_timing_summary = true

# Embedded platform (BSP)
[[platform]]
name = "mb_platform"
bd   = "system"
cpu  = "microblaze_0"
os   = "standalone"

[platform.properties.CONFIG]
stdout = "mdm_1"
stdin  = "mdm_1"

# Firmware application
[[app]]
name     = "inference_engine"
platform = "mb_platform"
template = "empty_application"
sources  = ["srcs/sw/**/*.c", "srcs/sw/**/*.h"]

# Testbench
[[simulation]]
name    = "tb_systolic"
sources = ["srcs/sim/tb_systolic.sv", "srcs/ip/systolic_array/**/*.sv"]
backend = "xsim"
```

---

### Example 3: Formal Verification with Multiple Targets

```toml
[project]
work_dir = "build"

[[fpga]]
name      = "main"
fpga_part = "xc7a35tcpg236-1"

[[design]]
name    = "counter"
sources = ["srcs/rtl/counter.sv"]

[[synth]]
design      = "counter"
constraints = ["constraints/counter.xdc"]

# Prove the counter never overflows
[[formal]]
name    = "counter_no_overflow"
top     = "counter"
mode    = "prove"
depth   = 50
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_props.sv"]
defines = ["FORMAL"]

# BMC check for reset behaviour
[[formal]]
name    = "counter_reset_bmc"
top     = "counter"
mode    = "bmc"
depth   = 20
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_reset_props.sv"]
defines = ["FORMAL"]
engine  = "smtbmc z3"

# Cover: can the counter reach its maximum value?
[[formal]]
name    = "counter_cover"
top     = "counter"
mode    = "cover"
depth   = 60
append  = 10
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_cover.sv"]
defines = ["FORMAL"]
```

```sh
# Run all three targets
xviv formal

# Run only the prove target
xviv formal --target counter_no_overflow
```