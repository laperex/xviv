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
import sys
import argcomplete

from xviv import command, config
from xviv.utils import _setup_logging

logger = logging.getLogger(__name__)


def _find_config(prefix, parsed_args, **kwargs) -> str:
	return getattr(parsed_args, "config", None) or "project.toml"


def _ip_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [ip["name"] for ip in cfg.get("ip", [])]
	except Exception:
		return []


def _bd_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [bd["name"] for bd in cfg.get("bd", [])]
	except Exception:
		return []


def _top_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s["top"] for s in cfg.get("synthesis", [])]
	except Exception:
		return []


def _dcp_stems_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
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
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [p["name"] for p in cfg.get("platform", [])]
	except Exception:
		return []


def _app_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = config.load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [a["name"] for a in cfg.get("app", [])]
	except Exception:
		return []


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)

	p.add_argument("--config", "-c", default="project.toml", metavar="TOML", help="Project configuration file (default: project.toml)")
	p.add_argument("--log-file", default="", metavar="FILE", help="Append debug log to FILE")

	sub = p.add_subparsers(dest="command", required=True)

	# ------------------------------------------------------------------
	# create --ip | --bd | --app [--platform] [--template] | --platform
	# ------------------------------------------------------------------
	c = sub.add_parser("create", help="Create an IP, BD, platform, or app")
	
	c.add_argument("--ip",       metavar="NAME", help="IP name").completer  = _ip_names_completer
	c.add_argument("--bd",       metavar="NAME", help="BD name").completer  = _bd_names_completer
	c.add_argument("--app",      metavar="NAME", help="App name").completer = _app_names_completer
	c.add_argument("--platform", metavar="NAME", 
		help="Platform to create, or platform override when used with --app").completer = _platform_names_completer
	c.add_argument("--template", metavar="TMPL", default=None,
		help="App template override (used with --app)")

	# ------------------------------------------------------------------
	# edit --ip | --bd
	# ------------------------------------------------------------------
	c = sub.add_parser("edit", help="Open an IP or BD in Vivado for editing")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip", metavar="NAME", help="IP name").completer = _ip_names_completer
	mg.add_argument("--bd", metavar="NAME", help="BD name").completer = _bd_names_completer

	# ------------------------------------------------------------------
	# config --ip | --bd | --top
	# ------------------------------------------------------------------
	c = sub.add_parser("config", help="Generate starter hooks for an IP, BD, or top")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip",  metavar="NAME", help="IP name").completer  = _ip_names_completer
	mg.add_argument("--bd",  metavar="NAME", help="BD name").completer  = _bd_names_completer
	mg.add_argument("--top", metavar="NAME", help="Top module name").completer = _top_names_completer

	# ------------------------------------------------------------------
	# generate --bd
	# ------------------------------------------------------------------
	c = sub.add_parser("generate", help="Generate output products for a BD")
	c.add_argument("--bd", required=True, metavar="NAME",
		help="BD name").completer = _bd_names_completer

	# ------------------------------------------------------------------
	# export --bd
	# ------------------------------------------------------------------
	c = sub.add_parser("export", help="Export BD as a versioned re-runnable TCL script")
	c.add_argument("--bd", required=True, metavar="NAME",
		help="BD name").completer = _bd_names_completer

	# ------------------------------------------------------------------
	# synth --ip | --bd [--ooc-run] | --top
	# ------------------------------------------------------------------
	c = sub.add_parser("synth", help="Synthesise an IP, BD, or top module")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip",  metavar="NAME", help="IP name").completer  = _ip_names_completer
	mg.add_argument("--bd",  metavar="NAME", help="BD name").completer  = _bd_names_completer
	mg.add_argument("--top", metavar="NAME", help="Top module name").completer = _top_names_completer
	c.add_argument("--ooc-run", action="store_true", dest="ooc_run",
		help="Run out-of-context synthesis for leaf IPs (BD only)")

	# ------------------------------------------------------------------
	# open --dcp --top | --snapshot --top | --wdb --top
	# ------------------------------------------------------------------
	c = sub.add_parser("open", help="Open a checkpoint, simulation snapshot, or waveform DB")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--dcp",      metavar="STEM", help="Checkpoint stem (e.g. post_synth)").completer = _dcp_stems_completer
	mg.add_argument("--snapshot", action="store_true", help="Open simulation snapshot in xsim GUI")
	mg.add_argument("--wdb",      action="store_true", help="Open waveform DB in xsim GUI")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Top module / sim top name").completer = _top_names_completer

	# ------------------------------------------------------------------
	# elab --top [--run <time>]
	# ------------------------------------------------------------------
	c = sub.add_parser("elab", help="Compile and optionally run simulation")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Simulation top module").completer = _top_names_completer
	c.add_argument("--run", metavar="TIME", default="",
		help="Simulation run time, e.g. 1000ns")

	# ------------------------------------------------------------------
	# reload --snapshot --top | --wdb --top
	# ------------------------------------------------------------------
	c = sub.add_parser("reload", help="Restart a simulation snapshot or reload a waveform DB")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--snapshot", action="store_true", help="Restart snapshot")
	mg.add_argument("--wdb",      action="store_true", help="Reload waveform window")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Simulation top module").completer = _top_names_completer

	# ------------------------------------------------------------------
	# build --platform | --app [--info]
	# ------------------------------------------------------------------
	c = sub.add_parser("build", help="Compile a BSP platform or application")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--platform", metavar="NAME", help="Platform name").completer = _platform_names_completer
	mg.add_argument("--app",      metavar="NAME", help="App name").completer      = _app_names_completer
	c.add_argument("--info", action="store_true",
		help="Print ELF section sizes after build (used with --app)")

	# ------------------------------------------------------------------
	# program [--app | --platform] [--elf | --bitstream]
	# ------------------------------------------------------------------
	c = sub.add_parser("program", help="Download bitstream and/or ELF to FPGA")
	bit_src = c.add_mutually_exclusive_group()
	bit_src.add_argument("--platform",  metavar="NAME", help="Derive bitstream from [[platform]] entry").completer = _platform_names_completer
	bit_src.add_argument("--bitstream", metavar="PATH", help="Explicit path to .bit file")
	elf_src = c.add_mutually_exclusive_group()
	elf_src.add_argument("--app", metavar="NAME", help="Derive ELF from [[app]] build dir").completer = _app_names_completer
	elf_src.add_argument("--elf", metavar="PATH", help="Explicit path to .elf file")

	# ------------------------------------------------------------------
	# processor --reset | --status
	# ------------------------------------------------------------------
	c = sub.add_parser("processor", help="Control the embedded processor via JTAG")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--reset",  action="store_true", help="Soft-reset the processor")
	mg.add_argument("--status", action="store_true", help="Print processor state and registers")

	return p


def main() -> None:
	parser = build_parser()
	argcomplete.autocomplete(parser)
	args = parser.parse_args()

	cfg_path    = os.path.abspath(args.config)
	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	cfg = config.load_config(cfg_path)
	_setup_logging(
		args.log_file or os.path.join(
			project_dir,
			cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR),
			"xviv", "xviv.log",
		)
	)

	match args.command:
		case "create":
			if args.ip:
				command.cmd_ip_create(cfg, project_dir, args.ip)
			elif args.bd:
				command.cmd_bd_create(cfg, project_dir, args.bd)
			elif args.app:
				command.cmd_app_create(cfg, project_dir, args.app, args.platform, args.template)
			elif args.platform:
				command.cmd_platform_create(cfg, project_dir, args.platform)
			else:
				parser.parse_args(['create', '--help'])

		case "edit":
			if args.ip:
				command.cmd_ip_edit(cfg, project_dir, args.ip)
			elif args.bd:
				command.cmd_bd_edit(cfg, project_dir, args.bd)

		case "config":
			if args.ip:
				command.cmd_ip_config(cfg, project_dir, args.ip)
			elif args.bd:
				command.cmd_bd_config(cfg, project_dir, args.bd)
			elif args.top:
				command.cmd_top_config(cfg, project_dir, args.top)

		case "generate":
			command.cmd_bd_generate(cfg, project_dir, args.bd)

		case "export":
			command.cmd_bd_export(cfg, project_dir, args.bd)

		case "synth":
			if args.ip:
				command.cmd_ip_synth(cfg, project_dir, args.ip)
			elif args.bd:
				command.cmd_bd_synth(cfg, project_dir, args.bd, args.ooc_run)
			elif args.top:
				command.cmd_top_synth(cfg, project_dir, args.top)

		case "open":
			if args.dcp:
				command.cmd_dcp_open(cfg, project_dir, args.dcp, args.top)
			elif args.snapshot:
				command.cmd_snapshot_open(cfg, project_dir, args.top)
			elif args.wdb:
				command.cmd_wdb_open(cfg, project_dir, args.top)

		case "elab":
			command.cmd_top_elab(cfg, project_dir, args.top, args.run)

		case "reload":
			if args.snapshot:
				command.cmd_snapshot_reload(cfg, project_dir, args.top)
			elif args.wdb:
				command.cmd_wdb_reload(cfg, project_dir, args.top)

		case "build":
			if args.platform:
				command.cmd_platform_build(cfg, project_dir, args.platform)
			elif args.app:
				command.cmd_app_build(cfg, project_dir, args.app, args.info)

		case "program":
			command.cmd_program(
				cfg, project_dir,
				args.app, args.platform, args.elf, args.bitstream,
			)

		case "processor":
			command.cmd_processor(cfg, args.reset, args.status)

		case _:
			parser.print_help()
			sys.exit(1)


if __name__ == "__main__":
	main()