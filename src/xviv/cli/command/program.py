import argparse
from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_app, c_platform
from xviv.functions.xsct import cmd_program


class ProgramCommand(Command):
	name = "program"
	help = "Download bitstream and/or ELF to FPGA"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c   = sub.add_parser(cls.name, help=cls.help)
		bit = c.add_mutually_exclusive_group()

		arg(bit, "--platform",  metavar="NAME",
			help="Derive bitstream from [[platform]] entry", completer=c_platform)

		bit.add_argument("--bitstream", metavar="PATH", help="Explicit path to .bit file")
		elf = c.add_mutually_exclusive_group()

		arg(elf, "--app", metavar="NAME",
			help="Derive ELF from [[app]] build dir", completer=c_app)
		elf.add_argument("--elf", metavar="PATH", help="Explicit path to .elf file")

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_program(cfg, args.app, args.platform, args.elf, args.bitstream)