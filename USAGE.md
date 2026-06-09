# xviv — Complete Usage Guide

> Commit `6ca6a3338f9a883ab13ac42f5f7470ad7c51c2a3` · Python ≥ 3.11 · [github.com/laperex/xviv](https://github.com/laperex/xviv)

A comprehensive reference for building, simulating, and verifying Xilinx/AMD FPGA projects with
xviv: philosophy, installation, full schema, every command, recommended workflows, constraint
validation, troubleshooting, known limitations, and notes for AI tools assisting with project
development.

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
   - [simulate](#simulate-1)
   - [open](#open)
   - [reload](#reload)
   - [build](#build-1)
   - [program](#program-1)
   - [processor](#processor-1)
   - [search](#search-1)
   - [formal](#formal-1)
   - [validate](#validate)
7. [Command Prerequisites and State Dependencies](#command-prerequisites-and-state-dependencies)
8. [Recommended Workflows](#recommended-workflows)
   - [Bare RTL Design — First Build](#bare-rtl-design--first-build)
   - [Custom IP Development Cycle](#custom-ip-development-cycle)
   - [Block Design Workflow](#block-design-workflow)
   - [Embedded MicroBlaze Workflow](#embedded-microblaze-workflow)
   - [Simulation Workflow](#simulation-workflow)
   - [UVM Simulation Workflow](#uvm-simulation-workflow)
   - [Formal Verification Workflow](#formal-verification-workflow)
   - [XDC Constraint Validation Workflow](#xdc-constraint-validation-workflow)
   - [Incremental and Resume Builds](#incremental-and-resume-builds)
   - [Team and Clean-Clone Workflow](#team-and-clean-clone-workflow)
9. [Shell Completion](#shell-completion)
10. [Git Traceability — USR_ACCESS Embedding](#git-traceability--usr_access-embedding)
11. [Dry-Run and TCL Inspection](#dry-run-and-tcl-inspection)
12. [Logging and Output Format](#logging-and-output-format)
13. [Lock File](#lock-file)
14. [Environment Variables](#environment-variables)
15. [Missing Features and Known Limitations](#missing-features-and-known-limitations)
16. [Troubleshooting](#troubleshooting)
17. [Notes for AI Tools](#notes-for-ai-tools)
18. [Annotated project.toml Examples](#annotated-projecttoml-examples)

---

## Philosophy

xviv is a **declarative, CLI-first project controller** for Xilinx/AMD Vivado and Vitis. The
entire build — FPGA target, custom IPs, block designs, RTL sources, synthesis runs, simulations,
and embedded firmware — is described in a single `project.toml`. Running any command from a clean
clone reproduces the project identically. The `build/` directory is fully gitignored and always
regenerable.

Key design decisions:

- **Non-project / batch-mode Vivado.** xviv never creates a `.xpr` project file. It generates TCL
  scripts and runs Vivado in batch mode. The repository stays clean; CI is trivial.
- **Block designs are TCL snapshots.** After editing a BD in the GUI, xviv writes a re-runnable
  TCL script under `scripts/xviv/bd/`. This file is committed and reviewed like any other source.
  `create --bd` recreates the BD from scratch on any machine.
- **Git traceability.** Synthesis embeds the short git SHA into the bitstream `USR_ACCESS` field.
  Bit 28 is set when the working tree was dirty. Any `.bit` file traces back to the exact commit.
- **Vivado-free validation.** `xviv validate` cross-references XDC constraints against RTL port
  declarations using Python's built-in Tcl engine and `pyslang` — no Vivado license needed.
- **GUI for what actually needs it.** BD editing and IP packaging benefit from the Vivado GUI.
  Everything else runs from the terminal.

---

## Installation

```sh
pip install xviv
```

Requirements:

- **Python 3.11+**
- **Vivado** (tested: 2024.1, 2024.2) — for synthesis, simulation, IP packaging, programming
- **Vitis / XSCT** — for embedded platform/app flows only
- **SymbiYosys (`sby`)** — for `[[formal]]` targets only (Vivado not required)
- **Verilator** — for `backend = "verilator"` simulation only

`pyslang <= 10.0.0` is a declared dependency (installed automatically). It is required for:
- SV wrapper generation (`[[wrapper]]` sections via `xviv_wrapper`)
- RTL port extraction for XDC constraint validation (`xviv validate`)

For development (editable install with linting and testing):

```sh
git clone https://github.com/laperex/xviv.git
cd xviv
pip install -e ".[dev]"
pre-commit install
```

---

## Tool Discovery

xviv resolves tool locations in this order:

1. **PATH** — if `vivado` (or `xsct`) is already on PATH (e.g. after sourcing `settings64.sh`),
   xviv uses it directly.
2. **`.env` file** — a `.env` at the project root is read first. This is the recommended
   per-project approach.
3. **`XVIV_VIVADO_SOURCE_SCRIPT` environment variable** — if the tool is not on PATH, xviv
   sources this script automatically before invoking anything.

**Recommended setup** — create `.env` at the project root (add to `.gitignore` if machine-specific):

```sh
# .env
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

Or export in your shell profile:

```sh
export XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

**Separate Vitis path** — if Vitis is installed separately from Vivado, set:

```sh
XVIV_VIVADO_DIR=/tools/Xilinx/Vivado/2024.1
XVIV_VITIS_DIR=/tools/Xilinx/Vitis/2024.1
```

---

## Project Layout

```
myproject/
├── project.toml                  # The only file xviv requires — declare everything here
├── project.lock                  # Auto-generated resolved config snapshot (can gitignore)
├── .env                          # Optional: XVIV_VIVADO_SOURCE_SCRIPT=...
├── .gitignore                    # Must include: build/
│
├── srcs/
│   ├── rtl/                      # Synthesisable RTL (.sv, .v, .vhd)
│   ├── ip/                       # Custom IP source trees
│   ├── sim/                      # Testbenches and simulation-only files
│   ├── formal/                   # Property files for SymbiYosys
│   └── sw/                       # Embedded software (C/C++)
│
├── constraints/                  # XDC constraint files
│
├── scripts/
│   └── xviv/
│       └── bd/
│           └── <name>.tcl        # BD TCL snapshot — VERSION CONTROL THIS
│
└── build/                        # Gitignore everything here; fully regenerable
    ├── log/
    │   └── xviv.log              # Debug log (overwritten each run)
    ├── ip/                       # Packaged custom IP repositories
    ├── core/                     # Instantiated catalog IP XCI files
    ├── bd/                       # Generated BD Vivado output products
    ├── wrapper/                  # Generated SV wrapper files
    ├── synth/
    │   └── <name>/
    │       ├── checkpoints/      # synth.dcp, place.dcp, route.dcp
    │       ├── reports/          # .rpt files (timing, DRC, power, utilization)
    │       ├── netlists/         # functional/timing netlists, SDF
    │       ├── <name>.bit        # Bitstream
    │       └── <name>.xsa        # Hardware platform for Vitis
    ├── sim/
    │   └── <name>/               # Per-simulation xsim/verilator work directory
    ├── formal/
    │   └── <name>/               # SymbiYosys task directory
    ├── platform/
    │   └── <name>/               # Vitis BSP output
    └── app/
        └── <name>/               # Vitis application; executable.elf lands here
```

**What to version-control:**

| Path | Commit? | Notes |
|------|---------|-------|
| `project.toml` | ✅ always | Source of truth |
| `scripts/xviv/bd/*.tcl` | ✅ always | BD snapshots — loss = BD must be rebuilt from scratch |
| `project.lock` | optional | Useful for CI reproducibility |
| `constraints/` | ✅ always | |
| `srcs/` | ✅ always | |
| `.env` | ❌ no | Machine-specific paths |
| `build/` | ❌ no | Fully regenerable |

---

## project.toml — Full Schema Reference

All sections except `[project]` are **arrays of tables** (`[[section]]`). Multiple entries of the
same type are allowed. The first `[[fpga]]` is the default used by all entities that omit
`fpga = "name"`.

xviv parses `project.toml` with Python's `tomllib`. Only valid TOML 1.0 syntax is accepted.

---

### `[project]`

Optional. All keys have defaults.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `work_dir` | string | `"build"` | Root directory for all generated outputs. |
| `log_file` | string | `"<work_dir>/log/xviv.log"` | Debug log file path. |
| `board_repo` | list[string] | `[]` | Additional board repo paths for `board_part` resolution. |
| `ip_repo` | list[string] | `[]` | Additional IP repo paths. `build/ip` is always included. |

```toml
[project]
work_dir   = "build"
board_repo = ["/opt/Xilinx/board_files"]
ip_repo    = ["/opt/myorg_ip_repo"]
```

---

### `[[fpga]]`

At least one entry required. The first is the default FPGA target.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | ✅ | Unique identifier. Referenced by other sections via `fpga = "name"`. |
| `fpga_part` | string | one of | Full Xilinx part number, e.g. `"xc7a200tfbg484-1"`. |
| `board_part` | string | one of | Board part string, e.g. `"digilentinc.com:arty-a7-35:part0:1.0"`. |

Exactly one of `fpga_part` or `board_part` must be set.

```toml
[[fpga]]
name      = "main"
fpga_part = "xc7a200tfbg484-1"

[[fpga]]
name       = "pynq"
board_part = "tul.com.tw:pynq-z2:part0:1.0"
```

---

### `[[design]]`

Declares an RTL design: sources + top module. Referenced by `[[synth]]` and `[[simulation]]`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. Also the default top module name. |
| `sources` | list | ✅ | | Source file globs or structured source entries. |
| `top` | string | | same as `name` | Top-level module name. |
| `fpga` | string | | first `[[fpga]]` | FPGA target reference. |

**Structured source entries** allow per-stage filtering with `used_in`:

```toml
[[design]]
name = "top"
top  = "top_module"
sources = [
    "srcs/rtl/**/*.sv",
    "srcs/rtl/**/*.v",
    { files = ["srcs/rtl/debug_probe.sv"], used_in = ["sim"] },
    { files = ["srcs/rtl/ooc_only.sv"],    used_in = ["ooc"] },
]
```

Valid `used_in` values: `"synth"`, `"impl"`, `"ooc"`, `"sim"`. A bare glob string is included in
all stages.

---

### `[[ip]]`

Custom IP to be packaged by Vivado's IP Packager. Outputs land in `build/ip/`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. Also the default top module name and VLNV `name` field. |
| `sources` | list | ✅ | | RTL sources (globs or structured). |
| `top` | string | | same as `name` | Top module inside the IP. |
| `vendor` | string | | `"xviv.org"` | VLNV vendor field. |
| `library` | string | | `"xviv"` | VLNV library field. |
| `version` | string | | `"1.0"` | VLNV version field. |
| `vlnv` | string | | auto | Override the full VLNV string; supersedes vendor/library/version. |
| `fpga` | string | | first `[[fpga]]` | FPGA target for packaging. |
| `repo` | string | | `"build/ip"` | Override the IP repo output path. |

```toml
[[ip]]
name    = "axi_gamma"
sources = ["srcs/ip/axi_gamma/**/*.sv"]
vendor  = "myorg"
library = "dsp"
version = "2.0"
```

After packaging, the full VLNV is `myorg:dsp:axi_gamma:2.0`. Use this string in `[[core]]`
entries if you want to instantiate the IP.

---

### `[[wrapper]]`

Optional companion to `[[ip]]`. Generates a SystemVerilog wrapper that flattens AXI/AXI-S
interface ports so Vivado's IP Packager can infer them. Requires `pyslang`.

The same `RTLPortExtractor` used by `xviv validate` parses the IP sources.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `ip` | string | ✅ | | Name of the `[[ip]]` to wrap. |
| `sources` | list | ✅ | | Sources that define the interface types. |
| `wrapper_top` | string | | `<ip_top>_wrapper` | Name of the generated wrapper module. |
| `wrapper_file` | string | | `build/wrapper/<wrapper_top>.sv` | Output path. |

```toml
[[wrapper]]
ip      = "axi_gamma"
sources = ["srcs/ip/axi_gamma/**/*.sv"]
```

The generated wrapper is automatically added as a source when `create --ip` runs.

---

### `[[core]]`

Instance of a catalog IP — Xilinx built-in or a previously packaged custom IP. Identified by a
partial VLNV string.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique instance name. Used as the XCI file basename. |
| `vlnv` | string | one of | | Partial or full VLNV. Tab completion resolves against the live catalog. |
| `ip` | string | one of | | Reference a declared `[[ip]]` entry by name instead of a catalog VLNV. |
| `fpga` | string | | first `[[fpga]]` | Target FPGA. |
| `xci_file` | string | | `build/core/<name>/<name>.xci` | Override the XCI output path. |

```toml
[[core]]
name = "clk_wiz_0"
vlnv = "clk_wiz"                          # partial VLNV — xviv resolves against catalog

[[core]]
name = "axi_dma_0"
vlnv = "xilinx.com:ip:axi_dma:7.1"       # full VLNV

[[core]]
name = "my_filter_0"
ip   = "axi_gamma"                        # references a declared [[ip]] entry
```

> **Tip:** use `xviv search <keyword>` to find VLNV strings: `xviv search "axi dma"`.

---

### `[[bd]]`

Block design managed by xviv. First creation opens the GUI; subsequent runs recreate from TCL
snapshot. The TCL snapshot at `scripts/xviv/bd/<name>.tcl` must be committed.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `fpga` | string | | first `[[fpga]]` | FPGA target. |
| `save_file` | string | | `scripts/xviv/bd/<name>.tcl` | TCL snapshot path. Commit this. |
| `bd_file` | string | | `build/bd/<name>/<name>.bd` | Generated `.bd` file path. |
| `bd_wrapper_file` | string | | `build/bd/<name>/hdl/<name>_wrapper.v` | HDL wrapper path. |

When a `.bd` file already exists, xviv parses its embedded IP list and registers each IP as a
`[[core]]` with OOC `[[synth]]` configuration automatically.

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

Declares a synthesis run. Exactly one of `design`, `bd`, or `core` is required.

**Identity:**

| Key | Type | Description |
|-----|------|-------------|
| `design` | string | Name of a `[[design]]` to synthesise. |
| `bd` | string | Name of a `[[bd]]` to synthesise (wrapper). |
| `core` | string | Name of a `[[core]]` to synthesise out-of-context. |

**Pipeline control (all default to `true`):**

| Key | Default | Description |
|-----|---------|-------------|
| `run_synth` | `true` | Run `synth_design`. |
| `run_opt` | `true` | Run `opt_design`. |
| `run_place` | `true` | Run `place_design`. |
| `run_phys_opt` | `true` | Run `phys_opt_design`. |
| `run_route` | `true` | Run `route_design`. |
| `synth_incremental` | `true` | Use prior synth checkpoint with `-incremental` when available. |
| `impl_incremental` | `true` | Use prior route checkpoint with `-incremental` when available. |

**Output artifacts** (each accepts `true` for default path, `false` to disable, or a string path):

| Key | Default (design/bd) | Default (core) | Description |
|-----|---------------------|----------------|-------------|
| `synth_dcp` | `true` | `true` | Checkpoint after `synth_design`. |
| `place_dcp` | `true` | `false` | Checkpoint after `place_design`. |
| `route_dcp` | `true` | `false` | Checkpoint after `route_design`. |
| `bitstream` | `true` | `false` | Output `.bit` file. Requires `run_route = true`. |
| `hw_platform` | `true` (bd only) | `false` | `.xsa` for Vitis. Requires `run_route = true`. |
| `synth_stub` | `false` | `true` | Black-box stub `.v` file. |
| `synth_functional_netlist` | `false` | `false` | Post-synth functional netlist. |
| `synth_timing_netlist` | `false` | `false` | Post-synth timing netlist. |
| `impl_functional_netlist` | `false` | `false` | Post-impl functional netlist. |
| `impl_timing_netlist` | `false` | `false` | Post-impl timing netlist. |
| `impl_timing_sdf` | auto | auto | SDF; auto-enabled when `impl_timing_netlist = true`. |

**Reports** (same `bool | str` semantics; all default to `false`):

| Key | Description |
|-----|-------------|
| `synth_report_timing_summary` | Post-synth timing summary. |
| `synth_report_utilization` | Post-synth resource utilisation. |
| `route_report_drc` | Post-route DRC report. |
| `route_report_methodology` | Post-route methodology report. |
| `route_report_power` | Post-route power estimate. |
| `route_report_route_status` | Post-route status. |
| `route_report_timing_summary` | Post-route timing summary. |
| `synth_report_incremental_reuse` | Incremental synth reuse statistics. |
| `impl_report_incremental_reuse` | Incremental impl reuse statistics. |

**Directives and synthesis options:**

| Key | Default | Description |
|-----|---------|-------------|
| `synth_directive` | `"default"` | `synth_design -directive` value. |
| `synth_mode` | `"default"` | `"default"` or `"out_of_context"`. Cores always use `"out_of_context"`. |
| `synth_flatten_hierarchy` | `"rebuilt"` | `"rebuilt"`, `"full"`, or `"none"`. |
| `synth_fsm_extraction` | `"auto"` | FSM extraction mode. |
| `opt_directive` | `"default"` | `opt_design -directive`. |
| `place_directive` | `"default"` | `place_design -directive`. |
| `phys_opt_directive` | `"default"` | `phys_opt_design -directive`. |
| `route_directive` | `"default"` | `route_design -directive`. |
| `usr_access_value` | `nil` | Hardcode the `USR_ACCESS` bitstream value. Default: embed git SHA. |
| `fpga` | inherited | Override FPGA target for this run. |
| `constraints` | `[]` | XDC constraint file globs. |
| `top` | from design/bd | Override top module name. |

```toml
[[synth]]
design      = "top"
constraints = ["constraints/top.xdc"]
run_route                   = true
route_report_timing_summary = true
route_report_drc            = true
synth_directive             = "AreaOptimized_high"
place_directive             = "ExplorePostRoutePhysOpt"

[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
hw_platform = true
route_report_timing_summary = true

[[synth]]
core      = "clk_wiz_0"
run_place = false
run_route = false
```

---

### `[[simulation]]`

Declares a simulation target. Supports `xsim` (default) and `verilator` backends.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | ✅ | Unique identifier. Also the default top module name. |
| `sources` | list | ✅ | Testbench + additional sources. |
| `top` | string | same as `name` | Top simulation module. |
| `backend` | string | `"xsim"` | `"xsim"` or `"verilator"`. |
| `timescale` | string | `"1ns/1ps"` | Timescale for xvlog/xelab. |
| `design` | string | | Pull sources from a `[[design]]` for post-synth/impl sim modes. |
| `plusargs` | list[str] | `[]` | `+arg` values passed to xsim or the verilated binary. |
| `defines` | list[str] | `[]` | Preprocessor `-D` flags. |
| `include_dirs` | list[str] | `[]` | Include directories. |
| `uvm` | list | `[]` | Inline UVM test declarations (same schema as `[[uvm]]`, minus `simulation`). |
| `uvm_version` | string | `"1.2"` | Pre-compiled UVM library version (`"1.1d"` or `"1.2"`). |
| `uvm_verbosity` | string | `"UVM_MEDIUM"` | Default UVM verbosity. |
| `uvm_max_quit_count` | int | `null` | Max UVM errors before abort. |
| `sdfmax` | list[str] | `[]` | SDF max-delay instance paths for timing back-annotation. |
| `sdfmin` | list[str] | `[]` | SDF min-delay instance paths. |

**Verilator-specific keys:**

| Key | Default | Description |
|-----|---------|-------------|
| `threads` | `1` | Number of Verilator threads. |
| `trace` | `false` | Enable VCD trace output. |
| `trace_fst` | `false` | Enable FST trace (preferred over VCD for large designs). |
| `trace_depth` | `null` | Trace hierarchy depth limit. |
| `verilator_args` | `[]` | Extra arguments passed verbatim to `verilator`. |
| `uvm_pkg_dir` | `null` | Path to a Verilator-compatible UVM package root (required for UVM with Verilator). |

```toml
[[simulation]]
name    = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
backend = "xsim"
defines = ["SIM=1"]

[[simulation]]
name       = "tb_fast"
sources    = ["srcs/sim/tb_top.sv", "srcs/rtl/**/*.sv"]
backend    = "verilator"
trace_fst  = true
threads    = 4
```

---

### `[[uvm]]`

UVM test configuration attached to a `[[simulation]]`. Multiple entries per simulation.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `test` | string | ✅ | | UVM test class name (`+UVM_TESTNAME=<test>`). |
| `simulation` | string | ✅ | | Name of the `[[simulation]]` this test belongs to. |
| `top` | string | | sim `top` | Override top module for this test. |
| `timescale` | string | | sim `timescale` | Override timescale. |
| `verbosity` | string | | sim `uvm_verbosity` | Override UVM verbosity. |
| `version` | string | | sim `uvm_version` | Override UVM library version. |
| `max_quit_count` | int | | sim value | Override `UVM_MAX_QUIT_COUNT`. |

```toml
[[uvm]]
simulation = "tb_top"
test       = "smoke_test"
verbosity  = "UVM_LOW"

[[uvm]]
simulation     = "tb_top"
test           = "stress_test"
verbosity      = "UVM_NONE"
max_quit_count = 5
```

Tests can also be declared inline inside `[[simulation]]`:

```toml
[[simulation]]
name = "tb_top"
sources = ["srcs/sim/tb_top.sv"]
uvm = [
  { test = "smoke_test",  verbosity = "UVM_LOW"  },
  { test = "stress_test", verbosity = "UVM_NONE" },
]
```

---

### `[[platform]]`

Vitis embedded platform. Generates a BSP from the `.xsa` produced by synthesis.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `bd` | string | one of | | Derive XSA + bitstream from a `[[bd]]` synth output. |
| `design` | string | one of | | Derive XSA + bitstream from a `[[design]]` synth output. |
| `xsa` | string | one of | | Explicit path to an `.xsa` file. |
| `bitstream` | string | | auto | Explicit path to a `.bit` file. |
| `cpu` | string | `"microblaze_0"` | CPU instance name in the block design. |
| `os` | string | `"standalone"` | OS type for BSP generation. |
| `properties` | dict | `{}` | BSP property overrides (nested TOML → `CONFIG.key = value`). |

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

Supported `os` values: `"standalone"`, `"freertos10_xilinx"`, others from the Xilinx BSP catalog.

---

### `[[app]]`

Vitis software application built against a platform.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `platform` | string | ✅ | | Name of the `[[platform]]` to build against. |
| `template` | string | `"empty_application"` | Vitis app template. |
| `sources` | list | `[]` | C/C++ source files to add to the app. |

Common templates: `"empty_application"`, `"hello_world"`, `"lwip_echo_server"`,
`"peripheral_tests"`.

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

Formal verification target using SymbiYosys. Vivado is **not** required.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | ✅ | | Unique identifier. |
| `top` | string | ✅ | | Top module to verify. |
| `mode` | string | ✅ | | `"bmc"`, `"prove"`, or `"cover"`. |
| `sources` | list[str] | ✅ | | RTL sources + property files. |
| `depth` | int | `20` | | Bound depth in cycles. |
| `append` | int | `0` | | Extra cycles appended to cover traces. |
| `engine` | string | `"smtbmc yices z3"` | | SymbiYosys engine string. |
| `defines` | list[str] | `[]` | | Preprocessor defines. |
| `include_dirs` | list[str] | `[]` | | Include directories. |
| `multiclock` | bool | `false` | | Enable multi-clock mode. |
| `async2sync` | bool | `false` | | Apply `async2sync` transformation. |
| `sv` | bool | `true` | | Parse sources as SystemVerilog. |
| `extra_script` | list[str] | `[]` | | Extra lines for the `[script]` section of the `.sby` file. |
| `extra_opts` | list[str] | `[]` | | Extra lines for the `[options]` section. |

Available engine strings: `"smtbmc yices"`, `"smtbmc yices z3"`, `"smtbmc z3"`,
`"smtbmc boolector"`, `"smtbmc bitwuzla"`, `"btor"`, `"abc pdr"`.

```toml
[[formal]]
name    = "gamma_props"
top     = "gamma_axi"
mode    = "prove"
depth   = 40
sources = [
    "srcs/ip/gamma_axi/gamma_axi.sv",
    "srcs/formal/gamma_axi_props.sv",
]
defines = ["FORMAL"]
```

Standard `FORMAL`-guarded property pattern:

```sv
`ifdef FORMAL
  // SVA property
  property p_no_overflow;
    @(posedge clk) disable iff (!rst_n)
      count < MAX_VALUE;
  endproperty
  assert property (p_no_overflow);
`endif
```

---

## Command Reference

All commands are invoked as `xviv <subcommand> [flags]`. The config file is auto-discovered
(`project.toml` in the current directory) or specified explicitly with `--config`.

### Global Flags

| Flag | Description |
|------|-------------|
| `--config FILE` / `-c FILE` | Path to `project.toml`. Default: `./project.toml`. |
| `--dry-run` | Print generated TCL to stdout; do not execute Vivado/XSCT/sby. |
| `--check` | Verify generated TCL outputs. |

---

### `create`

Create a custom IP, block design, catalog core, Vitis platform, or Vitis app.

```sh
xviv create --ip <name>       [--edit] [--nogui] [--regenerate]
xviv create --bd <name>       [--source-file FILE|true|false] [--generate] [--edit] [--nogui]
xviv create --core <name>     [--generate] [--edit] [--nogui]
xviv create --platform <name> [--build]
xviv create --app <name>      [--platform <name>] [--build]
```

**`--ip <name>`** — Packages the IP using Vivado IP Packager.
- `--edit` — Open the IP Packager GUI after packaging.
- `--nogui` — Run the packager in TCL batch mode (no GUI).
- `--regenerate` — After packaging, regenerate all `.xci` instances whose VLNV resolves to this
  IP, in parallel. Skips cores without an existing XCI file.

**`--bd <name>`** — Create or recreate a block design.
- Without `--source-file`: Creates a new empty BD and opens the GUI.
- `--source-file true` (default): Recreates from `scripts/xviv/bd/<name>.tcl` if it exists.
- `--source-file <path>`: Recreates from the specified TCL file.
- `--source-file false`: Always opens the GUI even if a snapshot exists.
- `--generate` — Generate output products after import.
- `--edit` — Open the GUI after import for editing.
- `--nogui` — Import from snapshot without opening the GUI.

**`--core <name>`** — Instantiate a catalog IP (creates the XCI file).
- `--generate` — Generate output products immediately.
- `--edit` — Open the IP customisation GUI.

**`--platform <name>`** — Generate the Vitis BSP from the `.xsa`. Requires synthesis to have run.
- `--build` — Also compile the BSP immediately.

**`--app <name>`** — Scaffold a Vitis app from the declared template.
- `--platform <name>` — Override the platform (defaults to value in `[[app]]`).
- `--build` — Also compile immediately.

---

### `edit`

Open an IP, BD, or core in Vivado for interactive editing.

```sh
xviv edit --ip   <name> [--nogui]
xviv edit --bd   <name> [--nogui]
xviv edit --core <name> [--nogui]
```

`--nogui` opens a Vivado TCL console instead of the full GUI. After editing a BD, run
`generate --bd <name>` to regenerate output products.

---

### `generate`

Generate (or re-generate) output products for a block design or catalog core.

```sh
xviv generate --bd   <name> [--force] [--reset]
xviv generate --core <name> [--force] [--reset]
```

- `--force` — Regenerate even if products appear current.
- `--reset` — Reset all output products before generating. Use when products are stale or
  corrupted and `--force` alone does not fix it.

---

### `synth`

Run the synthesis and implementation pipeline.

```sh
xviv synth --design <name> [--resume STAGE] [--parallel]
xviv synth --bd     <name> [--resume STAGE] [--parallel]
xviv synth --core   <name> [--resume STAGE]
```

The stages that run depend on `run_*` flags in `[[synth]]`. Default pipeline:
`synth_design` → `opt_design` → `place_design` → `phys_opt_design` → `route_design` →
`write_bitstream`.

**`--resume STAGE`** — Resume from an existing checkpoint:

| Value | Loads checkpoint | Skips to |
|-------|-----------------|----------|
| `auto` | Latest available | Next stage after that checkpoint |
| `synth` | `synth.dcp` | `opt_design` |
| `place` | `place.dcp` | `phys_opt_design` |
| `route` | `route.dcp` | `write_bitstream` |

**`--parallel`** — Synthesize all registered sub-cores in parallel before the top-level run.
Each sub-core gets its own Vivado batch process. The XCI file for each sub-core must already exist
(`create --core` must have been run). Not applicable to `--core` targets.

The git SHA is embedded into `USR_ACCESS` automatically. Set `usr_access_value` in `[[synth]]` to
override. A warning is printed if the working tree has uncommitted changes.

---

### `simulate`

Compile, elaborate, and run a simulation target.

```sh
xviv simulate --target <name> [--mode MODE] [--run TIME] [--uvm TEST]
```

**`--mode MODE`:**

| Mode | Source | Prerequisite |
|------|--------|-------------|
| `default` | RTL sources directly | None |
| `post_synth_functional` | Post-synth functional netlist | `synth_functional_netlist = true` in `[[synth]]` |
| `post_synth_timing` | Post-synth timing netlist | `synth_timing_netlist = true` |
| `post_impl_functional` | Post-impl functional netlist | `impl_functional_netlist = true` |
| `post_impl_timing` | Post-impl timing netlist + SDF | `impl_timing_netlist = true` |

**`--run TIME`** — Run duration. Default: `all` (run until `$finish`). Examples: `1000ns`, `2us`.

**`--uvm TEST`** — Run a specific UVM test class. Passes `+UVM_TESTNAME=<TEST>` and settings from
the matching `[[uvm]]` entry.

---

### `open`

Open a DCP checkpoint or WDB waveform.

```sh
xviv open --dcp <path>     [--nogui]
xviv open --wdb <sim-name> [--nogui]
```

- `--dcp <path>` — Open a `.dcp` checkpoint in Vivado. Path tab-completes to known checkpoint
  locations under `build/synth/`.
- `--wdb <sim-name>` — Open the `.wdb` waveform for a simulation target.
- `--nogui` — Run in TCL batch mode (headless DCP/snapshot inspection).

---

### `reload`

Hot-reload the waveform snapshot in a live xsim session without restarting.

```sh
xviv reload --target <sim-name>
```

Sends a reload command via a FIFO to a running xsim GUI process. The waveform updates to the
most recent simulation run without closing the viewer. Requires xsim to be open.

---

### `build`

Compile a Vitis platform BSP or application.

```sh
xviv build --platform <name>
xviv build --app      <name> [--info]
```

- `--platform <name>` — Runs `make` in the BSP directory. The platform must have been created with
  `create --platform` first.
- `--app <name>` — Runs `make` in the app directory. The platform must have been built first.
- `--info` — After a successful app build, print ELF section sizes (`size executable.elf`).

---

### `program`

Download a bitstream and/or ELF to the FPGA over JTAG using XSCT.

```sh
xviv program --platform <name> [--app <name>]
xviv program --bitstream <path> [--elf <path>]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--platform <name>` | | Derive bitstream path from `[[platform]]` + `[[synth]]` config. |
| `--app <name>` | | Derive ELF path from `[[app]]` config. |
| `--bitstream <path>` | | Explicit `.bit` path. |
| `--elf <path>` | | Explicit `.elf` path. |
| `--fpga <filter>` | `"xc7a*"` | Glob filter for FPGA target in the JTAG chain. |
| `--processor <filter>` | `"Microblaze #0*"` | Glob filter for soft processor target. |
| `--reset-duration <ms>` | `500` | Milliseconds to hold reset before loading the ELF. |

---

### `processor`

Control a soft processor via JTAG without re-programming.

```sh
xviv processor --reset
xviv processor --status
```

---

### `search`

Search the Vivado IP catalog. `QUERY` is a positional argument.

```sh
xviv search <query>
xviv search clk_wiz
xviv search "axi dma"
xviv search "xilinx.com:ip:fifo"
```

Returns the display name, VLNV string, and a short description for each match. Use the VLNV
output in `[[core]]` entries.

---

### `formal`

Run SymbiYosys formal verification targets. Vivado is not required.

```sh
xviv formal                      # run all [[formal]] targets
xviv formal --target <name>      # run a specific target
```

Multiple targets run in parallel when invoked without `--target`. On failure, the counterexample
VCD path is printed with a ready-to-paste `gtkwave` command. Exits with code `1` if any target
fails.

---

### `validate`

Cross-reference XDC constraint files against RTL port declarations. No Vivado license required.
Uses `tkinter.Tcl` (Python built-in) to evaluate XDC files and `pyslang` to extract RTL ports.

```sh
xviv validate synth --design <name> [--io {short|full}] [--level {error|info}]
xviv validate synth --bd     <name> [--io {short|full}] [--level {error|info}]
```

Exactly one of `--design` or `--bd` is required. `--core` is not yet supported.

| Flag | Description |
|------|-------------|
| `--io short` | Print a summary table: total ports, constrained, unconstrained, unmatched. |
| `--io full` | Print a full per-port table with PIN, IOSTANDARD, timing flags, and status. |
| `--level error` | Show only error rows (unconstrained/unmatched ports). |
| `--level info` | Show all rows (default). |

Before the port table, the command prints: top module, FPGA part, and which pipeline stages are
enabled for the target synth run.

**What is checked:**
- Every RTL port bit is matched against XDC `set_property PACKAGE_PIN` and `IOSTANDARD`
  assignments.
- Timing constraint coverage: `create_clock`, `set_input_delay`, `set_output_delay`,
  `set_false_path`, `set_max_delay`, `set_logic_*`.
- Unmatched XDC targets (constraints referencing ports that do not exist in RTL).
- Vivado-compatible glob wildcards: `[*]` (any bus index), `[?]` (single digit), bare names.

```sh
# Quick check — are there unconstrained ports?
xviv validate synth --design top --io short

# Detailed per-port table
xviv validate synth --design top --io full

# Errors only, suitable for CI
xviv validate synth --design top --io full --level error

# Block design target
xviv validate synth --bd system --io full
```

---

## Command Prerequisites and State Dependencies

The table below shows what must exist before each command can succeed. Run commands in this order
when setting up a project from scratch.

| Command | Requires |
|---------|----------|
| `create --ip` | `[[ip]]` declared in `project.toml`; Vivado on PATH |
| `create --core` | `[[core]]` declared; Vivado on PATH; IP repo populated if `ip =` reference |
| `create --bd` | `[[bd]]` declared; Vivado on PATH; TCL snapshot (`save_file`) for `--nogui` |
| `generate --bd` | `[[bd]]` must exist; BD file (`build/bd/<name>/<name>.bd`) must exist |
| `generate --core` | XCI file must exist (`build/core/<name>/<name>.xci`) |
| `synth --design` | `[[synth]]` with matching `design =`; `[[design]]` sources must exist on disk |
| `synth --bd` | `[[synth]]` with matching `bd =`; BD output products generated |
| `synth --bd --parallel` | All sub-core XCI files must exist (`create --core` for each) |
| `synth --core` | XCI file must exist |
| `simulate` | `[[simulation]]` declared; for non-default modes, matching netlist must exist |
| `open --dcp` | Checkpoint file must exist (result of a prior `synth` run) |
| `open --wdb` | WDB file must exist (result of a prior `simulate` run) |
| `reload` | xsim GUI must be running (opened via `open --wdb`) |
| `create --platform` | `[[platform]]` declared; `.xsa` must exist (product of `synth --bd`) |
| `build --platform` | Platform created with `create --platform` |
| `create --app` | `[[app]]` declared; platform created |
| `build --app` | App created (`create --app`); platform built (`build --platform`) |
| `program` | `.bit` and/or `.elf` must exist; FPGA connected via JTAG; XSCT available |
| `formal` | `[[formal]]` declared; `sby` on PATH; source files must exist |
| `validate synth` | `[[synth]]` with matching target; XDC and RTL source files must exist on disk |
| `search` | Vivado on PATH (queries the live IP catalog) |

**Typical full flow for a BD-based embedded project:**

```
create --bd           →  edit BD in GUI  →  generate --bd
synth --bd                               →  build/synth/system/system.{bit,xsa}
create --platform                        →  build/platform/mb_platform/
build --platform                         →  BSP compiled
create --app                             →  app workspace scaffolded
build --app                              →  build/app/firmware/executable.elf
program --platform mb_platform --app firmware
```

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
route_report_timing_summary = true
```

```sh
# Validate constraints before synthesis (no Vivado needed)
xviv validate synth --design top --io full

# First build
xviv synth --design top

# Open the routed checkpoint to check timing
xviv open --dcp build/synth/top/checkpoints/route.dcp

# After changing constraints only, resume from route checkpoint
xviv synth --design top --resume route

# After changing RTL, resume from synth checkpoint
xviv synth --design top --resume synth

# Preview the generated TCL without running
xviv synth --design top --dry-run
```

---

### Custom IP Development Cycle

**1. Declare the IP and package it:**

```toml
[[ip]]
name    = "my_filter"
sources = ["srcs/ip/my_filter/**/*.sv"]
vendor  = "myorg"
version = "1.0"
```

```sh
xviv create --ip my_filter --edit    # package + open IP Packager GUI
```

**2. If the IP has AXI interface ports, add a wrapper:**

```toml
[[wrapper]]
ip      = "my_filter"
sources = ["srcs/ip/my_filter/**/*.sv"]
```

```sh
xviv create --ip my_filter           # re-package; wrapper is auto-generated first
```

**3. Instantiate as a catalog core:**

```toml
[[core]]
name = "my_filter_0"
ip   = "my_filter"
```

```sh
xviv create --core my_filter_0 --generate
```

**4. After source changes, re-package and regenerate all instances:**

```sh
xviv create --ip my_filter --regenerate
```

**5. OOC synthesis of the core:**

```toml
[[synth]]
core = "my_filter_0"
```

```sh
xviv synth --core my_filter_0
```

---

### Block Design Workflow

```toml
[[fpga]]
name       = "arty"
board_part = "digilentinc.com:arty-a7-35:part0:1.0"

[[bd]]
name = "system"

[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
hw_platform = true
```

```sh
# First time: create a new empty BD and design it in the GUI
xviv create --bd system

# In Vivado: build the BD, then File → Export → Export Block Design → TCL
# The TCL snapshot is automatically saved to scripts/xviv/bd/system.tcl on GUI close.
# Commit it: git add scripts/xviv/bd/system.tcl

# Subsequent builds / clean clones: recreate from snapshot
xviv create --bd system --generate        # recreate + generate output products

# Or in two steps:
xviv create --bd system --nogui           # recreate without generate
xviv generate --bd system                 # generate output products

# Re-open for editing
xviv edit --bd system

# After editing, regenerate
xviv generate --bd system

# Synthesise (parallel OOC sub-core synthesis)
xviv synth --bd system --parallel

# Validate XDC constraints against the BD wrapper's ports
xviv validate synth --bd system --io full
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
hw_platform = true

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
# 1. Recreate BD from snapshot + generate output products
xviv create --bd mb_system --generate

# 2. Synthesise — produces mb_system.bit + mb_system.xsa
xviv synth --bd mb_system

# 3. Create the Vitis BSP from the XSA
xviv create --platform mb_platform

# 4. Compile the BSP
xviv build --platform mb_platform

# 5. Scaffold the app workspace
xviv create --app firmware

# 6. Build the ELF; print section sizes
xviv build --app firmware --info

# 7. Program the board (bitstream + ELF over JTAG)
xviv program --platform mb_platform --app firmware

# --- Firmware-only iteration (no hardware changes) ---
# Edit srcs/sw/main.c, then:
xviv build --app firmware
xviv program --platform mb_platform --app firmware

# Reset the processor without reprogramming the FPGA
xviv processor --reset

# Check processor state
xviv processor --status
```

---

### Simulation Workflow

**RTL simulation with xsim:**

```toml
[[simulation]]
name    = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
defines = ["SIM=1"]
```

```sh
# Run to $finish
xviv simulate --target tb_top

# Run for a fixed duration
xviv simulate --target tb_top --run 2000ns

# Open the waveform viewer
xviv open --wdb tb_top

# Hot-reload after re-running (waveform viewer stays open)
xviv simulate --target tb_top
xviv reload --target tb_top
```

**Post-implementation timing simulation:**

```toml
[[synth]]
design              = "top"
constraints         = ["constraints/top.xdc"]
impl_timing_netlist = true    # enables SDF generation automatically

[[simulation]]
name   = "tb_top_timing"
design = "top"
sources = ["srcs/sim/tb_top.sv"]
sdfmax = ["tb_top/dut"]       # SDF instance path in testbench hierarchy
```

```sh
xviv synth --design top
xviv simulate --target tb_top_timing --mode post_impl_timing
```

**Verilator simulation:**

```toml
[[simulation]]
name      = "tb_fast"
sources   = ["srcs/sim/tb_top.sv", "srcs/rtl/**/*.sv"]
backend   = "verilator"
trace_fst = true
threads   = 4
defines   = ["SIM=1", "VERILATOR=1"]
```

```sh
xviv simulate --target tb_fast
```

---

### UVM Simulation Workflow

```toml
[[simulation]]
name        = "tb_axi_vip"
sources     = ["srcs/sim/tb_axi_vip.sv"]
backend     = "xsim"
uvm_version = "1.2"

[[uvm]]
simulation = "tb_axi_vip"
test       = "axi_write_test"
verbosity  = "UVM_MEDIUM"

[[uvm]]
simulation     = "tb_axi_vip"
test           = "axi_stress_test"
verbosity      = "UVM_NONE"
max_quit_count = 10
```

```sh
# Run a specific UVM test
xviv simulate --target tb_axi_vip --uvm axi_write_test

# Run another test (same simulation, different test class)
xviv simulate --target tb_axi_vip --uvm axi_stress_test
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
engine  = "smtbmc yices z3"
```

```sv
// srcs/formal/counter_props.sv
`ifdef FORMAL
  default clocking @(posedge clk); endclocking
  default disable iff (!rst_n);

  property p_no_overflow;
    count < MAX_VALUE;
  endproperty
  assert property (p_no_overflow);

  cover property (count == MAX_VALUE - 1);
`endif
```

```sh
# Preview the generated .sby file without running
xviv formal --target counter_props --dry-run

# Run the proof
xviv formal --target counter_props

# On failure, open the counterexample trace:
# gtkwave build/formal/counter_props/engine_0/trace.vcd

# Run all [[formal]] targets
xviv formal
```

---

### XDC Constraint Validation Workflow

Use `validate` early in development and in CI to catch constraint errors before spending time on
synthesis.

```sh
# Quick pass/fail: how many ports are unconstrained?
xviv validate synth --design top --io short

# Full audit: see every port with its assigned PIN, IOSTANDARD, and timing status
xviv validate synth --design top --io full

# CI-friendly: exit non-zero if any ports are unconstrained or unmatched
xviv validate synth --design top --io full --level error

# For a block design target
xviv validate synth --bd system --io full --level error
```

`validate` is safe to run at any time — it requires only the `.xdc` and RTL source files on disk.
No synthesis checkpoints or running Vivado are needed.

**Interpretation of `--io full` output columns:**

| Column | Meaning |
|--------|---------|
| Port | Port name with bit index for buses |
| Dir | `In` / `Out` / `InOut` |
| PIN | Assigned PACKAGE_PIN, or `—` if none |
| STD | IOSTANDARD, or `—` if none |
| Timing | Flags: `CLK` / `IDL` / `ODL` / `FP` / `MD` |
| Status | `OK` (fully constrained) · `WARN` (partial) · `ERROR` (missing pin or standard) |

**Common findings and fixes:**

| Finding | Cause | Fix |
|---------|-------|-----|
| `ERROR` on output ports — no PIN | Output-only ports legitimately may not need PACKAGE_PIN | Add `set_false_path` or `set_output_delay` for clocked outputs |
| Unmatched XDC targets | Constraint references a port that was renamed or removed | Remove or update the XDC `set_property` line |
| Bus bits partially constrained | Only some bits assigned | Check wildcard: use `[*]` glob or list each bit |
| All ports `WARN` with no STD | IOSTANDARD constraint missing | Add `set_property IOSTANDARD LVCMOS33 [get_ports {*}]` |

---

### Incremental and Resume Builds

**Vivado incremental synthesis/implementation** (automatic):

Enabled by default via `synth_incremental = true` and `impl_incremental = true` in `[[synth]]`.
When a prior synth or route DCP exists, Vivado receives it with `-incremental`. This happens
transparently; no CLI flag is needed.

**Stage-level resume** (explicit — skip already-completed stages):

```sh
# Detect the latest existing checkpoint and resume from there
xviv synth --design top --resume auto

# Skip synth_design; resume from opt_design
xviv synth --design top --resume synth

# Skip through place_design; resume from phys_opt_design
xviv synth --design top --resume place

# Re-run only write_bitstream
xviv synth --design top --resume route
```

Use `--resume` when you have changed only constraints (`--resume route`) or only placement
directives (`--resume place`), and you want to avoid re-running earlier stages.

---

### Team and Clean-Clone Workflow

**Recommended `.gitignore`:**

```gitignore
build/
*.log
.env
```

**What to commit:**

```
project.toml                  # required
scripts/xviv/bd/*.tcl         # required — loss means BD must be rebuilt from scratch
constraints/                  # required
srcs/                         # required
project.lock                  # optional but useful for CI reproducibility
```

**After a fresh clone — RTL-only project:**

```sh
pip install xviv
cp /path/to/.env .            # set XVIV_VIVADO_SOURCE_SCRIPT
xviv synth --design top
```

**After a fresh clone — BD-based project:**

```sh
pip install xviv
cp /path/to/.env .
xviv create --bd system --generate
xviv synth --bd system
```

**After a fresh clone — embedded project:**

```sh
pip install xviv
cp /path/to/.env .
xviv create --bd mb_system --generate
xviv synth --bd mb_system
xviv create --platform mb_platform
xviv build --platform mb_platform
xviv create --app firmware
xviv build --app firmware
```

---

## Shell Completion

```sh
# System-wide (requires root/sudo)
activate-global-python-argcomplete

# Per-shell (bash)
eval "$(register-python-argcomplete xviv)"

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.bashrc
```

Completions are dynamic and context-aware:

| Argument | Source |
|----------|--------|
| `--ip`, `--bd`, `--design`, `--core` names | Parsed from `project.toml` |
| `--target` (simulate / validate) | Names from `project.toml` |
| `--uvm TEST` | UVM test names filtered to the selected simulation |
| `--dcp PATH` | Known checkpoint paths under `build/synth/` |
| `--platform`, `--app` names | Parsed from `project.toml` |
| VLNV strings in `[[core]]` | Live Vivado IP catalog with inline descriptions |
| `--bitstream` | Known bitstream paths from synth config |
| `--elf` | Known ELF paths from app config |

---

## Git Traceability — USR_ACCESS Embedding

Every `xviv synth` (design / BD targets only; not OOC cores) embeds the current git SHA into the
bitstream `USR_ACCESS` register:

- **Bits [27:0]** — Lower 28 bits of the 7-character short git SHA.
- **Bit 28** — Set to `1` if the working tree had uncommitted changes at build time (dirty flag).

To hard-code a specific value (non-git projects or release tagging):

```toml
[[synth]]
design           = "top"
constraints      = ["constraints/top.xdc"]
usr_access_value = 0xDEADBEEF
```

xviv prints a `WARNING` at synthesis time if the working tree is dirty. **Always commit before a
production build.** In non-git directories with no `usr_access_value` set, synthesis will fail
when trying to write a bitstream.

---

## Dry-Run and TCL Inspection

Every command supports `--dry-run`. The full TCL script that would be passed to Vivado/XSCT/sby
is printed to stdout without executing anything. Use this to:

- Audit what xviv will do before committing to a long synthesis run.
- Debug TOML configuration issues.
- Review the generated TCL for correctness.

```sh
xviv synth --design top --dry-run
xviv create --bd system --nogui --dry-run
xviv build --platform mb_platform --dry-run
xviv simulate --target tb_top --dry-run
xviv formal --target counter_props --dry-run
xviv validate synth --design top --io full --dry-run    # prints resolved config, no table
```

---

## Logging and Output Format

### Console output

xviv uses Python's standard `logging` module. The default level is `INFO`.

- `INFO` messages are printed without a level prefix.
- `WARNING` messages are printed in yellow.
- `ERROR` and `CRITICAL` messages are printed in red.
- Colour is automatically disabled when stdout is not a TTY (`NO_COLOR` env var also respected).
  Force colour with `FORCE_COLOR=1`.

### Vivado output

When Vivado runs, its stdout is streamed in real time through a PTY (for interactive/GUI launches)
or pipe (for batch jobs). Lines are classified:

| Vivado prefix | Log level | Color |
|--------------|-----------|-------|
| `ERROR:` | ERROR | Red |
| `CRITICAL WARNING:` | CRITICAL | Red |
| `WARNING:` | WARNING | Yellow |
| `INFO:` | INFO | Default |
| Everything else | DEBUG | Dim |

### Parallel job output

When `--parallel` is used or multiple formal targets run concurrently, each job's output is
grouped and flushed together when the job completes:

```
━━━━━━━━ ooc_synth_core: clk_wiz_0 ━━━━━━━━
[Vivado output here]
OK  clk_wiz_0   finished in 12s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

A failed job shows `FAILED` in red and prints its full output regardless of log level.

### Debug log

The full debug log (all levels including DEBUG) is written to `build/log/xviv.log`. Override
with `log_file` in `[project]`. The file is overwritten each run.

```sh
# Watch the debug log in real time during a synthesis run
tail -f build/log/xviv.log
```

---

## Lock File

`project.lock` is written to the project root at the start of every command. It is a TOML
snapshot of the fully-resolved configuration: globs expanded, defaults applied, all paths
expressed relative to the project root.

**Uses:**

- **Debugging** — diff two lock files to see what changed between runs.
- **CI reproducibility** — commit the lock file to pin glob resolutions.
- **Audit** — the lock records the exact input state that produced a given build.

The lock file is written before any Vivado/XSCT invocation, so it reflects what *will* run even
if the run fails.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `XVIV_VIVADO_SOURCE_SCRIPT` | Path to the Vivado `settings64.sh`. Sourced automatically if `vivado` is not on PATH. Read from `.env` first, then the shell environment. |
| `XVIV_VIVADO_DIR` | Path to the Vivado installation directory (alternative to the source script). |
| `XVIV_VITIS_DIR` | Path to the Vitis installation directory. |
| `NO_COLOR` | Set to any value to disable ANSI color output. |
| `FORCE_COLOR` | Set to `1` to force ANSI color even in non-TTY contexts (e.g. CI logs). |

A `.env` file at the project root is automatically loaded and takes precedence over shell
environment variables.

---

## Missing Features and Known Limitations

The table below lists features that are **not yet implemented** or have **known gaps**. Marked
with: ⚠ Partial · ✗ Not implemented · 🔧 Planned.

### `validate` gaps

| Feature | Status | Notes |
|---------|--------|-------|
| `validate synth --core` | ⚠ Partial | Command accepts `--core` but emits a warning and skips. Only `--design` and `--bd` are functional. |
| VHDL port extraction | ✗ | `RTLPortExtractor` uses pyslang which is SV-only. VHDL ports are not extracted. |
| Multi-file XDC (Tcl packages) | ⚠ | XDC files that `source` other files or use `package require` may fail in the tkinter.Tcl evaluator. |

### Simulation gaps

| Feature | Status | Notes |
|---------|--------|-------|
| DPI-C / C++ testbenches | ✗ | `--dpi-lib` / `--so` flags are not supported. |
| UVM with Verilator backend | ⚠ | Requires `uvm_pkg_dir` to be set; no pre-compiled library included. |
| `[[simulation]]` referencing `bd =` | ⚠ | Field is declared in the schema but not yet wired into source resolution. |
| Verilator lint-only pass | ⚠ | Verilator backend compiles + runs; standalone `--lint-only` mode is not directly invocable via xviv. |

### Synthesis gaps

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-file constraint sets (OOC vs in-context) | ⚠ | Single `constraints` list per `[[synth]]`; separate OOC constraint override not exposed. |
| Synth strategy presets | ✗ | Directives must be set individually; no named strategy bundles (e.g. "Performance_ExplorePostRoutePhysOpt"). |
| Phys opt disable condition | ⚠ | `phys_opt_design` always runs when `run_phys_opt = true`; not conditionally gated on timing failure. |

### IP / Core gaps

| Feature | Status | Notes |
|---------|--------|-------|
| Subcore dependencies for custom IPs | ✗ | A custom IP that internally uses another IP (e.g. `clk_wiz`) cannot declare that dependency in `project.toml`. BD cores get this automatically. |
| IP properties / parameter overrides | ✗ | `[[core]]` VLNV parameters (IP customisation values) cannot be set from `project.toml`. Must be set in the IP Packager GUI and saved. |

### Formal gaps

| Feature | Status | Notes |
|---------|--------|-------|
| `live` mode | ⚠ | `SbyMode.LIVE` constant exists but is not validated/exposed in `[[formal]]`. |
| Parallel targets — ordering | ⚠ | All targets run in parallel when invoked without `--target`; dependency ordering between targets is not supported. |

### Embedded gaps

| Feature | Status | Notes |
|---------|--------|-------|
| QSPI / flash programming | ✗ | `program` only programs via JTAG direct; flash write not supported. |
| Non-MicroBlaze soft cores | ⚠ | `cpu` field accepts any string but only MicroBlaze flows have been tested. |
| Vitis HLS integration | ✗ | HLS projects cannot be declared in `project.toml`. |

### Infrastructure gaps

| Feature | Status | Notes |
|---------|--------|-------|
| ILA / debug core insertion | ✗ | No `create --ila` or `insert_debug_probes` support. |
| Dependency graph command | ✗ | No `graph` command to visualise entity relationships. |
| Remote synthesis dispatch | ✗ | All synthesis runs locally. |
| CI/CD helper commands | ✗ | No built-in `ci` or `check` subcommand beyond `--dry-run`. |
| Windows support | ⚠ | Developed and tested on Linux. FIFO-based `reload` and PTY streaming are POSIX-only. |

---

## Troubleshooting

### Tool not found

**Error:** `ToolBinaryNotFoundError: vivado not found on PATH`

**Cause:** Vivado is not on PATH and `XVIV_VIVADO_SOURCE_SCRIPT` is not set.

**Fix:**
```sh
# Add to .env at project root:
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh

# Or source it manually before running xviv:
source /tools/Xilinx/Vivado/2024.1/settings64.sh
```

---

**Error:** `SettingsFileNotFoundError: settings script not found: /path/to/settings64.sh`

**Cause:** `XVIV_VIVADO_SOURCE_SCRIPT` points to a file that does not exist.

**Fix:** Check the Vivado installation path. Typical locations:
- `/tools/Xilinx/Vivado/<version>/settings64.sh`
- `/opt/Xilinx/Vivado/<version>/settings64.sh`
- `C:\Xilinx\Vivado\<version>\settings64.bat` (Windows — not fully supported)

---

### Config / TOML errors

**Error:** `ProjectConfigTomlFileMissingError`

**Cause:** `project.toml` was not found in the current directory.

**Fix:** Run xviv from the directory containing `project.toml`, or use `--config path/to/project.toml`.

---

**Error:** `SynthDoesNotExistError: SynthConfig not found for: design='top'`

**Cause:** A `[[synth]]` entry with `design = "top"` does not exist in `project.toml`.

**Fix:** Add the entry:
```toml
[[synth]]
design      = "top"
constraints = ["constraints/top.xdc"]
```

---

**Error:** `DesignDoesNotExistError: DesignConfig not found: 'top'`

**Cause:** A `[[design]]` with `name = "top"` does not exist, but is referenced by a `[[synth]]`
or `[[simulation]]`.

**Fix:** Add:
```toml
[[design]]
name    = "top"
sources = ["srcs/rtl/**/*.sv"]
```

---

**Error:** `VlnvResolveError` or `CoreVlnvNotInCatalogError`

**Cause:** A VLNV string in `[[core]]` could not be resolved against the live Vivado IP catalog.

**Fix:** Use `xviv search <keyword>` to find the correct VLNV. Partial VLNVs like `"clk_wiz"` are
supported; the catalog resolves to the latest version. Full VLNVs like
`"xilinx.com:ip:clk_wiz:6.0"` must match exactly.

---

### Synthesis errors

**Error:** `SynthResumeDcpMissingError: checkpoint not found`

**Cause:** `--resume synth` was used but `build/synth/<name>/checkpoints/synth.dcp` does not exist.

**Fix:** Run `xviv synth --design <name>` without `--resume` first to create the checkpoint.

---

**Error:** `SynthBitstreamRequiresRouteError`

**Cause:** `bitstream = true` but `run_route = false` in `[[synth]]`.

**Fix:** Either set `run_route = true`, or set `bitstream = false` if you only want a checkpoint.

---

**Error:** `SynthUsrAccessValueEmbedGitShaError`

**Cause:** The project directory is not a git repository and `usr_access_value` is not set, but a
bitstream is being written.

**Fix:** Either initialise a git repo (`git init && git commit -m "init"`) or set:
```toml
[[synth]]
design           = "top"
constraints      = ["constraints/top.xdc"]
usr_access_value = 0x00000000
```

---

**Vivado reports `ERROR: [Common 17-55] 'set_property' expects at least one object`**

**Cause:** An XDC `set_property` targets a port that does not exist in the netlist (e.g.
`get_ports clk` when the top module has no port named `clk`).

**Fix:** Use `xviv validate synth --design <name> --io full` to find unmatched XDC targets before
synthesis.

---

**Vivado timing fails — negative WNS after route**

This is a design/constraint issue, not an xviv error. Common approaches:
1. Open the routed checkpoint: `xviv open --dcp build/synth/top/checkpoints/route.dcp`
2. In Vivado: Run → Report Timing Summary → identify failing paths.
3. Try a stronger directive:
   ```toml
   [[synth]]
   synth_directive  = "AreaOptimized_high"
   place_directive  = "ExplorePostRoutePhysOpt"
   route_directive  = "AggressiveExplore"
   ```
4. Or resume from the synth checkpoint with a new directive: `xviv synth --design top --resume synth`.

---

### Block design errors

**Error:** `BdDoesNotExistError`

**Cause:** `[[bd]]` entry missing from `project.toml`.

**Fix:** Add a `[[bd]]` section with the correct `name`.

---

**BD recreate fails or produces wrong design**

**Cause:** The TCL snapshot (`scripts/xviv/bd/<name>.tcl`) is out of sync with the expected BD
state, or it was not committed.

**Fix:**
1. If the snapshot exists but is stale: re-open and re-export.
   ```sh
   xviv edit --bd <name>    # make changes in GUI
   # Vivado writes the snapshot on GUI close automatically
   git add scripts/xviv/bd/<name>.tcl
   ```
2. If the snapshot is missing (not committed): recreate the BD from scratch.
   ```sh
   xviv create --bd <name>    # opens GUI — rebuild the BD
   git add scripts/xviv/bd/<name>.tcl
   ```

---

**`generate --bd` fails with stale/corrupted output products**

**Fix:**
```sh
xviv generate --bd <name> --reset    # reset products first
```

---

### Simulation errors

**Error:** `SimDoesNotExistError`

**Fix:** Add a `[[simulation]]` entry with `name = "<target>"` to `project.toml`.

---

**xsim fails: `ERROR: [XSIM 43-3316] No top-level module found`**

**Cause:** The top module name in `[[simulation]]` does not match the module name in the testbench source.

**Fix:** Set `top = "<module_name>"` in `[[simulation]]` explicitly.

---

**xsim fails in post-impl timing mode**

**Cause:** The timing netlist or SDF file was not generated during synthesis.

**Fix:** Set in `[[synth]]`:
```toml
impl_timing_netlist = true    # also auto-enables impl_timing_sdf
```
Then re-run synthesis and simulate again.

---

**Error:** `VerilatorNotFoundError: verilator not found on PATH`

**Fix:** Install Verilator and ensure it is on PATH:
```sh
# Arch Linux
sudo pacman -S verilator
# Ubuntu / Debian
sudo apt install verilator
```

---

**Error:** `UvmPkgDirRequiredError`

**Cause:** `[[simulation]]` uses UVM with `backend = "verilator"` but `uvm_pkg_dir` is not set.

**Fix:** Verilator does not ship a pre-compiled UVM library. Either:
- Use `backend = "xsim"` for UVM simulations.
- Provide a Verilator-compatible UVM source package and set `uvm_pkg_dir = "/path/to/uvm"`.

---

### Formal verification errors

**Error:** `sby: command not found` / `FormalSourceMissingError`

**Cause 1:** SymbiYosys (`sby`) is not installed or not on PATH.

**Fix:** Install SymbiYosys: `pip install symbiyosys` or from your OS package manager.

**Cause 2:** A source file listed in `[[formal]] sources` does not exist on disk.

**Fix:** Check the glob paths and ensure all source files are committed.

---

**Formal proof fails (FAIL / counterexample)**

**Fix flow:**
1. Get the counterexample path from xviv output.
2. `gtkwave <path/to/trace.vcd>` — inspect the trace.
3. If the depth is too small (proof is interrupted): increase `depth` in `[[formal]]`.
4. If a real bug: fix the RTL and re-run.

---

### Validate errors

**Error:** `ImportError: pyslang is required`

**Fix:**
```sh
pip install "pyslang<=10.0.0"
```

---

**`validate` reports all ports as `ERROR` with no PIN or STD**

**Cause:** The XDC file path in `[[synth]] constraints` does not exist or the glob resolves to
nothing.

**Fix:** Check the constraints paths:
```sh
python3 -c "import glob; print(glob.glob('constraints/*.xdc'))"
```

---

**`validate` reports unmatched XDC targets for ports that exist**

**Cause:** Port names in the XDC use a different capitalisation or hierarchy prefix than in the RTL.

**Fix:** In Vivado, port names are case-sensitive. Ensure the XDC uses exactly the same port names
as the SystemVerilog module declaration. Use `--io full` to see what port names were extracted.

---

### Embedded / Vitis errors

**Error:** `PlatformBspDirectoryMissingError`

**Cause:** `build --platform <name>` was run before `create --platform <name>`.

**Fix:** Run in order:
```sh
xviv create --platform <name>
xviv build  --platform <name>
```

---

**XSCT can't find the FPGA target (`FpgaTargetFilterUnspecifiedError`)**

**Cause:** The FPGA target filter `--fpga` does not match the connected device.

**Fix:** Check the device part number on the board and adjust:
```sh
xviv program --platform mb_platform --fpga "xc7a100t*"
```

---

**`program` hangs or times out**

**Cause:** No JTAG device is connected, or the hw_server is not running.

**Fix:**
1. Ensure the board is powered and the USB-JTAG cable is connected.
2. Check that `xhwsvr` / `hw_server` is running (usually started automatically by XSCT).
3. If Vivado Hardware Manager sees the device, XSCT should too.

---

## Notes for AI Tools

This section is written for AI assistants (Claude, Copilot, etc.) helping users develop
xviv-based FPGA projects. It provides a concise mental model of the system.

### Core model

```
project.toml  ──declares──►  entities (fpga, design, ip, core, bd, synth, simulation, ...)
                                  │
                          xviv resolves config
                                  │
                          generates TCL scripts
                                  │
                          runs Vivado / XSCT / sby / pyslang
                                  │
                          outputs land in build/
```

The user **declares intent in `project.toml`**; xviv **acts on it** via CLI commands.

### Entity relationship rules

- Every `[[synth]]`, `[[simulation]]`, `[[core]]`, `[[bd]]`, and `[[platform]]` references back
  to a `[[fpga]]` (explicit `fpga =` or implicit first entry).
- `[[synth]]` references exactly one of `design =`, `bd =`, or `core =`.
- `[[simulation]]` optionally references a `[[design]]` via `design =` (for post-synth sim modes).
- `[[platform]]` references a `[[bd]]`, `[[design]]`, or explicit `xsa =` path.
- `[[app]]` references a `[[platform]]`.
- `[[wrapper]]` references an `[[ip]]` by name.
- `[[uvm]]` references a `[[simulation]]` by name.

### What requires Vivado vs what does not

| Operation | Requires Vivado |
|-----------|----------------|
| `synth`, `create --ip`, `create --bd`, `create --core`, `generate`, `search`, `open --dcp`, `simulate` (xsim), `program` | ✅ Yes |
| `simulate` (verilator) | No (requires verilator) |
| `formal` | No (requires sby + SMT solver) |
| `validate` | **No** (uses tkinter.Tcl + pyslang; pure Python) |
| Parsing / loading `project.toml` | No |
| `--dry-run` on any command | No (generates TCL only; does not execute Vivado) |

### When helping a user set up a project

1. Ask: RTL-only, BD-based, or embedded (MicroBlaze)?
2. Ask: Which part or board? Check the `[[fpga]]` section.
3. Confirm `XVIV_VIVADO_SOURCE_SCRIPT` or equivalent is set.
4. Suggest running `xviv validate synth --design <top> --io short` before synthesis to catch XDC
   issues early.
5. For BD projects: always remind the user to commit `scripts/xviv/bd/<name>.tcl`.

### When debugging a failing synthesis

1. Check `build/log/xviv.log` for the full log.
2. Look for `ERROR:` lines from Vivado — these are the root cause.
3. Common Vivado errors:
   - `[DRC NSTD-1]` → IOSTANDARD not set in XDC. Use `validate` first.
   - `[DRC UCIO-1]` → Unconstrained I/O ports. Use `validate --level error`.
   - `[Place 30-574]` → Device too small. Check `fpga_part` in `[[fpga]]`.
   - `[Synth 8-439]` → Module not found. Check `sources` globs in `[[design]]`.
4. Resume from the last good checkpoint rather than starting over:
   `xviv synth --design <name> --resume auto`

### When helping write `project.toml`

Key rules to validate:

- `[[fpga]]` must have `name` + exactly one of `fpga_part` / `board_part`.
- `[[synth]]` must have exactly one of `design` / `bd` / `core`.
- `[[simulation]]` must have `name` + `sources`.
- `[[formal]]` must have `name`, `top`, `mode`, `sources`.
- `[[platform]]` must have exactly one of `bd` / `design` / `xsa`.
- `[[app]]` must have `name` + `platform`.
- `[[wrapper]]` must have `ip` + `sources`.
- Every reference (`design =`, `bd =`, `core =`, `fpga =`, `platform =`) must match a declared
  entity name in the same file.
- Source globs are relative to the directory containing `project.toml`.
- `constraints` globs are also relative to the project root.

### Generating shell commands for a task

Use the [Command Prerequisites](#command-prerequisites-and-state-dependencies) table to determine
the correct command sequence. Always check whether the prerequisite state exists before suggesting
a command.

Example: if a user asks "how do I simulate post-implementation", the answer requires:
1. `impl_timing_netlist = true` in `[[synth]]`
2. Running `xviv synth --design <name>`
3. A `[[simulation]]` with `sdfmax` instance paths set
4. Running `xviv simulate --target <name> --mode post_impl_timing`

### Schema validation checklist for AI-generated `project.toml`

Before presenting a `project.toml` to a user, verify:

- [ ] At least one `[[fpga]]` entry with `name` and part.
- [ ] All `[[synth]]` entries have `constraints` pointing to files that will exist.
- [ ] `bitstream = true` is only used when `run_route = true`.
- [ ] `hw_platform = true` is only used on `bd =` synth entries.
- [ ] Source globs use forward slashes and are relative to the project root.
- [ ] No duplicate `name` values within the same section type.
- [ ] `[[platform]]` references a `[[bd]]` or `[[design]]` that has a `[[synth]]` entry
  with `hw_platform = true`.

---

## Annotated project.toml Examples

### Example 1: Multi-IP RTL Design

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

# SV wrapper (flattens AXI interface ports for the IP Packager)
[[wrapper]]
ip      = "axi_filter"
sources = ["srcs/ip/axi_filter/**/*.sv"]

# Clock wizard instance
[[core]]
name = "clk_wiz_0"
vlnv = "clk_wiz"

# Top-level RTL — sim-only source filtered out during synthesis
[[design]]
name = "top"
sources = [
    "srcs/rtl/**/*.sv",
    { files = ["srcs/rtl/sim_only.sv"], used_in = ["sim"] },
]

# Full synthesis run with reports
[[synth]]
design      = "top"
constraints = ["constraints/top.xdc", "constraints/timing.xdc"]
run_route                   = true
route_report_timing_summary = true
route_report_drc            = true
route_report_power          = true
synth_directive             = "AreaOptimized_high"
place_directive             = "ExplorePostRoutePhysOpt"

# RTL simulation
[[simulation]]
name    = "tb_top"
design  = "top"
sources = ["srcs/sim/tb_top.sv"]
backend = "xsim"
defines = ["SIM=1"]

# Formal property check
[[formal]]
name    = "filter_props"
top     = "axi_filter"
mode    = "prove"
depth   = 20
sources = ["srcs/ip/axi_filter/axi_filter.sv", "srcs/formal/filter_props.sv"]
defines = ["FORMAL"]
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

# Block design (BD TCL snapshot committed under scripts/xviv/bd/system.tcl)
[[bd]]
name = "system"
fpga = "pynq"

# Synthesis — produces system.bit + system.xsa for Vitis
[[synth]]
bd          = "system"
fpga        = "pynq"
constraints = ["constraints/system.xdc"]
hw_platform                 = true
route_report_timing_summary = true

# Vitis BSP targeting MicroBlaze
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

# Testbench for the accelerator IP
[[simulation]]
name    = "tb_systolic"
sources = ["srcs/sim/tb_systolic.sv", "srcs/ip/systolic_array/**/*.sv"]
backend = "xsim"
```

---

### Example 3: Formal Verification with Multiple Modes

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

# Prove: counter never overflows
[[formal]]
name    = "counter_no_overflow"
top     = "counter"
mode    = "prove"
depth   = 50
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_overflow_props.sv"]
defines = ["FORMAL"]
engine  = "smtbmc yices z3"

# BMC: reset behaviour (faster check)
[[formal]]
name    = "counter_reset"
top     = "counter"
mode    = "bmc"
depth   = 20
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_reset_props.sv"]
defines = ["FORMAL"]
engine  = "smtbmc z3"

# Cover: can the counter reach max value?
[[formal]]
name    = "counter_reach_max"
top     = "counter"
mode    = "cover"
depth   = 60
append  = 10
sources = ["srcs/rtl/counter.sv", "srcs/formal/counter_cover.sv"]
defines = ["FORMAL"]
```

```sh
# Run all three (in parallel)
xviv formal

# Run only the prove target
xviv formal --target counter_no_overflow
```

---

### Example 4: XDC-Constrained Design with Validation in CI

```toml
[[fpga]]
name      = "main"
fpga_part = "xc7a35tcpg236-1"

[[design]]
name    = "blinky"
sources = ["srcs/rtl/blinky.sv"]

[[synth]]
design      = "blinky"
constraints = ["constraints/blinky.xdc"]
```

```sh
# CI pipeline (Makefile / shell):

# Step 1: Validate constraints (no Vivado license needed in CI)
xviv validate synth --design blinky --io full --level error
# Exits 0 if all constrained, 1 if any errors — gates the rest of the pipeline

# Step 2: Full synthesis (only on tagged releases or manually triggered)
xviv synth --design blinky
```

```xdc
# constraints/blinky.xdc
set_property PACKAGE_PIN E3     [get_ports clk]
set_property IOSTANDARD  LVCMOS33 [get_ports clk]
create_clock -period 10.000     [get_ports clk]

set_property PACKAGE_PIN H5     [get_ports {led[0]}]
set_property PACKAGE_PIN J5     [get_ports {led[1]}]
set_property PACKAGE_PIN T9     [get_ports {led[2]}]
set_property PACKAGE_PIN T10    [get_ports {led[3]}]
set_property IOSTANDARD  LVCMOS33 [get_ports {led[*]}]
```
