#!/usr/bin/env python3
"""
xviv  -  FPGA project controller for Vivado / Vitis
Reads project.toml and drives Vivado, xsct, or standalone Xilinx tools.

Usage:
xviv [--config project.toml] <command> [options]

Vivado-backed commands:
create-ip    --ip   <n>
edit-ip      --ip   <n>
ip-config    --ip   <n>
create-bd    --bd   <n>
edit-bd      --bd   <n>
generate-bd  --bd   <n>
export-bd    --bd   <n>
bd-config    --bd   <n>
synthesis    --top  <module>
synth-config --top  <module>
simulate     --top  <sim_top>  [--so libdpi]  [--dpi-lib ./build/libs]
open-dcp     --top  <module>   [--dcp post_synth]

xsct-backed commands (MicroBlaze / Vitis):
create-platform  --platform <n>
platform-build   --platform <n>
create-app       --app <n>  [--platform <n>]  [--template <t>]
app-build        --app <n>  [--info]
program          (--bitstream <path> | --platform <n>)  [--elf <path> | --app <n>]
processor        (--reset | --status)
jtag-monitor     --uart

Standalone commands:
open-wdb        --top <sim_top>
reload-wdb      --top <sim_top>
open-snapshot   --top <sim_top>
reload-snapshot --top <sim_top>
"""

import argparse
import glob as _glob
import logging
import os
import subprocess
import sys
import argcomplete

from xviv import command, config, wrapper
from xviv import waveform
from xviv.bd_deps import find_all_ip_ooc_info
from xviv.config import _resolve_globs, generate_config_tcl, load_config
from xviv.hooks import generate_bd_hooks, generate_ip_hooks, generate_synth_hooks
from xviv.platform import _app_dir, _bsp_dir, _find_elf, _hw_server, _mb_tool, _platform_paths, _resolve_app_cfg, _resolve_platform_cfg, _transform_app_makefile
from xviv.utils import _atomic_symlink, _git_sha_tag, _setup_logging
from xviv.vitis import _find_xsct_script, _get_vitis_env, run_xsct, run_xsct_live
from xviv.vivado import _find_tcl_script, _strip_bd_tcl, run_vivado, run_vivado_xelab, run_vivado_xsim, run_vivado_xvlog
from xviv.waveform import open_snapshot, open_wdb, reload_snapshot, reload_wdb

logger = logging.getLogger(__name__)


def _find_config(prefix, parsed_args, **kwargs) -> str:
	return getattr(parsed_args, "config", None) or "project.toml"


def _ip_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [ip["name"] for ip in cfg.get("ip", [])]
	except Exception:
		return []


def _bd_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [bd["name"] for bd in cfg.get("bd", [])]
	except Exception:
		return []


def _top_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s["top"] for s in cfg.get("synthesis", [])]
	except Exception:
		return []


def _dcp_stems_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		top = getattr(parsed_args, "top", None)
		build_dir = cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR)
		if not top:
			return ["post_synth", "post_place", "post_route"]
		stems = [
			os.path.splitext(os.path.basename(f))[0]
			for f in _glob.glob(os.path.join(build_dir, top, "*.dcp"))
		]
		return stems or ["post_synth", "post_place", "post_route"]
	except Exception:
		return ["post_synth", "post_place", "post_route"]


def _platform_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [p["name"] for p in cfg.get("platform", [])]
	except Exception:
		return []


def _app_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [a["name"] for a in cfg.get("app", [])]
	except Exception:
		return []


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)
	p.add_argument(
		"--config", "-c",
		default="project.toml",
		metavar="TOML",
		help="Project configuration file (default: project.toml)",
	)
	p.add_argument(
		"--log-file",
		default="",
		metavar="FILE",
		help="Append debug log to FILE",
	)

	sub = p.add_subparsers(dest="command", required=True)

	def _cmd(name: str, help_str: str):
		return sub.add_parser(name, help=help_str)

	for name in ("create-ip", "edit-ip"):
		c = _cmd(name, f"{name} for the specified IP")
		c.add_argument(
			"--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
		).completer = _ip_names_completer

	c = _cmd("ip-config", "Generate a starter hooks file for an IP")
	c.add_argument(
		"--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
	).completer = _ip_names_completer

	for name in ("create-bd", "edit-bd", "generate-bd"):
		c = _cmd(name, f"{name} for the specified Block Design")
		c.add_argument(
			"--bd", required=True, help="BD name as defined in [[bd]] TOML entry"
		).completer = _bd_names_completer

	c = _cmd("export-bd", "Export the current BD as a versioned re-runnable TCL script")
	c.add_argument(
		"--bd",
		required=True,
		help="BD name as defined in [[bd]] TOML entry"
	).completer = _bd_names_completer

	c = _cmd("bd-config", "Generate a starter hooks file for a BD")
	c.add_argument(
		"--bd",
		required=True,
		help="BD name as defined in [[bd]] TOML entry"
	).completer = _bd_names_completer

	c = _cmd("synthesis", "Synthesise, place, route, and write bitstream")
	# --top and --bd are mutually exclusive
	top_bd = c.add_mutually_exclusive_group(required=True)
	top_bd.add_argument(
		"--top",
		default="",
		help="Top module name (flat RTL synthesis)",
	).completer = _top_names_completer
	top_bd.add_argument(
		"--bd",
		default="",
		help="BD name: OOC-synthesise all custom IPs then synthesise the BD wrapper",
	).completer = _bd_names_completer

	c.add_argument("--out-of-context-synth", action="store_true", dest="out_of_context_synth")
	c.add_argument("--out-of-context-run", action="store_true", dest="out_of_context_run", default=False)

	c.add_argument("--report-all",     action="store_true", dest="report_all")
	c.add_argument("--report-synth",   action="store_true", dest="report_synth")
	c.add_argument("--report-place",   action="store_true", dest="report_place")
	c.add_argument("--report-route",   action="store_true", dest="report_route")
	c.add_argument("--generate-netlist", action="store_true", dest="generate_netlist")

	c = _cmd("synth-config", "Generate a starter hooks file for synthesis")
	c.add_argument(
		"--top",
		required=True, help="Top module name"
	).completer = _top_names_completer

	c = _cmd("elaborate", "Compile and optionally run simulation")
	c.add_argument(
		"--top",
		required=True, help="Simulation top module"
	).completer = _top_names_completer
	c.add_argument("--so",      default="", help="DPI shared library name (no path/extension)")
	c.add_argument("--dpi-lib", default="", help="Directory containing the DPI .so")
	c.add_argument("--run",     default="", help="Simulation run time, e.g. 1000ns")

	c = _cmd("open-dcp", "Open a checkpoint in Vivado GUI")
	c.add_argument(
		"--top",
		required=True, help="Top module name (locates build/<top>/)"
	).completer = _top_names_completer
	c.add_argument(
		"--dcp",
		default="post_synth", help="Checkpoint stem (default: post_synth)"
	).completer = _dcp_stems_completer

	c = _cmd("open-snapshot", "Open the simulation snapshot in xsim GUI")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("reload-snapshot", "Restart simulation snapshot")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("open-wdb", "Open the waveform database in xsim GUI")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("reload-wdb", "Reload waveform window")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd(
		"create-platform",
		"Generate BSP from XSA using hsi (xsct). "
		"BSP is placed in build/bsp/<platform>.",
	)
	c.add_argument(
		"--platform",
		required=True,
		help="Platform name as defined in [[platform]] TOML entry",
	).completer = _platform_names_completer

	c = _cmd(
		"platform-build",
		"Compile the BSP with make -j<ncpu>.",
	)
	c.add_argument(
		"--platform",
		required=True,
		help="Platform name as defined in [[platform]] TOML entry",
	).completer = _platform_names_completer

	c = _cmd(
		"create-app",
		"Scaffold an application from a Vitis template using hsi (xsct). "
		"App is placed in build/app/<app>. "
		"If the BSP does not yet exist it is created automatically.",
	)
	c.add_argument(
		"--app",
		required=True,
		help="App name as defined in [[app]] TOML entry",
	).completer = _app_names_completer
	c.add_argument(
		"--platform", default="",
		help="Override the platform name specified in the [[app]] TOML entry",
	).completer = _platform_names_completer
	c.add_argument(
		"--template", default="",
		help="Override the app template (e.g. 'empty_application', 'hello_world')",
	)

	c = _cmd(
		"app-build",
		"Compile the application with make -j<ncpu>.",
	)
	c.add_argument(
		"--app",
		required=True,
		help="App name as defined in [[app]] TOML entry",
	).completer = _app_names_completer
	c.add_argument(
		"--info", action="store_true",
		help="Print ELF section sizes and headers after a successful build "
		"(uses microblaze-xilinx-elf-size and microblaze-xilinx-elf-objdump)",
	)

	c = _cmd(
		"program",
		"Download bitstream to FPGA, and optionally load an ELF. "
		"Requires hw_server running (Vivado Hardware Manager or standalone).",
	)
	bit_src = c.add_mutually_exclusive_group()
	bit_src.add_argument(
		"--bitstream", metavar="PATH",
		help="Explicit path to the .bit file to program",
	)
	bit_src.add_argument(
		"--platform", metavar="NAME",
		help="Derive bitstream path from [[platform]] TOML entry",
	).completer = _platform_names_completer

	elf_src = c.add_mutually_exclusive_group()
	elf_src.add_argument(
		"--elf", metavar="PATH",
		help="Explicit path to the .elf file to load",
	)
	elf_src.add_argument(
		"--app", metavar="NAME",
		help="Derive ELF path from [[app]] build directory",
	).completer = _app_names_completer

	c = _cmd(
		"processor",
		"Control the embedded MicroBlaze processor via JTAG.",
	)
	proc_action = c.add_mutually_exclusive_group(required=True)
	proc_action.add_argument(
		"--reset", action="store_true",
		help="Soft-reset the processor (rst -processor then continue)",
	)
	proc_action.add_argument(
		"--status", action="store_true",
		help="Print target list, processor state, and key registers",
	)

	c = _cmd(
		"jtag-monitor",
		"Stream debug output from the embedded processor over JTAG. "
		"Requires the MDM IP in the Vivado design with JTAG UART enabled. "
		"Press Ctrl-C to stop.",
	)
	c.add_argument(
		"--uart", action="store_true", default=True,
		help="Stream JTAG UART output to stdout (default mode)",
	)

	return p


def main() -> None:
	parser = build_parser()

	# echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.zshrc
	argcomplete.autocomplete(parser)
	args = parser.parse_args()

	cfg_path = os.path.abspath(args.config)
	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	cfg = load_config(cfg_path)

	_setup_logging(
		args.log_file or os.path.join(
			os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR)),
			"xviv",
			"xviv.log"
		)
	)

	match args.command:
		case "ip-create":
			command.cmd_ip_create(cfg, project_dir, args.ip)

		case "bd-create":
			command.cmd_bd_create(cfg, project_dir, args.bd)

		case "platform-create":
			command.cmd_platform_create(cfg, project_dir, args.platform)

		case "app-create":
			command.cmd_app_create(cfg, project_dir, args.app, args.platform, args.template)


		case "ip-edit":
			command.cmd_ip_edit(cfg, project_dir, args.ip)

		case "bd-edit":
			command.cmd_bd_edit(cfg, project_dir, args.bd)


		case "ip-config":
			command.cmd_ip_config(cfg, project_dir, args.ip)

		case "bd-config":
			command.cmd_bd_config(cfg, project_dir, args.bd)

		case "top-config":
			command.cmd_top_config(cfg, project_dir, args.top)


		case "bd-generate":
			command.cmd_bd_generate(cfg, project_dir, args.bd)


		case "bd-save":
			command.cmd_bd_save(cfg, project_dir, args.bd)


		case "ip-synth":
			command.cmd_ip_synth(cfg, project_dir, args.ip)

		case "bd-synth":
			command.cmd_bd_synth(cfg, project_dir, args.bd, args.ooc_run)

		case "top-synth":
			command.cmd_top_synth(cfg, project_dir, args.top)


		case "dcp-open":
			command.cmd_dcp_open(cfg, project_dir, args.top, args.dcp)

		case "snapshot-open":
			command.cmd_snapshot_open(cfg, project_dir, args.top)

		case "wdb-open":
			command.cmd_snapshot_open(cfg, project_dir, args.top)


		case "top-elaborate":
			command.cmd_top_elab(cfg, project_dir, args.top, args.run)


		case "snapshot-reload":
			command.cmd_snapshot_reload(cfg, project_dir, args.top)

		case "wdb-reload":
			command.cmd_snapshot_reload(cfg, project_dir, args.top)


		case "platform-build":
			command.cmd_platform_build(cfg, project_dir, args.platform)

		case "app-build":
			command.cmd_app_build(cfg, project_dir, args.app, args.info)


		case "program":
			command.cmd_program(cfg, project_dir, args.app, args.platform, args.elf, args.bitstream)


		case "processor":
			command.cmd_processor(cfg, args.reset, args.status)


		case _:
			parser.print_help()
			sys.exit(1)


if __name__ == "__main__":
	main()
