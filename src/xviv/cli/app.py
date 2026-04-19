
import os
import sys
import argcomplete
from xviv.cli.commands.bd import cmd_bd_config, cmd_bd_create, cmd_bd_edit, cmd_bd_generate, cmd_bd_synth
from xviv.cli.commands.core import cmd_core_create, cmd_search_core
from xviv.cli.commands.ip import cmd_ip_config, cmd_ip_create, cmd_ip_edit, cmd_ip_synth
from xviv.cli.commands.sim import cmd_top_elaborate, cmd_top_simulate
from xviv.cli.commands.synth import cmd_dcp_open, cmd_synth_config, cmd_top_synth
from xviv.cli.commands.waveform import cmd_snapshot_open, cmd_snapshot_reload, cmd_wdb_open, cmd_wdb_reload
from xviv.cli.commands.xsct import cmd_app_build, cmd_app_create, cmd_platform_build, cmd_platform_create, cmd_processor, cmd_program
from xviv.cli.parser import build_completions_parser
from xviv.config.loader import load_config
from xviv.utils.log import _setup_logging

def run():
	parser = build_completions_parser()
	argcomplete.autocomplete(parser)
	args = parser.parse_args()

	target_config = args.config
	if not target_config:
		if os.path.exists("project.cue"):
			target_config = "project.cue"
		elif os.path.exists("project.toml"):
			target_config = "project.toml"
		else:
			sys.exit("ERROR: Neither project.cue nor project.toml found in current directory.")

	cfg_path    = os.path.abspath(target_config)
	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	cfg = load_config(cfg_path)
	_setup_logging(args.log_file or os.path.join(cfg.build_dir, "xviv", "xviv.log"))

	match args.command:
		case "create":
			if args.ip:
				cmd_ip_create(cfg, args.ip)
			elif args.bd:
				cmd_bd_create(cfg, args.bd)
			elif args.app:
				cmd_app_create(cfg, args.app, args.platform, args.template)
			elif args.platform:
				cmd_platform_create(cfg, args.platform)
			elif args.core:
				cmd_core_create(cfg, args.vlnv, args.core)
			else:
				parser.parse_args(['create', '--help'])

		case "search":
			cmd_search_core(cfg, args.query)

		case "edit":
			if args.ip:
				cmd_ip_edit(cfg, args.ip, nogui=args.nogui)
			elif args.bd:
				cmd_bd_edit(cfg, args.bd, nogui=args.nogui)

		case "config":
			if args.synth:
				cmd_synth_config(cfg, top_name=args.top, bd_name=args.bd, ip_name=args.ip)
			else:
				if args.ip:
					cmd_ip_config(cfg, args.ip)
				elif args.bd:
					cmd_bd_config(cfg, args.bd)
				elif args.top:
					sys.exit('ERROR: --top <top_name> cannot be specified without --synth')

		case "generate":
			cmd_bd_generate(cfg, args.bd)

		case "synth":
			if args.ip:
				cmd_ip_synth(cfg, args.ip)
			elif args.bd:
				cmd_bd_synth(cfg, args.bd, args.ooc_run)
			elif args.top:
				cmd_top_synth(cfg, args.top)

		case "open":
			if args.dcp:
				cmd_dcp_open(cfg, args.dcp, top_name=args.top, bd_name=args.bd, nogui=args.nogui)
			elif args.snapshot:
				cmd_snapshot_open(cfg, args.top, nogui=args.nogui)
			elif args.wdb:
				cmd_wdb_open(cfg, args.top, nogui=args.nogui)

		case "elaborate":
			cmd_top_elaborate(cfg, args.top, args.run)

		case "simulate":
			cmd_top_simulate(cfg, args.top, args.run)

		case "reload":
			if args.snapshot:
				cmd_snapshot_reload(cfg, args.top)
			elif args.wdb:
				cmd_wdb_reload(cfg, args.top)

		case "build":
			if args.platform:
				cmd_platform_build(cfg, args.platform)
			elif args.app:
				cmd_app_build(cfg, args.app, args.info)

		case "program":
			cmd_program(
				cfg,
				args.app, args.platform, args.elf, args.bitstream,
			)

		case "processor":
			cmd_processor(cfg, args.reset, args.status)

		case _:
			parser.print_help()
			sys.exit(1)
