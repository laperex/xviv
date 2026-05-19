# xviv

CLI project controller for Vivado and Vitis. Describe your whole project in a `project.toml`, run everything from the terminal, keep the GUI for the parts that actually need it.

```
pip install xviv
```

> **Work in progress.** xviv is being actively developed alongside a real project and the API is not stable. Commands, config keys, and behaviour can change between versions without notice. It works, but expect rough edges.

---

Vivado is hard to use across a team. Project files embed absolute paths, block designs don't diff cleanly, and there's no real CLI surface for automation. The standard workaround is to commit the build directory and hope nobody's on a different version.

xviv fixes this with a single config file that describes the FPGA target, IP cores, block designs, RTL sources, synthesis runs, simulations, and embedded platform — everything needed to reproduce a build from a clean clone. The build directory is fully gitignored. Block design state is exported as re-runnable TCL snapshots that live in version control. Every bitstream gets the git SHA burned into `USR_ACCESS` (bits [27:0] = short SHA, bit 28 = dirty flag), so any `.bit` file on a bench is traceable to its commit.

The design is deliberately not GUI-free. Tools like Hog and Edalize route around Vivado's GUI entirely, which loses a lot — especially for block designs and IP packaging. xviv drives the scriptable parts from the CLI and opens the GUI when you actually need it.

---

## Install

```sh
pip install xviv
```

Requires Python 3.10+. Vivado and Vitis must be on your PATH (source `settings64.sh`), or set `XVIV_VIVADO_SOURCE_SCRIPT` and xviv will source it for you:

```sh
# .env at project root works too
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

Optional: `cue` for schema-validated project files, `pyslang` for SV wrapper generation.

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
activate-global-python-argcomplete        # system-wide
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

## License

MIT