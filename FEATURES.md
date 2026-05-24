# xviv — Complete Feature Documentation

> Commit `4c16650f835812856621b59b6ba140166cc7b854` · Version 0.2.7  
> CLI project controller for Vivado and Vitis.

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [project.toml Reference](#projecttoml-reference)
   - [\[project\]](#project)
   - [\[\[fpga\]\]](#fpga)
   - [\[\[design\]\]](#design)
   - [\[\[ip\]\]](#ip)
   - [\[\[wrapper\]\]](#wrapper)
   - [\[\[core\]\]](#core)
   - [\[\[bd\]\]](#bd)
   - [\[\[synth\]\]](#synth)
   - [\[\[simulation\]\]](#simulation)
   - [\[\[uvm\]\]](#uvm)
   - [\[\[formal\]\]](#formal)
   - [\[\[platform\]\]](#platform)
   - [\[\[app\]\]](#app)
4. [CLI Commands](#cli-commands)
   - [create](#create)
   - [edit](#edit)
   - [generate](#generate)
   - [synth](#synth-command)
   - [simulate](#simulate)
   - [open](#open)
   - [reload](#reload)
   - [build](#build)
   - [program](#program)
   - [processor](#processor)
   - [search](#search)
   - [formal](#formal-command)
5. [Global CLI Flags](#global-cli-flags)
6. [Environment Variables](#environment-variables)
7. [Shell Completion](#shell-completion)
8. [Project Layout](#project-layout)
9. [Git SHA / USR_ACCESS Bitstream Tagging](#git-sha--usr_access-bitstream-tagging)
10. [Synthesis Pipeline Details](#synthesis-pipeline-details)
11. [Simulation Backends](#simulation-backends)
12. [Formal Verification](#formal-verification)
13. [Embedded / Vitis Flow](#embedded--vitis-flow)
14. [SV Wrapper Generation](#sv-wrapper-generation)
15. [Build Artifacts Reference](#build-artifacts-reference)

---

## Overview

xviv describes an entire Xilinx/AMD FPGA project in a single `project.toml` file: FPGA target, custom IPs, block designs, RTL designs, synthesis runs, simulations, formal verification targets, and embedded platform/app configuration. A clean git clone is enough to reproduce the project; the `build/` directory is fully gitignore-able.

Key design goals:
- Reproducible builds from version-controlled source only.
- Block designs captured as re-runnable TCL snapshots (`scripts/xviv/bd/<name>.tcl`).
- Git SHA embedded into every bitstream via the `USR_ACCESS` register.
- GUI stays available for interactive work; CLI handles everything else.

---

## Installation

```sh
pip install xviv
```

Requires **Python 3.11+**. Vivado and Vitis must be on your PATH (source `settings64.sh`), or set the environment variable `XVIV_VIVADO_SOURCE_SCRIPT` (see [Environment Variables](#environment-variables)).

For development:
```sh
git clone https://github.com/laperex/xviv
pip install -e ".[dev]"
pre-commit install
```

Optional dependency: `pyslang <= 10.0.0` — required only for the SV wrapper generator (`[[wrapper]]` sections).

---

## project.toml Reference

`project.toml` is the single source of truth. Every section is an **array of tables** (e.g. `[[fpga]]`), meaning you can have multiple entries of each type. The file is loaded with Python's `tomllib`.

### `[project]`

Top-level project settings. This is the only non-array section.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `build_dir` | string | `"build"` | Path to the build output directory (relative to `project.toml`). |
| `board_repo_paths` | list[string] | `[]` | Additional board repository paths to register with Vivado. |

```toml
[project]
build_dir        = "build"
board_repo_paths = ["/opt/board_files"]
```

---

### `[[fpga]]`

Defines an FPGA target. The **first** entry is the project default and is used automatically when other sections omit `fpga =`. Multiple entries allow different sections to target different parts.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Logical name used as a reference in other sections. |
| `fpga_part` | string | one of these | Full Xilinx part number, e.g. `"xc7a200tfbg484-1"`. |
| `board_part` | string | one of these | Board part identifier, e.g. `"digilentinc.com:nexys-a7-100t:part0:1.3"`. |

Either `fpga_part` or `board_part` must be set (not both required, but at least one).

```toml
[[fpga]]
name      = "main"
fpga_part = "xc7a200tfbg484-1"

[[fpga]]
name       = "dev"
board_part = "digilentinc.com:nexys-a7-100t:part0:1.3"
```

---

### `[[design]]`

Declares an RTL (synthesisable) design. Sources are glob-expanded relative to `project.toml`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Unique design name. Also used as the default top module name. |
| `sources` | list[string \| table] | required | RTL source globs. Can be strings or structured tables (see below). |
| `top` | string | `name` | Top-level module name (if different from `name`). |
| `fpga` | string | first `[[fpga]]` | Reference to an `[[fpga]]` entry by name. |

**Structured source entries** allow per-file stage filtering:

```toml
[[design]]
name = "top"
top  = "top_module"
sources = [
  "srcs/rtl/**/*.sv",
  { files = ["srcs/rtl/debug.sv"], used_in = ["synth", "impl"] }
]
```

Valid `used_in` values: `"synth"`, `"impl"`, `"ooc"`, `"sim"`.

---

### `[[ip]]`

Declares a custom IP to be packaged with the Vivado IP Packager. xviv handles the packaging and registers the IP repo so it is available to BDs and cores.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | IP name. Also the default VLNV component name and top module. |
| `sources` | list[string \| table] | required | RTL source files for the IP. |
| `top` | string | `name` | Top-level module name. |
| `vendor` | string | `"xviv.org"` | VLNV vendor field. |
| `library` | string | `"xviv"` | VLNV library field. |
| `version` | string | `"1.0"` | VLNV version field. |
| `vlnv` | string | auto-generated | Full VLNV string — overrides individual vendor/library/version fields. |
| `repo` | string | `build/ip` | IP repository directory where the packaged IP lands. |
| `fpga` | string | first `[[fpga]]` | Target FPGA for packaging. |

```toml
[[ip]]
name    = "gamma_axi"
sources = ["srcs/ip/gamma_axi/**/*.sv"]
vendor  = "myorg"
version = "2.0"
```

---

### `[[wrapper]]`

Pairs with a `[[ip]]` entry to generate a SystemVerilog wrapper that flattens interface ports. Requires `pyslang`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ip` | string | required | Name of the `[[ip]]` entry this wrapper targets. |
| `sources` | list[string \| table] | required | Source files that the wrapper generator parses for interface definitions. |
| `wrapper_top` | string | `<ip_top>_wrapper` | Name of the generated wrapper module. |
| `wrapper_file` | string | `build/wrapper/<wrapper_top>.sv` | Output path for the generated wrapper file. |

```toml
[[wrapper]]
ip      = "gamma_axi"
sources = ["srcs/ip/gamma_axi/**/*.sv"]
```

---

### `[[core]]`

Instantiates a catalog IP (Xilinx built-in or packaged custom IP). The VLNV is resolved against the live Vivado IP catalog at `build` time (partial VLNVs are supported and fuzzy-matched).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Unique instance name. Used as the XCI file stem. |
| `vlnv` | string | required (one of) | Full or partial VLNV string, e.g. `"xilinx.com:ip:clk_wiz:6.0"` or just `"clk_wiz"`. |
| `ip` | string | required (one of) | Reference to a `[[ip]]` entry instead of a catalog VLNV. |
| `xci_file` | string | `build/core/<name>/<name>.xci` | Override for the XCI output path. |
| `fpga` | string | first `[[fpga]]` | Target FPGA for OOC synthesis. |

```toml
[[core]]
name = "clk_wiz_0"
vlnv = "clk_wiz"

[[core]]
name = "axi_dma_0"
vlnv = "xilinx.com:ip:axi_dma:7.1"
```

---

### `[[bd]]`

Declares a block design. On first creation, xviv opens the Vivado GUI so you can build the BD interactively. After you exit, it writes a TCL snapshot to `scripts/xviv/bd/<name>.tcl`. On subsequent runs, the BD is recreated non-interactively from that snapshot.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Block design name. |
| `fpga` | string | first `[[fpga]]` | Target FPGA. |
| `save_file` | string | `scripts/xviv/bd/<name>.tcl` | Path to the TCL state snapshot (version-control this). |
| `bd_file` | string | `build/bd/<name>/<name>.bd` | Path to the Vivado `.bd` file. |
| `bd_wrapper_file` | string | `build/bd/<name>/hdl/<name>_wrapper.v` | Path to the generated HDL wrapper. |

If a `.bd` file already exists, xviv automatically parses its embedded IP list and registers each IP as a `[[core]]` + OOC `[[synth]]` entry.

```toml
[[bd]]
name = "system"
```

---

### `[[synth]]`

Controls a synthesis (and optionally place-and-route) run. Exactly one of `design`, `bd`, or `core` must be specified.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `design` | string | — | Name of a `[[design]]` to synthesize. |
| `bd` | string | — | Name of a `[[bd]]` to synthesize. |
| `core` | string | — | Name of a `[[core]]` to synthesize OOC. |
| `fpga` | string | inherited | Override FPGA target. |
| `constraints` | list[string] | `[]` | XDC constraint file globs. |
| `run_synth` | bool | `true` | Run `synth_design`. |
| `run_opt` | bool | `true` | Run `opt_design`. |
| `run_place` | bool | `true` | Run `place_design`. |
| `run_phys_opt` | bool | `true` | Run `phys_opt_design` (skipped if timing passes after place). |
| `run_route` | bool | `true` | Run `route_design`. |
| `synth_incremental` | bool | `true` | Use incremental synthesis when a previous synth DCP exists. |
| `impl_incremental` | bool | `true` | Use incremental implementation when a previous route DCP exists. |
| `out_of_context_subcores` | bool | `false` | Synthesize sub-cores OOC before the top-level. |
| `synth_dcp` | bool \| string | `true` | Write synth checkpoint. Pass a path string to override location. |
| `place_dcp` | bool \| string | `true` | Write place checkpoint. |
| `route_dcp` | bool \| string | `true` | Write route checkpoint. |
| `bitstream` | bool \| string | `true` (design/bd), `false` (core) | Write `.bit` file. |
| `hw_platform` | bool \| string | `true` (bd), `false` (design/core) | Write `.xsa` hardware platform file for Vitis. |
| `synth_directive` | string | `"default"` | `synth_design -directive` value. |
| `synth_mode` | string | `"default"` or `"out_of_context"` | Synthesis mode. Cores default to `"out_of_context"`. |
| `synth_flatten_hierarchy` | string | `"rebuilt"` | Flatten hierarchy mode. |
| `synth_fsm_extraction` | string | `"auto"` | FSM extraction mode. |
| `opt_directive` | string | `"default"` | `opt_design -directive`. |
| `place_directive` | string | `"default"` | `place_design -directive`. |
| `phys_opt_directive` | string | `"default"` | `phys_opt_design -directive`. |
| `route_directive` | string | `"default"` | `route_design -directive`. |
| `usr_access_value` | int | `nil` | Override the `USR_ACCESS` value embedded in the bitstream. If not set, the git SHA is used. |
| `synth_report_timing_summary` | bool \| string | `false` | Write post-synth timing summary report. |
| `synth_report_utilization` | bool \| string | `false` | Write post-synth utilisation report. |
| `route_report_drc` | bool \| string | `false` | Write post-route DRC report. |
| `route_report_methodology` | bool \| string | `false` | Write post-route methodology report. |
| `route_report_power` | bool \| string | `false` | Write post-route power report. |
| `route_report_route_status` | bool \| string | `false` | Write post-route route status report. |
| `route_report_timing_summary` | bool \| string | `false` | Write post-route timing summary report. |
| `synth_report_incremental_reuse` | bool \| string | `false` | Write synth incremental reuse report. |
| `impl_report_incremental_reuse` | bool \| string | `false` | Write impl incremental reuse report. |
| `synth_functional_netlist` | bool \| string | `false` | Write post-synth functional netlist (`.v`). |
| `synth_timing_netlist` | bool \| string | `false` | Write post-synth timing netlist. |
| `impl_functional_netlist` | bool \| string | `false` | Write post-impl functional netlist. |
| `impl_timing_netlist` | bool \| string | `false` | Write post-impl timing netlist. |
| `impl_timing_sdf` | bool \| string | auto | Write SDF file (auto-enabled when `impl_timing_netlist` is set). |
| `synth_stub` | bool \| string | `false` (design), `true` (core) | Write a black-box stub file. |

```toml
[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
run_synth   = true
run_place   = true
run_route   = true
route_report_timing_summary = true
```

---

### `[[simulation]]`

Declares a simulation target. Supports both `xsim` (Vivado bundled) and `verilator` backends.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Simulation target name. Also the default top module name. |
| `sources` | list[string \| table] | required | Source file globs for compilation. |
| `top` | string | `name` | Top-level testbench module. |
| `backend` | string | `"xsim"` | Simulator: `"xsim"` or `"verilator"`. |
| `timescale` | string | `"1ns/1ps"` | Timescale passed to `xelab`. |
| `design` | string | — | Reference a `[[design]]` to pull its sources for post-synth/impl simulation. |
| `bd` | string | — | Reference a `[[bd]]` (not yet used, reserved). |
| `sdfmax` | list[string] | `[]` | SDF instance paths for max-delay back-annotation. |
| `sdfmin` | list[string] | `[]` | SDF instance paths for min-delay back-annotation. |
| `plusargs` | list[string] | `[]` | `+arg` strings passed verbatim to xsim or the verilated binary. |
| `defines` | list[string] | `[]` | Preprocessor `+define+` values for `xvlog` / Verilator. |
| `include_dirs` | list[string] | `[]` | Include directories for `xvlog` / Verilator. |
| `uvm` | list[table] | `[]` | Inline UVM test declarations (see `[[uvm]]`). |
| `uvm_version` | string | `"1.2"` | UVM version (`"1.1d"` or `"1.2"` — pre-compiled in Vivado). |
| `uvm_verbosity` | string | `"UVM_MEDIUM"` | Default UVM verbosity. |
| `uvm_max_quit_count` | int | `nil` | UVM_MAX_QUIT_COUNT plusarg. |
| **Verilator only** | | | |
| `threads` | int | `1` | Number of Verilator threads. |
| `trace` | bool | `false` | Enable VCD tracing. |
| `trace_fst` | bool | `false` | Enable FST tracing (preferred over VCD). |
| `trace_depth` | int | `nil` | Trace hierarchy depth limit. |
| `verilator_args` | list[string] | `[]` | Extra arguments passed to `verilator`. |
| `uvm_pkg_dir` | string | `nil` | Path to a Verilator-compatible UVM package root (required when using UVM with Verilator). |

```toml
[[simulation]]
name    = "tb_gamma"
sources = ["srcs/sim/tb_gamma.sv", "srcs/rtl/**/*.sv"]
backend = "xsim"
timescale = "1ns/100ps"
defines   = ["SIMULATION"]
```

---

### `[[uvm]]`

Declares a UVM test configuration attached to a `[[simulation]]`. Multiple entries can target the same simulation with different tests.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `test` | string | required | UVM test class name (e.g. `"gamma_basic_test"`). |
| `simulation` | string | required | Name of the `[[simulation]]` this test belongs to. |
| `top` | string | sim `top` | Top module (overrides simulation default). |
| `timescale` | string | sim `timescale` | Timescale override. |
| `verbosity` | string | sim `uvm_verbosity` | UVM verbosity level for this specific test. |
| `version` | string | sim `uvm_version` | UVM version override. |
| `max_quit_count` | int | sim value | Override `UVM_MAX_QUIT_COUNT` for this test. |

```toml
[[uvm]]
simulation = "tb_gamma"
test       = "gamma_basic_test"
verbosity  = "UVM_MEDIUM"

[[uvm]]
simulation = "tb_gamma"
test       = "gamma_corner_test"
verbosity  = "UVM_HIGH"
```

UVM tests can also be declared inline inside `[[simulation]]`:

```toml
[[simulation]]
name = "tb_gamma"
sources = ["..."]

[[simulation.uvm]]
test = "gamma_basic_test"
verbosity = "UVM_MEDIUM"
```

```toml
[[simulation]]
name = "tb_gamma"
sources = ["..."]
uvm = [
  { test = "gamma_basic_test", verbosity = "UVM_MEDIUM" }
]
```

---

### `[[formal]]`

Declares a SymbiYosys formal verification target. Vivado is **not** required; this flow uses `sby` (SymbiYosys) + SMT solvers.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Target name. |
| `top` | string | required | Top-level module to verify. |
| `mode` | string | required | Verification mode: `"bmc"`, `"prove"`, or `"cover"`. |
| `sources` | list[string] | required | Source file globs. |
| `depth` | int | `20` | Bound depth (number of cycles for BMC/prove). |
| `append` | int | `0` | Append cycles for cover mode. |
| `engine` | string | `"smtbmc yices z3"` | SymbiYosys engine string. |
| `defines` | list[string] | `[]` | Preprocessor defines. |
| `include_dirs` | list[string] | `[]` | Include directories. |
| `multiclock` | bool | `false` | Enable multi-clock mode. |
| `async2sync` | bool | `false` | Apply `async2sync` transformation. |
| `sv` | bool | `true` | Enable SystemVerilog parsing. |
| `extra_script` | list[string] | `[]` | Extra lines appended to the `[script]` section of the `.sby` file. |
| `extra_opts` | list[string] | `[]` | Extra lines appended to the `[options]` section. |

```toml
[[formal]]
name    = "gamma_props"
top     = "gamma_axi"
mode    = "prove"
depth   = 30
sources = [
  "srcs/ip/gamma_axi/gamma_axi.sv",
  "srcs/formal/gamma_axi_props.sv"
]
```

---

### `[[platform]]`

Vitis embedded flow — generates a BSP from the XSA file produced by synthesis. Exactly one of `bd`, `design`, or `xsa` must be specified.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Platform name. |
| `bd` | string | — | Derive XSA + bitstream from a `[[bd]]`'s synth output. |
| `design` | string | — | Derive XSA + bitstream from a `[[design]]`'s synth output. |
| `xsa` | string | — | Explicit path to an `.xsa` file. |
| `bitstream` | string | derived | Explicit path to a `.bit` file. |
| `cpu` | string | `"microblaze_0"` | CPU instance name in the hardware design. |
| `os` | string | `"standalone"` | OS type for BSP generation (e.g. `"standalone"`, `"freertos10_xilinx"`). |
| `properties` | table | `{}` | BSP property key-value pairs. Nested tables are flattened with `.` notation. |

The `properties` table maps to Vitis `set_property` calls. Nesting is supported:

```toml
[[platform]]
name = "mb_platform"
bd   = "system"
cpu  = "microblaze_0"
os   = "standalone"

[platform.properties]
CONFIG.stdout = "mdm_1"
CONFIG.stdin  = "mdm_1"
```

This sets `CONFIG.stdout` and `CONFIG.stdin` on the BSP. equivalent to
```TCL
hsi::set_property CONFIG.stdout mdm_1 [hsi::get_os]
hsi::set_property CONFIG.stdin mdm_1 [hsi::get_os]
```

---

### `[[app]]`

Declares a Vitis embedded application to build against a platform.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | required | Application name. |
| `platform` | string | required | Name of the `[[platform]]` to build against. |
| `template` | string | `"empty_application"` | Vitis application template (e.g. `"hello_world"`, `"lwip_echo_server"`). |
| `sources` | list[string \| table] | `[]` | C/C++ source files to add to the application. |

```toml
[[app]]
name     = "firmware"
platform = "mb_platform"
template = "empty_application"
sources  = ["srcs/sw/**/*.c"]
```

---

## CLI Commands

All commands share these global options (place them before the subcommand):

```
--config / -c FILE    project.toml path (default: project.toml)
--log FILE            append debug log to file (default: xviv.log)
```

Each subcommand also accepts:
```
--dry-run    Print generated TCL without executing Vivado
--check      Check TCL-generated outputs
```

---

### `create`

Create a new IP, block design, catalog core instance, platform, or Vitis app.

```
xviv create --ip <NAME>        [--edit] [--nogui]
xviv create --bd <NAME>        [--source-file FILE] [--no-generate] [--edit] [--nogui]
xviv create --core <NAME>      [--no-generate] [--edit] [--nogui]
xviv create --platform <NAME>  [--build]
xviv create --app <NAME>       --platform <PLATFORM> [--build]
```

**`--ip <NAME>`** — Packages the custom IP declared in `project.toml` using Vivado IP Packager.
- `--edit` — Opens Vivado GUI for interactive IP editing after creation.
- `--nogui` — Run IP packager in TCL-only batch mode (no GUI).

**`--bd <NAME>`** — Creates a block design.
- `--source-file FILE` — Recreate from a specific TCL snapshot instead of the default `scripts/xviv/bd/<name>.tcl`. Pass `false` to always open the GUI even if a snapshot exists.
- `--no-generate` — Import and register the BD without generating output products.
- `--edit` — Open the BD editor GUI after creation/import.
- `--nogui` — Non-interactive mode; requires an existing snapshot.

**`--core <NAME>`** — Instantiates a catalog IP core from its VLNV, creating the XCI file.
- `--no-generate` — Skip output product generation.
- `--edit` — Open the IP customisation GUI.

**`--platform <NAME>`** — Generates a BSP from the XSA using `hsi::generate_bsp`.
- `--build` — Also run `build --platform` immediately after creation.

**`--app <NAME> --platform <PLATFORM>`** — Scaffolds a Vitis application from the declared template.
- `--build` — Also compile the app immediately.

```sh
# Package custom IP
xviv create --ip gamma_axi

# Create BD from scratch (opens GUI)
xviv create --bd system

# Recreate BD from existing TCL snapshot
xviv create --bd system --source-file scripts/xviv/bd/system.tcl

# Recreate BD non-interactively, skip generate
xviv create --bd system --no-generate

# Create platform and immediately build it
xviv create --platform mb_platform --build

# Create app
xviv create --app firmware --platform mb_platform
```

---

### `edit`

Open an IP, block design, or core in Vivado for interactive editing. Changes are saved back to the TCL snapshot on exit.

```
xviv edit --ip   <NAME>  [--nogui]
xviv edit --bd   <NAME>  [--nogui]
xviv edit --core <NAME>  [--nogui]
```

- `--nogui` — Opens a Vivado TCL console instead of the full GUI (useful in scripted contexts).

```sh
xviv edit --ip   gamma_axi
xviv edit --bd   system
xviv edit --core clk_wiz_0
```

---

### `generate`

Generate (or re-generate) output products for a block design or core. Skips up-to-date outputs unless `--force` is used.

```
xviv generate --bd   <NAME>  [--force]
xviv generate --core <NAME>  [--force]
```

- `--force` — Regenerate even if the output products appear current.

```sh
xviv generate --bd   system
xviv generate --core clk_wiz_0 --force
```

After a `create --ip` run, use `generate --core <name>` to regenerate all associated output products.

---

### `synth` (command)

Run synthesis (and optionally place, route, bitstream) for a design, block design, or core. The pipeline is: `synth_design → opt_design → place_design → phys_opt_design → route_design → write_bitstream`.

```
xviv synth --design <NAME>  [--resume STAGE] [--usr-access-type TYPE]
xviv synth --bd     <NAME>  [--resume STAGE] [--usr-access-type TYPE]
xviv synth --core   <NAME>  [--resume STAGE]
```

- `--resume STAGE` — Resume from an existing checkpoint instead of starting fresh.
  - `auto` — Detect the latest available checkpoint automatically.
  - `synth` — Resume from after `synth_design` (load `synth.dcp`).
  - `place` — Resume from after `place_design` (load `place.dcp`).
  - `route` — Resume from after `route_design` (load `route.dcp`).
- `--usr-access-type TYPE` — Controls what value is embedded in `USR_ACCESS`.
  - `git` (default) — Embeds the short git SHA (bit 28 set if working tree is dirty).

```sh
# Full RTL synthesis
xviv synth --design top

# BD synthesis
xviv synth --bd system

# OOC core synthesis
xviv synth --core clk_wiz_0

# Resume from latest checkpoint
xviv synth --design top --resume auto

# Resume specifically from after placement
xviv synth --design top --resume place

# Preview TCL without running
xviv synth --design top --dry-run
```

The `[[synth]]` section in `project.toml` controls which stages run, incremental flows, directives, reports, and what artifacts are written.

---

### `simulate`

Compile, elaborate, and run a simulation target.

```
xviv simulate --target <NAME>  [--mode MODE] [--run TIME] [--uvm TEST]
```

- `--mode MODE` — Simulation mode (default: `default`).
  - `default` — Use RTL sources directly.
  - `post_synth_functional` — Use post-synthesis functional netlist.
  - `post_synth_timing` — Use post-synthesis timing netlist.
  - `post_impl_functional` — Use post-implementation functional netlist.
  - `post_impl_timing` — Use post-implementation timing netlist + SDF.
- `--run TIME` — Simulation run time (default: `all`). Examples: `1000ns`, `1us`, `all`.
- `--uvm TEST` — Run a specific UVM test declared in `[[uvm]]`.

**xsim pipeline:** `xvlog` (compile) → `xelab` (elaborate with `-R` for run-after-elab) → `xsim` (run). A `waveform_config.tcl` is generated automatically before simulation.

**Verilator pipeline:** `verilator` (compile + link) → run verilated binary.

```sh
xviv simulate --target tb_gamma
xviv simulate --target tb_gamma --run 2000ns
xviv simulate --target tb_gamma --mode post_synth_functional
xviv simulate --target tb_gamma --uvm gamma_basic_test
```

---

### `open`

Open a DCP checkpoint in Vivado or a WDB waveform in xsim.

```
xviv open --dcp <PATH>           [--nogui]
xviv open --wdb <SIM_NAME>       [--nogui]
```

- `--dcp <PATH>` — Open any `.dcp` checkpoint. The path tab-completes to known checkpoint locations under `build/synth/`.
- `--wdb <SIM_NAME>` — Open the waveform database for a simulation target by name.
- `--nogui` — Open a Vivado TCL console only (no GUI).

```sh
xviv open --dcp build/synth/top/checkpoints/route.dcp
xviv open --dcp build/synth/system/checkpoints/synth.dcp --nogui
xviv open --wdb tb_gamma
```

---

### `reload`

Hot-reload a simulation snapshot in a live xsim GUI session (without restarting). Use this during interactive debug to pick up RTL changes.

```
xviv reload --target <SIM_NAME>
```

```sh
xviv reload --target tb_gamma
```

---

### `build`

Compile a Vitis platform (BSP) or application.

```
xviv build --platform <NAME>
xviv build --app      <NAME>  [--info]
```

- `--info` — After building the app, print ELF section sizes (`size` output).

```sh
xviv build --platform mb_platform
xviv build --app firmware
xviv build --app firmware --info
```

---

### `program`

Download a bitstream and/or ELF to the FPGA over JTAG using XSCT.

```
xviv program [--platform NAME | --bitstream FILE]  [--app NAME | --elf FILE]
			 [--fpga FILTER] [--processor FILTER] [--reset-duration MS]
```

- `--platform NAME` — Derive bitstream + ELF paths from a `[[platform]]` entry.
- `--bitstream FILE` — Explicit path to a `.bit` file.
- `--app NAME` — Derive ELF path from an `[[app]]` entry.
- `--elf FILE` — Explicit path to an `.elf` file.
- `--fpga FILTER` — Target filter for FPGA device (default: `"xc7a*"`). Supports glob wildcards.
- `--processor FILTER` — Target filter for soft processor (default: `"Microblaze #0*"`).
- `--reset-duration MS` — Duration of the soft reset in milliseconds before loading the ELF (default: `500`).

```sh
# Program from project config
xviv program --platform mb_platform --app firmware

# Explicit paths
xviv program --bitstream build/synth/system/system.bit --elf build/app/firmware/executable.elf

# Custom target filters
xviv program --platform mb_platform --fpga "xc7a35t*" --processor "MicroBlaze #0*"

# Longer reset before ELF load
xviv program --platform mb_platform --app firmware --reset-duration 1000
```

---

### `processor`

Control an embedded soft processor over JTAG via XSCT.

```
xviv processor --reset
xviv processor --status
```

- `--reset` — Issue a soft reset to the processor.
- `--status` — Print processor state and register values.

```sh
xviv processor --reset
xviv processor --status
```

---

### `search`

Search the Vivado IP catalog by name, partial VLNV, or keyword. Results include the display name, vendor/library, and a short description. This is useful to find the exact VLNV string to use in `[[core]]` entries.

```
xviv search <QUERY>
```

```sh
xviv search axi4 dma
xviv search clk_wiz
xviv search xilinx.com:ip:fifo
```

---

### `formal` (command)

Run SymbiYosys formal verification on one or all `[[formal]]` targets. On failure, the counterexample VCD path is printed alongside a `gtkwave` command.

```
xviv formal [--target NAME]
```

- `--target NAME` — Run a specific target. Omit to run **all** `[[formal]]` targets.

```sh
# Run a named target
xviv formal --target gamma_props

# Run all formal targets
xviv formal
```

Results are displayed as a colour-coded summary table (PASS / FAIL). The command exits with code `1` if any target fails.

On failure, the counterexample trace can be opened directly:
```
counterexample trace -> build/formal/gamma_props/engine_0/trace.vcd
open with: gtkwave build/formal/gamma_props/engine_0/trace.vcd
```

---

## Global CLI Flags

These flags can be passed to any subcommand:

| Flag | Description |
|------|-------------|
| `--dry-run` | Print generated TCL to stdout without executing Vivado or XSCT. |
| `--check` | Verify TCL-generated outputs. |

```sh
xviv synth --design top --dry-run
xviv create --bd system --dry-run
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `XVIV_VIVADO_SOURCE_SCRIPT` | Path to `settings64.sh`. xviv will source it before invoking Vivado. Alternatively, put it in `.env` at the project root. |
| `XVIV_VIVADO_DIR` | Path to the Vivado installation directory. |
| `XVIV_VITIS_DIR` | Path to the Vitis installation directory. |

A `.env` file at the project root is automatically read:

```sh
# .env
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

---

## Shell Completion

xviv supports dynamic tab completion via `argcomplete`. Completions are context-aware:

| Argument | Completion source |
|----------|-------------------|
| `--ip`, `--bd`, `--design`, `--core` | Names parsed from `project.toml` |
| `--target` (simulate) | Simulation names from `project.toml` |
| `--uvm` | UVM test names filtered to the selected simulation |
| `--dcp` | Known checkpoint file paths under `build/synth/` |
| `--platform`, `--app` | Names from `project.toml` |
| VLNV strings | Live Vivado IP catalog with inline descriptions |

**Activate completion:**

```sh
# System-wide (requires root):
activate-global-python-argcomplete

# Per-shell (bash):
eval "$(register-python-argcomplete xviv)"

# Add to ~/.bashrc for persistence:
echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.bashrc
```

---

## Project Layout

```
project/
├── project.toml               # Single source of truth — commit this
├── .env                       # Optional: XVIV_VIVADO_SOURCE_SCRIPT=...
├── srcs/
│   ├── rtl/                   # RTL source files
│   ├── sim/                   # Testbench files
│   ├── ip/                    # Custom IP source files
│   └── sw/                    # Embedded software source files
├── constraints/               # XDC constraint files
├── scripts/
│   └── xviv/
│       └── bd/
│           └── system.tcl     # BD TCL snapshot — commit this
└── build/                     # Fully gitignore-able; all outputs land here
	├── synth/
	│   └── <name>/
	│       ├── checkpoints/   # synth.dcp, place.dcp, route.dcp
	│       ├── reports/       # .rpt files
	│       ├── netlists/      # .v netlist files
	│       ├── <name>.bit     # Bitstream
	│       └── <name>.xsa     # Hardware platform (for Vitis)
	├── bd/                    # Block design Vivado project files
	├── core/                  # XCI files for catalog IP instances
	├── ip/                    # Packaged custom IP repository
	├── sim/<name>/            # Simulation work directories
	├── formal/<name>/         # SymbiYosys work directories
	├── platform/<name>/       # BSP output
	├── app/<name>/            # App output; executable.elf lands here
	└── wrapper/               # Generated SV wrapper files
```

Only `scripts/xviv/` (BD TCL snapshots) needs to be version-controlled alongside sources and `project.toml`. Everything under `build/` is reproducible.

---

## Git SHA / USR_ACCESS Bitstream Tagging

By default, every synthesis run embeds the current git commit SHA into the bitstream's `USR_ACCESS` register. This lets you trace any `.bit` file back to its exact source revision via JTAG readback.

**Encoding:**
- Bits **[27:0]** — 7-character short git SHA (hex-encoded, 28 bits).
- Bit **28** — Set to `1` if the working tree was dirty (uncommitted changes) at build time.

This is applied automatically. Override the embedded value per run in `project.toml`:

```toml
[[synth]]
design           = "top"
constraints      = ["constraints/top.xdc"]
usr_access_value = 0xDEADBEEF   # hard-coded value instead of git SHA
```

Or from the CLI:
```sh
xviv synth --design top --usr-access-type git   # default
```

In non-git projects, the SHA falls back to a datestamp.

---

## Synthesis Pipeline Details

A full synthesis run executes these stages in order (each can be individually disabled in `project.toml`):

1. **`synth_design`** — Logic synthesis. Writes `checkpoints/synth.dcp`.
2. **`opt_design`** — Logic optimisation. Controlled by `opt_directive`.
3. **`place_design`** — Placement. Writes `checkpoints/place.dcp`. Controlled by `place_directive`.
4. **`phys_opt_design`** — Physical optimisation. Only runs when timing fails after placement. Controlled by `phys_opt_directive`.
5. **`route_design`** — Routing. Writes `checkpoints/route.dcp`. Controlled by `route_directive`.
6. **`write_bitstream`** — Bitstream generation with `USR_ACCESS` tagging. Writes `<name>.bit`.
7. **`write_hw_platform`** — Hardware platform export. Writes `<name>.xsa` (for Vitis flows).

**Incremental flows:** When a previous checkpoint exists, xviv automatically passes the previous DCP to `read_checkpoint` with `-incremental` for both synthesis and implementation. Disable with `synth_incremental = false` or `impl_incremental = false`.

**OOC synthesis for cores:** When `synth_mode = "out_of_context"` (default for `[[core]]`), `synth_design` is called with `-mode out_of_context`. No bitstream or XSA is produced. The output DCP + stub can be used as a black-box replacement in a parent design.

**Resume:** The `--resume` flag loads the named checkpoint and skips earlier stages. `--resume auto` inspects `checkpoints/` and picks the latest available stage.

---

## Simulation Backends

### xsim (default)

Vivado's bundled simulator. Full pipeline:

1. `xvlog -sv [defines] [include_dirs] <sources>` — Compile SystemVerilog sources.
2. `xelab -R [timescale] [-L uvm] <top>` — Elaborate and immediately run. The `-R` flag means simulation starts without a separate `xsim` invocation.
3. A `waveform_config.tcl` is auto-generated to configure wave display.
4. SDF back-annotation via `--sdfmax` / `--sdfmin` is applied during elaboration for timing simulation modes.

### Verilator

Open-source simulation. When `backend = "verilator"`:

1. `verilator --sv [--lint-only] [defines] [includes] <sources>` — Compile.
2. Runs the verilated binary directly.
3. Tracing is controlled by `trace` (VCD) and `trace_fst` (FST).
4. Thread parallelism via `threads`.

### Post-synthesis / post-implementation simulation modes

When `--mode` is anything other than `default`, xviv resolves the relevant netlist from the corresponding `[[synth]]` configuration and uses it as the source. The required netlist/SDF must exist (i.e. the corresponding `[[synth]]` must have the report/netlist flags enabled and have been run).

| Mode | Required synth output |
|------|-----------------------|
| `post_synth_functional` | `synth_functional_netlist = true` |
| `post_synth_timing` | `synth_timing_netlist = true` |
| `post_impl_functional` | `impl_functional_netlist = true` |
| `post_impl_timing` | `impl_timing_netlist = true` + `impl_timing_sdf = true` |

---

## Formal Verification

xviv's formal flow uses [SymbiYosys](https://symbiyosys.readthedocs.io/) (`sby`) as the frontend with SMT solvers (default: `smtbmc yices z3`).

A `.sby` script is generated from the `[[formal]]` configuration and placed in `build/formal/`. The generated script structure is:

```
[options]
mode prove
depth 30

[engines]
smtbmc yices z3

[script]
read_verilog -formal -sv gamma_axi.sv
read_verilog -formal -sv gamma_axi_props.sv
hierarchy -check -top gamma_axi
proc
opt -full
flatten
opt -full
setundef -zero

[files]
srcs/ip/gamma_axi/gamma_axi.sv
srcs/formal/gamma_axi_props.sv
```

**Modes:**
- `bmc` — Bounded model checking: checks all reachable states up to `depth` cycles.
- `prove` — Full inductive proof over the bound.
- `cover` — Reachability: checks that `cover()` statements are reachable within `depth` cycles.

If verification fails, the VCD counterexample trace path is printed and a `gtkwave` command is provided.

---

## Embedded / Vitis Flow

Full MicroBlaze (or other soft processor) embedded flow:

```
synth --bd system          # produces system.xsa + system.bit
create --platform mb_platform  # generates BSP from system.xsa via hsi
build --platform mb_platform   # compiles BSP with make
create --app firmware          # scaffolds Vitis app from template
build --app firmware           # compiles app -> executable.elf
program --platform mb_platform --app firmware  # downloads bit + elf over JTAG
```

Each step is idempotent. You can rebuild only what changed.

**Platform BSP properties** are set via XSCT `set_property` calls driven by `[platform.properties]`:

```toml
[platform.properties.CONFIG]
stdout = "mdm_1"
stdin  = "mdm_1"
```

This flattens to `CONFIG.stdout = mdm_1`, `CONFIG.stdin = mdm_1`.

---

## SV Wrapper Generation

When a custom IP has AXI interface ports, the Vivado IP Packager expects flattened signals. The `[[wrapper]]` section automates this by generating a SystemVerilog wrapper module that re-exposes interfaces as flat ports.

Requires `pyslang` to be installed.

The generated wrapper is placed at `build/wrapper/<wrapper_top>.sv` and automatically included as a source when `create --ip` is run.

```toml
[[ip]]
name    = "gamma_axi"
sources = ["srcs/ip/gamma_axi/**/*.sv"]

[[wrapper]]
ip      = "gamma_axi"
sources = ["srcs/ip/gamma_axi/**/*.sv"]
```

The wrapper generator is also available as a standalone entry point:

```sh
xviv_wrapper --help
```

---

## Build Artifacts Reference

| Artifact | Location | Condition |
|----------|----------|-----------|
| Synth checkpoint | `build/synth/<name>/checkpoints/synth.dcp` | `synth_dcp = true` |
| Place checkpoint | `build/synth/<name>/checkpoints/place.dcp` | `place_dcp = true` |
| Route checkpoint | `build/synth/<name>/checkpoints/route.dcp` | `route_dcp = true` |
| Bitstream | `build/synth/<name>/<name>.bit` | `bitstream = true` |
| Hardware platform | `build/synth/<name>/<name>.xsa` | `hw_platform = true` |
| Synth stub | `build/synth/<name>/<name>_stub.v` | `synth_stub = true` |
| Post-synth functional netlist | `build/synth/<name>/netlists/<name>_synth_functional_netlist.v` | `synth_functional_netlist = true` |
| Post-synth timing netlist | `build/synth/<name>/netlists/<name>_synth_timing_netlist.v` | `synth_timing_netlist = true` |
| Post-impl functional netlist | `build/synth/<name>/netlists/<name>_impl_functional_netlist.v` | `impl_functional_netlist = true` |
| Post-impl timing netlist | `build/synth/<name>/netlists/<name>_impl_timing_netlist.v` | `impl_timing_netlist = true` |
| SDF back-annotation file | `build/synth/<name>/netlists/<name>_impl_timing.sdf` | `impl_timing_sdf = true` |
| Synth timing summary | `build/synth/<name>/reports/synth_report_timing_summary_file.rpt` | `synth_report_timing_summary = true` |
| Synth utilisation | `build/synth/<name>/reports/synth_report_utilization_file.rpt` | `synth_report_utilization = true` |
| Route DRC | `build/synth/<name>/reports/route_report_drc_file.rpt` | `route_report_drc = true` |
| Route power | `build/synth/<name>/reports/route_report_power_file.rpt` | `route_report_power = true` |
| Route timing summary | `build/synth/<name>/reports/route_report_timing_summary_file.rpt` | `route_report_timing_summary = true` |
| BD TCL snapshot | `scripts/xviv/bd/<name>.tcl` | After any `generate --bd` or GUI exit |
| Core XCI | `build/core/<name>/<name>.xci` | After `create --core` |
| IP repository | `build/ip/` | After `create --ip` |
| Platform BSP | `build/platform/<name>/` | After `build --platform` |
| App ELF | `build/app/<name>/executable.elf` | After `build --app` |
| SV wrapper | `build/wrapper/<wrapper_top>.sv` | `[[wrapper]]` defined |
| Formal .sby | `build/formal/<name>.sby` | `xviv formal` |
| Formal task dir | `build/formal/<name>/` | `xviv formal` |
| Debug log | `xviv.log` (project root) | Always |