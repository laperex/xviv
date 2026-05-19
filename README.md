# xviv

[![PyPI](https://img.shields.io/pypi/v/xviv)](https://pypi.org/project/xviv/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/xviv)](https://pypi.org/project/xviv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

CLI project controller for Vivado and Vitis. Describe your whole project in a `project.toml`, run everything from the terminal, keep the GUI for the parts that actually need it.

```
pip install xviv
```

> **Work in progress.** xviv is being actively developed alongside a real project and the API is not stable. Commands, config keys, and behaviour can change between versions without notice. It works, but expect rough edges.

---

Vivado can be difficult to use in a team environment. Project files often contain absolute paths, block designs are hard to review cleanly in git, and automation usually depends on generated TCL scripts rather than a clean, reproducible CLI workflow. As a result, teams often end up either committing large amounts of generated project state or maintaining custom rebuild scripts to keep projects portable across machines and Vivado versions.

xviv takes a different approach. Instead of relying on generated project files, the entire build is described in a single config file: FPGA target, IP cores, block designs, RTL sources, synthesis runs, simulations, and embedded platform configuration. A clean clone is enough to reproduce the project, while the build directory itself remains fully gitignored.

For block designs, xviv exports re-runnable TCL snapshots that can be version-controlled and reviewed like normal source files. It also embeds git metadata directly into the generated bitstream using `USR_ACCESS` — bits [27:0] store the short commit SHA, while bit 28 indicates whether the working tree was dirty at build time. That makes it possible to trace any `.bit` file back to the exact source revision that produced it.

The goal was never to eliminate the Vivado GUI entirely. Tools like Edalize focus primarily on non-project automation flows, which can make some Vivado workflows — especially block design editing and IP packaging — less convenient. xviv instead automates the parts Vivado handles well through scripting, while still allowing developers to use the GUI when it is actually useful.

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

**`[[fpga]]`** — part number and optional board definition. The first entry is the default; later sections can override with `fpga = "name"`.

**`[[design]]`** — RTL sources and top module for a synthesisable design.

**`[[ip]]`** — custom IP to package with the Vivado IP Packager. xviv handles the packaging and wires the IP repo into the project. Use `[[wrapper]]` alongside it if the IP has interface ports that need flattening (requires `pyslang`).

**`[[core]]`** — an instance of a catalog IP (Xilinx built-in or custom). Identified by a partial VLNV that resolves against the live catalog; tab completion works here.

**`[[bd]]`** — a block design. xviv creates it, opens the editor, and exports its state as a TCL snapshot under `scripts/xviv/bd/`. After that, `create --bd <name>` recreates it non-interactively from the snapshot on any machine.

**`[[synth]]`** — a synthesis run. Identified by one of `design`, `bd`, or `core`. Controls the full pipeline (which stages to run, incremental flows, directives, reports, output artifacts).

**`[[simulation]]`** — a simulation target. Backends: `xsim` (default) or `verilator`. Supports UVM, SDF back-annotation, post-synthesis and post-implementation modes.

**`[[platform]]` / `[[app]]`** — Vitis embedded flow. `platform` generates a BSP from the XSA produced by synthesis; `app` scaffolds and builds a Vitis application against it.

**`[[formal]]`** — SymbiYosys formal verification target. Modes: `bmc`, `prove`, `cover`. Vivado not required.

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

[[app]]
name     = "firmware"
platform = "mb_platform"
template = "empty_application"

[[simulation]]
name    = "tb_gamma"
sources = ["srcs/sim/tb_gamma.sv", "srcs/rtl/**/*.sv"]
backend = "xsim"

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
xviv edit   --ip gamma_axi        # opens IP Packager

# Create a block design and open the editor
xviv create --bd system
xviv edit   --bd system

# After editing, generate output products
xviv generate --bd system

# Instantiate a catalog IP (VLNV tab-completes from live catalog)
xviv create --core clk_wiz_0 --vlnv clk_wiz:6.0

# Search the IP catalog
xviv search axi4 dma
```

### Synthesis

```sh
xviv synth --design top          # RTL design
xviv synth --bd     system       # block design
xviv synth --core   clk_wiz_0    # out-of-context IP core

# Open a checkpoint (path tab-completes)
xviv open --dcp build/synth/system/checkpoints/route.dcp
```

By default, every synth run produces synth/place/route checkpoints and a bitstream. Fine-grained control is in `project.toml`: `run_synth`, `run_place`, `run_route`, incremental flows, directive overrides, reports, netlists.

### Simulation

```sh
xviv simulate --target tb_gamma
xviv simulate --target tb_gamma --run 1000ns
xviv simulate --target tb_gamma --mode post_synth_functional

# Open the waveform DB without re-running
xviv open   --wdb tb_gamma
xviv reload --target tb_gamma    # hot-reload snapshot in a live xsim session
```

### Embedded

```sh
xviv build --platform mb_platform
xviv build --app firmware
xviv build --app firmware --info    # print ELF section sizes after build

xviv program --platform mb_platform --app firmware
xviv program --bitstream path/to/custom.bit --elf path/to/custom.elf

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

Completion is dynamic: IP, BD, design, and simulation names come from `project.toml`; VLNV strings come from the live Vivado IP catalog with descriptions inline; DCP paths complete from the known checkpoint locations for each synth run.

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
│           └── system.tcl    # BD TCL snapshot — version control this
└── build/                    # gitignore everything here
```

`scripts/xviv/` is the only generated directory that belongs in version control. Everything under `build/` is reproducible.

---

## Roadmap

Roughly in order of priority.

**Near-term**

- **Simulation config restructure** — the `[[simulation]]` section has grown unwieldy and backend-specific fields don't map cleanly onto both xsim and Verilator. A cleaner split is needed, which may require command changes.
- **DPI support** — C/C++ testbenches that call into the simulator via DPI-C. Follows naturally from the simulation restructure.
- **Unit tests** — the TCL generator and config loader have almost no test coverage. Required before the API can be considered stable.
- **Configurable HSI targets** — the FPGA part and processor target passed to `hsi` during BSP generation are currently hardcoded in the XSCT script. Should be driven from `[[platform]]` config.
- **Subcore support for custom IPs** — declare that a custom IP depends on another IP internally (e.g. a `clk_wiz` sub-core), so the packager carries the dependency correctly. BDs get automatic subcore tracking already; standalone IPs don't.

**Feature additions**

- **ILA / debug core insertion** — add and configure Integrated Logic Analyzer cores during implementation, with an optional GUI mode for probe assignment.
- **QSPI flash programming** — extend `program` to write bitstreams to QSPI flash over JTAG, not just direct FPGA configuration.
- **HLS support** — bring Vitis HLS projects under the same `project.toml` and CLI. Synthesised HLS output would export as a first-class IP feeding directly into `[[ip]]` and the BD flow.
- **Dependency graph** — `graph` command to print or visualise the full entity dependency tree (fpga → ip → core → bd → synth → platform → app). The skeleton is already in the codebase.

**Infrastructure**

- **CI/CD** — synthesis on push using xviv's own CLI, intended for a dedicated machine rather than shared runners given resource and license constraints.
- **Remote synthesis server** — offload synthesis jobs to a networked machine with the Vivado license, while keeping the local CLI workflow unchanged.

---

## License

MIT
