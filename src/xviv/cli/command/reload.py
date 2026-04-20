import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_top_synth
from xviv.functions.simulation import cmd_wdb_reload


class ReloadCommand(Command):
	name = "reload"
	help = "Reload a live waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c  = sub.add_parser(cls.name, help=cls.help)
		arg(c, "--top", required=True, metavar="NAME", help="Simulation top module", completer=c_top_synth)

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_wdb_reload(cfg, args.top)