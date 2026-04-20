import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_bd
from xviv.cli.command.bd import cmd_bd_generate


class GenerateCommand(Command):
	name = "generate"
	help = "Generate output products for a BD"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		arg(c, "--bd", required=True, metavar="NAME", help="BD name", completer=c_bd)

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_bd_generate(cfg, args.bd)