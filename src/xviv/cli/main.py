import argparse
import os

import argcomplete

from xviv.cli.commands import register_commands
from xviv.config.loader import load_config, resolve_config
from xviv.utils.log import _setup_logging


def run() -> None:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)
	p.add_argument("--config", "-c", help="Project configuration file (default: %(default)s)", default="project.toml")
	p.add_argument("--log", metavar="FILE", help="Append debug log to file", default="")

	registry = register_commands(p.add_subparsers(dest="command", required=True))

	argcomplete.autocomplete(p)
	args = p.parse_args()

	cfg_path = os.path.abspath(resolve_config(args.config))

	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	_setup_logging("xviv.log")

	cfg = load_config(cfg_path).build()

	registry[args.command].run(cfg, args)