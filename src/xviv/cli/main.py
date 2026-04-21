import argparse
import argcomplete
import os
import sys

from xviv.cli.command.base import Command
from xviv.cli.command.create import CreateCommand
from xviv.cli.command.search import SearchCommand
from xviv.cli.command.edit import EditCommand
from xviv.cli.command.config import ConfigCommand
from xviv.cli.command.generate import GenerateCommand
from xviv.cli.command.synth import SynthCommand
from xviv.cli.command.open import OpenCommand
from xviv.cli.command.elaborate import ElaborateCommand
from xviv.cli.command.simulate import SimulateCommand
from xviv.cli.command.reload import ReloadCommand
from xviv.cli.command.build import BuildCommand
from xviv.cli.command.program import ProgramCommand
from xviv.cli.command.processor import ProcessorCommand
from xviv.config.loader import load_config
from xviv.utils.log import _setup_logging

_COMMANDS: list[type[Command]] = [
	CreateCommand,
	SearchCommand,
	EditCommand,
	ConfigCommand,
	GenerateCommand,
	SynthCommand,
	OpenCommand,
	ElaborateCommand,
	SimulateCommand,
	ReloadCommand,
	BuildCommand,
	ProgramCommand,
	ProcessorCommand,
]

def run() -> None:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)
	p.add_argument("--config", "-c", default="", metavar="TOML",
		help="Project configuration file (default: project.cue | project.toml)")
	p.add_argument("--log-file", default="", metavar="FILE",
		help="Append debug log to FILE")

	sub = p.add_subparsers(dest="command", required=True)

	registry: dict[str, Command] = {}
	for cls in _COMMANDS:
		cls.register(sub)        # sets up the sub-parser
		registry[cls.name] = cls()  # one instance per command

	argcomplete.autocomplete(p)
	args = p.parse_args()

	cfg_path = os.path.abspath(_resolve_config(args.config))
	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	cfg = load_config(cfg_path)
	_setup_logging(args.log_file or os.path.join(cfg.build_dir, "xviv", "xviv.log"))

	registry[args.command].run(cfg, args)