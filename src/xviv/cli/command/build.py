import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_app, c_platform
from xviv.functions.xsct import cmd_app_build, cmd_platform_build


class BuildCommand(Command):
	name = "build"
	help = "Compile a BSP platform or application"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c  = sub.add_parser(cls.name, help=cls.help)
		mg = c.add_mutually_exclusive_group(required=True)
		arg(mg, "--platform", metavar="NAME", help="Platform name", completer=c_platform)
		arg(mg, "--app",      metavar="NAME", help="App name",      completer=c_app)
		c.add_argument("--info", action="store_true",
			help="Print ELF section sizes after build (used with --app)")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if   args.platform: cmd_platform_build(cfg, args.platform)
		elif args.app:      cmd_app_build(cfg, args.app, args.info)