# xviv

[![PyPI](https://img.shields.io/pypi/v/xviv)](https://pypi.org/project/xviv/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/xviv)](https://pypi.org/project/xviv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://github.com/laperex/xviv/actions/workflows/test.yml/badge.svg)](https://github.com/laperex/xviv/actions/workflows/test.yml)

CLI project controller for Vivado and Vitis. Describe your whole project in a `project.toml`, run everything from the terminal, keep the GUI for the parts that actually need it.

```
pip install xviv
```

> **Work in progress.** xviv is being actively developed alongside a another project and the API is not stable. Commands, config keys, and behaviour can change between versions without notice. It works, but expect rough edges.

---

Vivado can be difficult to use in a team environment. Project files often contain absolute paths, block designs are hard to review cleanly in git, and automation usually depends on generated TCL scripts rather than a clean, reproducible CLI workflow. As a result, teams often end up either committing large amounts of generated project state or maintaining custom rebuild scripts to keep projects portable across machines and Vivado versions.

xviv takes a different approach. Instead of relying on generated project files, the entire build is described in a single config file: FPGA target, IP cores, block designs, RTL sources, synthesis runs, simulations, and embedded platform configuration. A clean clone is enough to reproduce the project, while the build directory itself remains fully gitignored.

For block designs, xviv exports re-runnable TCL snapshots that can be version-controlled and reviewed like normal source files. It also embeds git metadata directly into the generated bitstream using `USR_ACCESS` - bits [27:0] store the short commit SHA, while bit 28 indicates whether the working tree was dirty at build time. That makes it possible to trace any `.bit` file back to the exact source revision that produced it.

The goal was never to eliminate the Vivado GUI entirely. Tools like Edalize focus primarily on non-project automation flows, which can make some Vivado workflows - especially block design editing and IP packaging - less convenient. xviv instead automates the parts Vivado handles well through scripting, while still allowing developers to use the GUI when it is actually useful.

---

## Install

```sh
pip install xviv
```

Requires Python 3.11+. Vivado and Vitis must be on your PATH (source `settings64.sh`), or set `XVIV_VIVADO_SOURCE_SCRIPT` and xviv will source it for you:

```sh
# .env at project root works too
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

Optional: `pyslang` for SV wrapper generation.

For development:

```sh
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

That runs the full pipeline: synth → opt → place → phys\_opt → route → bitstream. Checkpoints land in `build/synth/top/checkpoints/`. Open any of them with:

```sh
xviv open --dcp build/synth/top/checkpoints/route.dcp
```

---

## project.toml

All sections are arrays of tables. A real project uses some combination of the following:

**`[[fpga]]`** - part number and optional board definition. The first entry is the default; later sections can override with `fpga = "name"`.

**`[[design]]`** - RTL sources and top module for a synthesisable design.

**`[[ip]]`** - custom IP to package with the Vivado IP Packager. xviv handles the packaging and wires the IP repo into the project. Use `[[wrapper]]` alongside it if the IP has interface ports that need flattening (requires `pyslang`).

**`[[core]]`** - an instance of a catalog IP (Xilinx built-in or custom). Identified by a partial VLNV that resolves against the live catalog; tab completion works here.

**`[[bd]]`** - a block design. xviv creates it, opens the editor, and exports its state as a TCL snapshot under `scripts/xviv/bd/`. After that, `create --bd <name>` recreates it non-interactively from the snapshot on any machine.

**`[[synth]]`** - a synthesis run. Identified by one of `design`, `bd`, or `core`. Controls the full pipeline (which stages to run, incremental flows, directives, reports, output artifacts).

**`[[simulation]]`** - a simulation target. Backends: `xsim` (default) or `verilator`. Supports UVM (see `[[uvm]]` below), SDF back-annotation, post-synthesis and post-implementation modes.

**`[[uvm]]`** - a UVM test configuration attached to a `[[simulation]]`. Each entry defines a test name, verbosity, and version, letting you declare multiple UVM tests for the same simulation target.

**`[[platform]]` / `[[app]]`** - Vitis embedded flow. `platform` generates a BSP from the XSA produced by synthesis; `app` scaffolds and builds a Vitis application against it. The `properties` key on `[[platform]]` lets you set BSP properties (e.g. `CONFIG.stdout`) directly from the toml.

**`[[formal]]`** - SymbiYosys formal verification target. Modes: `bmc`, `prove`, `cover`. Vivado not required.

The `[project]` table has two optional keys: `build_dir` (default: `"build"`) and `board_repo_paths`.

A more complete example:

```toml
[project]
build_dir = "build"

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

[platform.properties.CONFIG]
stdout = "mdm_1"
stdin  = "mdm_1"

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
```

---

## Commands

### Working with IPs and BDs

```sh
# Create and package a custom IP
xviv create --ip gamma_axi
xviv edit   --ip gamma_axi          # opens IP Packager

# Create a block design from scratch (opens GUI)
xviv create --bd system

# Import from an existing TCL snapshot and open the editor
xviv create --bd system --source-file scripts/xviv/bd/system.tcl

# Just import and regenerate output products, no GUI
xviv create --bd system --no-generate

# After editing, generate output products
xviv generate --bd system

# Instantiate a catalog IP
xviv create --core clk_wiz_0
xviv edit   --core clk_wiz_0

# Search the IP catalog
xviv search axi4 dma
```

### Synthesis

```sh
xviv synth --design top          # RTL design
xviv synth --bd     system       # block design
xviv synth --core   clk_wiz_0    # out-of-context IP core

# Resume from an existing checkpoint
xviv synth --design top --resume auto      # detect latest checkpoint automatically
xviv synth --design top --resume place     # resume from after place_design

# Control what gets embedded in the bitstream USR_ACCESS field
xviv synth --design top --usr-access-type git   # default: embeds git SHA

# Open a checkpoint (path tab-completes)
xviv open --dcp build/synth/system/checkpoints/route.dcp
```

By default, every synth run embeds the short git SHA into the bitstream `USR_ACCESS` field (bit 28 is set if the working tree was dirty). Fine-grained control is in `project.toml`: `run_synth`, `run_place`, `run_route`, incremental flows, directive overrides, reports, netlists.

### Simulation

```sh
xviv simulate --target tb_gamma
xviv simulate --target tb_gamma --run 1000ns
xviv simulate --target tb_gamma --mode post_synth_functional

# Run a specific UVM test
xviv simulate --target tb_gamma --uvm gamma_basic_test

# Open the waveform DB without re-running
xviv open   --wdb tb_gamma
xviv reload --target tb_gamma    # hot-reload snapshot in a live xsim session
```

Available `--mode` values: `default`, `post_synth_functional`, `post_synth_timing`, `post_impl_functional`, `post_impl_timing`.

### Embedded

```sh
xviv build --platform mb_platform
xviv build --app firmware
xviv build --app firmware --info    # print ELF section sizes after build

# Program with default FPGA and processor filters (xc7a* / MicroBlaze #0*)
xviv program --platform mb_platform --app firmware

# Explicit paths or custom target filters
xviv program --bitstream path/to/custom.bit --elf path/to/custom.elf
xviv program --platform mb_platform --fpga "xc7a35t*" --processor "MicroBlaze #0*"
xviv program --platform mb_platform --reset-duration 1000   # ms before loading ELF

xviv processor --reset
xviv processor --status
```

### Formal

```sh
# Run a named target, or all targets if --target is omitted
xviv formal --target gamma_props
xviv formal
```

On failure, the counterexample trace path is printed with a `gtkwave` command ready to paste.

Every command accepts `--dry-run` to print the generated TCL without executing.

---

## Shell completion

```sh
activate-global-python-argcomplete          # system-wide
eval "$(register-python-argcomplete xviv)"  # or per-shell (bash)
```

Completion is dynamic: IP, BD, design, and simulation names come from `project.toml`; VLNV strings come from the live Vivado IP catalog with descriptions inline; DCP paths complete from the known checkpoint locations for each synth run; UVM test names filter to the selected simulation target; bitstream and ELF paths complete from known output locations.

---

## Project layout

```
project/
├── project.toml
├── .env                      # optional: XVIV_VIVADO_SOURCE_SCRIPT=...
├── srcs/
│   ├── rtl/
│   ├── sim/
│   └── sw/
├── constraints/
├── scripts/
│   └── xviv/
│       └── bd/
│           └── system.tcl    # BD TCL snapshot - version control this
└── build/                    # gitignore everything here
```

`scripts/xviv/` is the only generated directory that belongs in version control. Everything under `build/` is reproducible.

---

## Roadmap

Roughly in order of priority.

**Near-term**

- **DPI support** - C/C++ testbenches that call into the simulator via DPI-C.
- **Configurable HSI targets** - the FPGA part and processor target passed to `hsi` during BSP generation are currently driven by the `[[platform]]` properties dict; exposing typed config keys would be cleaner.
- **Subcore support for custom IPs** - declare that a custom IP depends on another IP internally (e.g. a `clk_wiz` sub-core), so the packager carries the dependency correctly. BDs get automatic subcore tracking already; standalone IPs don't.

**Feature additions**

- **ILA / debug core insertion** - add and configure Integrated Logic Analyzer cores during implementation, with an optional GUI mode for probe assignment.
- **QSPI flash programming** - extend `program` to write bitstreams to QSPI flash over JTAG, not just direct FPGA configuration.
- **HLS support** - bring Vitis HLS projects under the same `project.toml` and CLI. Synthesised HLS output would export as a first-class IP feeding directly into `[[ip]]` and the BD flow.
- **Dependency graph** - `graph` command to print or visualise the full entity dependency tree (fpga → ip → core → bd → synth → platform → app). The skeleton is already in the codebase.

**Infrastructure**

- **CI/CD** - synthesis on push using xviv's own CLI, intended for a dedicated machine rather than shared runners given resource and license constraints.
- **Remote synthesis server** - offload synthesis jobs to a networked machine with the Vivado license, while keeping the local CLI workflow unchanged.

---

## License

MIT