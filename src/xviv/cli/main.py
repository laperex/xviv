import argparse
import os

import argcomplete

from xviv.cli import commands
from xviv.config.loader import load_config, resolve_config
from xviv.utils.log import _setup_logging


def run() -> None:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)
	p.add_argument("--config", "-c", default="", metavar="TOML",
		help="Project configuration file (default: project.toml)")
	p.add_argument("--log-file", default="", metavar="FILE",
		help="Append debug log to FILE")

	sub = p.add_subparsers(dest="command", required=True)
	# sub.add_argument("--dry-run", action="store_true", default=False, help="Dry Run")

	registry: dict[str, commands.Command] = {}
	for cls in [
		commands.CreateCommand,
		commands.SearchCommand,
		commands.EditCommand,
		commands.GenerateCommand,
		commands.SynthCommand,
		commands.OpenCommand,
		commands.SimulateCommand,
		commands.ReloadCommand,
		commands.BuildCommand,
		commands.ProgramCommand,
		commands.ProcessorCommand,
		# commands.GraphCommand,
		# commands.StatusCommand,
	]:
		cls.register(sub)        # sets up the sub-parser
		registry[cls.name] = cls()  # one instance per command

	argcomplete.autocomplete(p)
	args = p.parse_args()

	cfg_path = os.path.abspath(resolve_config(args.config))

	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)
	
	_setup_logging("xviv.log")

	cfg = load_config(cfg_path).build()

	cfg.get_vivado().dry_run = args.dry_run

	registry[args.command].run(cfg, args)