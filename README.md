# xviv

[![PyPI](https://img.shields.io/pypi/v/xviv)](https://pypi.org/project/xviv/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/xviv)](https://pypi.org/project/xviv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://github.com/laperex/xviv/actions/workflows/test.yml/badge.svg)](https://github.com/laperex/xviv/actions/workflows/test.yml)

Declarative CLI for Xilinx Vivado and Vitis - reproducible FPGA builds from a single `project.toml`, no GUI required.

```sh
pip install xviv
```

---

- [Description](#description)
    - [The problem](#the-problem)
    - [The philosophy](#the-philosophy)
    - [Machine agnostic](#machine-agnostic)
    - [Efficiency](#efficiency)
    - [Debugging](#debugging)
    - [Collaborative debugging](#collaborative-debugging)
- [Install](#install)
  - [Shell completion](#shell-completion)
- [Getting started](#getting-started)
- [Project layout](#project-layout)
- [project.toml](#projecttoml)
- [Commands](#commands)
  - [Working with IPs and BDs](#working-with-ips-and-bds)
  - [Synthesis](#synthesis)
  - [Simulation](#simulation)
  - [Embedded](#embedded)
  - [Validate](#validate)
  - [Formal](#formal)
- [Validate](#validate-1)
- [Roadmap](#roadmap)
- [License](#license)

---

## Description

### The problem

Unlike traditional C++ or Python development, RTL/FPGA projects built with Vivado are notoriously hostile to version control and team collaboration.

Vivado's default Project Mode tightly couples the developer to its GUI. It buries absolute file paths inside its project files and indiscriminately mixes source code with massive generated build artifacts. This makes version control a mess and means a project that builds on one machine will likely break on another - two engineers, two machines, the same repository, and there's still no guarantee they get the same build.

Vivado's Non-Project Mode solves the version control issue, but lacks a modern developer experience - forcing teams to manually manage complex Tcl scripts just to maintain a workflow.

### The philosophy

xviv bridges this gap, borrowing heavily from the developer experience Cargo brought to Rust: one manifest, one CLI, reproducible builds, and no clicking through wizards for something that should just be a command.

It provides a configuration-driven CLI that enforces a strict separation between source files and build artifacts. Describe the whole project in a single `project.toml` - FPGA part, IP, block designs, RTL, synth/sim/formal targets - and everything Vivado actually generates (checkpoints, logs, cached IP outputs) goes into a single build directory that stays entirely git-ignored. Nobody has to sort through it or worry about breaking something by deleting it; it's rebuilt fresh every time. A clean clone is all you need to reproduce the project on any system.

It automates the scriptable parts of the Non-Project flow, while seamlessly allowing developers to spin up the Vivado GUI for tasks where it genuinely shines - like editing IP Packaging, configuring cores, or designing Block Diagrams.

### Machine agnostic

Nothing in the tracked config ever points at a specific machine. The local Vivado install path lives in an environment variable, not the config (see `XVIV_VIVADO_SOURCE_SCRIPT` below). Block designs are exported as re-runnable TCL snapshots instead of the `.bd` file itself, so two developers - or two Vivado versions - rebuild the exact same block design without touching the GUI. Checksums decide what's stale and needs rebuilding, so builds actually converge to the same state instead of quietly drifting apart across machines.

### Efficiency

The full synthesis pipeline (`synth_design` → `opt_design` → `place_design` → `phys_opt_design` → `route_design` → `write_bitstream`) runs as one command instead of stepping through the GUI manually, with shell completion for IP names, DCP paths, and more. Synthesis can resume from an existing checkpoint instead of rerunning from scratch after a small change, and out-of-context sub-core synthesis for block designs runs in parallel.

### Debugging

Any checkpoint at any stage can be opened directly (`xviv open --dcp`), and waveform databases can be reopened without rerunning the simulation. A hot-reload mode for `xsim` means an RTL tweak doesn't require killing and restarting the simulation session. Formal verification failures print a ready-to-paste `gtkwave` command for the counterexample trace.

Every synth run also embeds the short git commit SHA into the bitstream's `USR_ACCESS` field (with a bit reserved for a dirty working tree), so any bitstream can be traced back to the exact revision that produced it - useful when a board in the lab is misbehaving and it isn't obvious which build is actually on it.

### Collaborative debugging

Because everything is reproducible, debugging stops being a one-person job. Anyone on the team can pull the exact commit and re-run synthesis to get the identical checkpoint a bug showed up in, so multiple people can dig into the same failing place/route stage independently instead of passing a laptop around. If an issue only shows up on one board, another engineer can check out that exact commit - visible directly in the bitstream - and try to reproduce it on their own setup before anyone touches the hardware again. Since block design changes are just TCL text, they can also be reviewed in a pull request like any other code change, catching a bad change before it's ever synthesized.

---

## Install

```sh
pip install xviv
```

Requires **Python 3.11+**. Vivado and Vitis must be on your PATH (source `settings64.sh`), or set `XVIV_VIVADO_SOURCE_SCRIPT` and xviv will source it for you:

```sh
# .env at project root (recommended, add to .gitignore)
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

`pyslang` (already a declared dependency) is used for SV wrapper generation (`[[wrapper]]` sections).

We'd also recommend enabling shell completion at this point - see [Shell completion](#shell-completion) below.

### Shell completion

```sh
activate-global-python-argcomplete          # system-wide
eval "$(register-python-argcomplete xviv)"  # or per-shell (bash)

# Add to ~/.bashrc for persistence
echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.bashrc
```

Completion is dynamic:
- IP, BD, design, simulation, core, platform, app, and formal target names come from `project.toml`
- VLNV strings for `[[core]]` come from the live Vivado IP catalog with descriptions inline
- DCP paths complete from known checkpoint locations for each synth run
- UVM test names filter to the selected simulation target
- Bitstream and ELF paths complete from known output locations

For development:

```sh
git clone https://github.com/laperex/xviv.git
cd xviv
pip install -e ".[dev]"
pre-commit install
```

---

## Getting started

A minimal project for a bare RTL design:

```toml
# project.toml

[[fpga]]
name      = "main"
fpga_part = "xc7a200tfbg484-1"

[[design]]
name    = "top"
sources = ["srcs/rtl/**/*.sv"]

[[synth]]
design      = "top"
constraints = ["constraints/top.xdc"]
```

```sh
xviv synth --design top
```

That runs the full pipeline: `synth_design` → `opt_design` → `place_design` → `phys_opt_design` → `route_design` → `write_bitstream`. Checkpoints land in `build/synth/top/checkpoints/`. Open any of them with:

```sh
xviv open --dcp build/synth/top/checkpoints/route.dcp
```

Every command also generates a `project.lock` file at the project root - a TOML snapshot of the fully-resolved configuration (all globs expanded, all defaults applied). Useful for debugging and as an audit trail.

---

---

## Project layout

```
project/
├── project.toml               # single source of truth - commit this
├── project.lock               # auto-generated resolved config snapshot
├── .env                       # optional: XVIV_VIVADO_SOURCE_SCRIPT=...
├── srcs/
│   ├── rtl/
│   ├── ip/
│   ├── sim/
│   └── sw/
├── constraints/
├── scripts/
│   └── xviv/
│       └── bd/
│           └── system.tcl     # BD TCL snapshot - version control this
└── build/                     # gitignore everything here
    ├── log/
    │   └── xviv.log
    ├── synth/<name>/
    │   ├── checkpoints/       # synth.dcp, place.dcp, route.dcp
    │   ├── reports/
    │   ├── netlists/
    │   ├── <name>.bit
    │   └── <name>.xsa
    ├── core/                  # .xci files
    ├── ip/                    # packaged IP repos
    ├── bd/
    ├── sim/<name>/
    ├── platform/<name>/
    ├── app/<name>/
    └── formal/<name>/
```

`scripts/xviv/` is the only generated directory that belongs in version control. Everything under `build/` is reproducible from `project.toml` and the BD TCL snapshots.


## project.toml

All sections except `[project]` are arrays of tables. A real project uses some combination of the following:

| Section | Description |
| --- | --- |
| `[[fpga]]` | Part number and optional board definition. The first entry is the default; later sections can override with `fpga = "name"`. |
| `[[design]]` | RTL sources and top module for a synthesisable design. Sources can be bare glob strings or structured entries with `used_in` stage filtering (`"synth"`, `"impl"`, `"ooc"`, `"sim"`). |
| `[[ip]]` | Custom IP to package with the Vivado IP Packager. xviv handles the packaging and wires the IP repo into the project. Use `[[wrapper]]` alongside it if the IP has interface ports that need flattening (requires `pyslang`). |
| `[[core]]` | An instance of a catalog IP (Xilinx built-in or custom packaged). Identified by a partial VLNV that resolves against the live catalog; tab completion works here. |
| `[[bd]]` | A block design. xviv creates it, opens the editor, and writes its state as a re-runnable TCL snapshot under `scripts/xviv/bd/`. After that, `create --bd <name>` recreates it non-interactively from the snapshot on any machine. |
| `[[synth]]` | A synthesis run. Identified by one of `design`, `bd`, or `core`. Controls the full pipeline (which stages to run, incremental flows, directive overrides, reports, output artifacts). |
| `[[simulation]]` | A simulation target. Backends: `xsim` (default) or `verilator`. Supports UVM (see `[[uvm]]`), SDF back-annotation, and post-synthesis / post-implementation modes. |
| `[[uvm]]` | A UVM test configuration attached to a `[[simulation]]`. Each entry defines a test name, verbosity, and version. Multiple tests can target the same simulation. |
| `[[platform]]` / `[[app]]` | Vitis embedded flow. `platform` generates a BSP from the XSA produced by synthesis; `app` scaffolds and builds a Vitis application against it. The `properties` key on `[[platform]]` sets BSP properties (e.g. `CONFIG.stdout`) directly from the TOML. |
| `[[formal]]` | SymbiYosys formal verification target. Modes: `bmc`, `prove`, `cover`. Vivado is not required for this flow. |
| `[project]` | Optional global settings: `work_dir` (default: `"build"`), `log_file`, `board_repo`, `ip_repo`. |

A complete example:

```toml
[project]
work_dir = "build"

[[fpga]]
name      = "main"
fpga_part = "xc7a200tfbg484-1"

[[ip]]
name    = "gamma_axi"
sources = ["srcs/ip/gamma_axi/**/*.sv"]

[[bd]]
name = "system"

[[synth]]
bd          = "system"
constraints = ["constraints/system.xdc"]
run_synth   = true
run_place   = true
run_route   = true

[[platform]]
name = "mb_platform"
bd   = "system"
cpu  = "microblaze_0"
os   = "standalone"

[platform.properties]
CONFIG.stdout = "mdm_1"
CONFIG.stdin  = "mdm_1"

[[app]]
name     = "firmware"
platform = "mb_platform"
template = "empty_application"

[[simulation]]
name    = "tb_gamma"
sources = ["srcs/sim/tb_gamma.sv", "srcs/rtl/**/*.sv"]
backend = "xsim"

[[uvm]]
simulation = "tb_gamma"
test       = "gamma_basic_test"
verbosity  = "UVM_MEDIUM"

[[formal]]
name    = "gamma_props"
top     = "gamma_axi"
mode    = "prove"
sources = ["srcs/ip/gamma_axi/gamma_axi.sv", "srcs/formal/gamma_axi_props.sv"]
depth   = 30
defines = ["FORMAL"]
```

---

## Commands

### Working with IPs and BDs

```sh
# Package a custom IP
xviv create --ip gamma_axi
xviv edit   --ip gamma_axi              # opens IP Packager GUI

# Re-package and regenerate all XCI instances that use this IP (in parallel)
xviv create --ip gamma_axi --regenerate

# Create a block design from scratch (opens GUI)
xviv create --bd system

# Import from an existing TCL snapshot, no GUI
xviv create --bd system --nogui

# Import from snapshot and generate output products
xviv create --bd system --generate

# After editing, generate (or force-regenerate) output products
xviv generate --bd system
xviv generate --bd system --force
xviv generate --bd system --reset      # reset stale products first

# Instantiate a catalog IP core
xviv create --core clk_wiz_0
xviv create --core clk_wiz_0 --generate
xviv edit   --core clk_wiz_0

# Search the IP catalog
xviv search clk_wiz
xviv search "axi dma"
```

### Synthesis

```sh
xviv synth --design top          # RTL design
xviv synth --bd     system       # block design
xviv synth --core   clk_wiz_0    # out-of-context IP core

# Parallel OOC synthesis of all sub-cores before the top-level run
xviv synth --bd system --parallel

# Resume from an existing checkpoint
xviv synth --design top --resume auto      # detect latest checkpoint automatically
xviv synth --design top --resume synth     # resume from after synth_design
xviv synth --design top --resume place     # resume from after place_design
xviv synth --design top --resume route     # re-run write_bitstream only

# Preview the generated TCL without running
xviv synth --design top --dry-run

# Open a checkpoint (path tab-completes)
xviv open --dcp build/synth/system/checkpoints/route.dcp
```

By default, every synth run embeds the short git SHA into the bitstream `USR_ACCESS` field (bit 28 is set if the working tree was dirty). Fine-grained control is in `project.toml`: `run_synth`, `run_place`, `run_route`, incremental flows, directive overrides, reports, netlists.

### Simulation

```sh
xviv simulate --target tb_gamma
xviv simulate --target tb_gamma --run 1000ns
xviv simulate --target tb_gamma --mode post_synth_functional
xviv simulate --target tb_gamma --mode post_impl_timing

# Run a specific UVM test
xviv simulate --target tb_gamma --uvm gamma_basic_test

# Open the waveform DB or hot-reload in a live xsim session
xviv open   --wdb tb_gamma
xviv reload --target tb_gamma
```

Available `--mode` values: `default`, `post_synth_functional`, `post_synth_timing`, `post_impl_functional`, `post_impl_timing`.

### Embedded

```sh
xviv create --platform mb_platform
xviv build  --platform mb_platform

xviv create --app firmware
xviv build  --app firmware
xviv build  --app firmware --info   # also print ELF section sizes

# Program the board (derive paths from config)
xviv program --platform mb_platform --app firmware

# Explicit paths or custom JTAG target filters
xviv program --bitstream path/to/custom.bit --elf path/to/custom.elf
xviv program --platform mb_platform --fpga "xc7a35t*" --processor "MicroBlaze #0*"
xviv program --platform mb_platform --reset-duration 1000   # ms before loading ELF

xviv processor --reset
xviv processor --status
```

### Validate

Validate XDC constraint files against RTL port declarations without running Vivado. The engine uses Python's native Tcl interpreter to evaluate XDC files and `pyslang` to extract ports directly from SystemVerilog source.

```sh
# Check XDC I/O pins against RTL ports for a design
xviv validate synth --design top --io short
xviv validate synth --design top --io full

# Same for a block design
xviv validate synth --bd system --io full

# Control which issues are reported
xviv validate synth --design top --io full --level error   # errors only
xviv validate synth --design top --io full --level info    # all (default)
```

`--io short` prints a summary table; `--io full` shows every port with its constraint status (PACKAGE_PIN, IOSTANDARD, timing constraints, and any unmapped or unconstrained pins).

### Formal

```sh
# Run all [[formal]] targets
xviv formal

# Run a specific target
xviv formal --target gamma_props
```

On failure, the counterexample trace path is printed with a `gtkwave` command ready to paste.

Every command accepts `--dry-run` to print the generated TCL without executing.

---

## Validate

`xviv validate` cross-references XDC constraints against RTL port declarations without invoking Vivado. It runs entirely in Python:

- **XDC parsing** - uses Python's built-in `tkinter.Tcl` engine to evaluate XDC files natively. Handles `set_property`, `create_clock`, `set_input_delay`, `set_output_delay`, `set_false_path`, `set_max_delay`, and Vivado-style glob/bus wildcards (`[*]`, `[?]`).
- **RTL extraction** - uses `pyslang` to extract port declarations (name, direction, width) from SystemVerilog sources.
- **Reporting** - renders a colour-coded ASCII table showing every port, its assigned PACKAGE_PIN, IOSTANDARD, and timing constraint coverage. Unconstrained or unmatched pins are flagged.

```sh
xviv validate synth --design top --io full
```

---

## Roadmap

Near-term

| Priority | Feature | Description |
|---|---|---|
| 1 | `validate synth --core` | XDC/port validation for standalone OOC core targets (currently only `--design` and `--bd` are supported) |
| 2 | DPI support | C/C++ testbenches that call into the simulator via DPI-C |
| 3 | Configurable HSI targets | FPGA part and processor target passed to `hsi` during BSP generation are currently driven by the `[[platform]]` properties dict; exposing typed config keys would be cleaner |
| 4 | Subcore support for custom IPs | Declare that a custom IP depends on another IP internally (e.g. a `clk_wiz` sub-core) so the packager carries the dependency correctly. BDs get automatic subcore tracking already; standalone IPs don't |

Feature additions

| Priority | Feature | Description |
|---|---|---|
| 1 | ILA / debug core insertion | Add and configure Integrated Logic Analyzer cores during implementation, with an optional GUI mode for probe assignment |
| 2 | QSPI flash programming | Extend `program` to write bitstreams to QSPI flash over JTAG, not just direct FPGA configuration |
| 3 | HLS support | Bring Vitis HLS projects under the same `project.toml` and CLI; synthesized HLS output would export as a first-class IP feeding directly into `[[ip]]` and the BD flow |
| 4 | Dependency graph | `graph` command to print or visualize the full entity dependency tree (fpga → ip → core → bd → synth → platform → app) |

Infrastructure

| Priority | Feature | Description |
|---|---|---|
| 1 | CI/CD | Automatically run synthesis and validation from git push/PR events using xviv's CLI, typically on self-hosted infrastructure due to Vivado resource and licensing constraints |
| 2 | Remote synthesis server | Transparently dispatch synthesis jobs to a licensed network machine while preserving the same local xviv command workflow |
---

## License

MIT
