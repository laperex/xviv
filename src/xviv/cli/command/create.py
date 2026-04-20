import argparse
import sys

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_ip, c_bd, c_app, c_platform, c_core, c_core_instance
from xviv.cli.command.bd   import cmd_bd_create
from xviv.functions.core import cmd_core_create
from xviv.functions.ip   import cmd_ip_create
from xviv.functions.xsct import cmd_app_create, cmd_platform_create


class CreateCommand(Command):
	name = "create"
	help = "Create an IP, BD, platform, or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		arg(c, "--ip",       metavar="NAME", help="IP name",  completer=c_ip)
		arg(c, "--bd",       metavar="NAME", help="BD name",  completer=c_bd)
		arg(c, "--app",      metavar="NAME", help="App name", completer=c_app)
		arg(c, "--platform", metavar="NAME",
			help="Platform to create, or platform override when used with --app",
			completer=c_platform)
		arg(c, "--core", metavar="NAME", nargs="?", const="", default=None,
			help="Core instance name (optional — derived from --vlnv if omitted)",
			completer=c_core)
		arg(c, "--vlnv", default=None,
			help="VLNV of IP from Vivado's IP catalog",
			completer=c_core_instance)
		c.add_argument("--template", metavar="TMPL", default=None,
					help="App template override (used with --app)")
		c.add_argument("--edit", action="store_true", help="Customize in GUI")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.ip:
			cmd_ip_create(cfg, args.ip)
		elif args.bd:
			cmd_bd_create(cfg, args.bd)
		elif args.app:
			cmd_app_create(cfg, args.app, args.platform, args.template)
		elif args.platform:
			cmd_platform_create(cfg, args.platform)
		elif args.core is not None:
			cmd_core_create(cfg, args.vlnv, args.core, args.edit)
		else:
			sys.exit("ERROR: one of --ip / --bd / --app / --platform / --core is required")