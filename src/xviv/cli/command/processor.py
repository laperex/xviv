import argparse
from xviv.cli.command.base import Command
from xviv.functions.xsct import cmd_processor

class ProcessorCommand(Command):
	name = "processor"
	help = "Control the embedded processor via JTAG"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c  = sub.add_parser(cls.name, help=cls.help)
		mg = c.add_mutually_exclusive_group(required=True)
		mg.add_argument("--reset",  action="store_true", help="Soft-reset the processor")
		mg.add_argument("--status", action="store_true", help="Print processor state and registers")

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_processor(cfg, args.reset, args.status)