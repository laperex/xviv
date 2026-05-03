import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, target_group, c_core
from xviv.functions.bd   import cmd_bd_edit
from xviv.functions.core import cmd_core_edit
from xviv.functions.ip   import cmd_ip_edit


class EditCommand(Command):
	name = "edit"
	help = "Open an IP, BD, or core in Vivado for editing"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c  = sub.add_parser(cls.name, help=cls.help)
		# --ip / --bd / --core are all mutually exclusive
		mg = target_group(c, ip=True, bd=True)
		arg(mg, "--core", metavar="NAME", help="Core name", completer=c_core)
		c.add_argument("--nogui", action="store_true", help="Do not open in GUI (TCL mode)")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.ip:
			cmd_ip_edit(cfg, args.ip, nogui=args.nogui)
		elif args.bd:
			cmd_bd_edit(cfg, args.bd, nogui=args.nogui)
		elif args.core:
			cmd_core_edit(cfg, args.core, nogui=args.nogui)