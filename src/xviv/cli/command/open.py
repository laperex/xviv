import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, target_group, c_top_all, dcp_stems_completer
from xviv.functions.synthesis    import cmd_dcp_open
from xviv.functions.simulation import cmd_wdb_open


class OpenCommand(Command):
	name = "open"
	help = "Open a checkpoint, or waveform DB"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)

		# What to open: exactly one of --dcp / --wdb
		mode = c.add_mutually_exclusive_group(required=True)
		arg(mode, "--dcp", metavar="STEM",
			help="Checkpoint stem (e.g. post_synth)",
			completer=dcp_stems_completer)
		mode.add_argument("--wdb",      action="store_true",
			help="Open waveform DB in xsim GUI")

		# Target: exactly one of --ip / --bd / --top
		target_group(c, ip=True, bd=True, top=c_top_all)

		c.add_argument("--nogui", action="store_true", help="Do not open in GUI (TCL mode)")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.dcp:
			cmd_dcp_open(cfg, args.dcp, top_name=args.top, bd_name=args.bd, nogui=args.nogui)
		elif args.wdb:
			cmd_wdb_open(cfg, args.top, nogui=args.nogui)