import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_top_synth
from xviv.functions.simulation import cmd_snapshot_reload, cmd_wdb_reload


class ReloadCommand(Command):
	name = "reload"
	help = "Restart a simulation snapshot or reload a waveform DB"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c  = sub.add_parser(cls.name, help=cls.help)
		mg = c.add_mutually_exclusive_group(required=True)
		mg.add_argument("--snapshot", action="store_true", help="Restart snapshot")
		mg.add_argument("--wdb",      action="store_true", help="Reload waveform window")
		arg(c, "--top", required=True, metavar="NAME",
			help="Simulation top module", completer=c_top_synth)

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.snapshot:
			cmd_snapshot_reload(cfg, args.top)
		elif args.wdb:
			cmd_wdb_reload(cfg, args.top)