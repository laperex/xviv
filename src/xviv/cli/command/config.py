import argparse
import sys

from xviv.cli.command.base import Command
from xviv.cli.completers import target_group, c_top_synth
from xviv.functions.bd import cmd_bd_config
from xviv.functions.ip import cmd_ip_config
from xviv.functions.synthesis import cmd_synth_config


class ConfigCommand(Command):
	name = "config"
	help = "Generate starter hooks for an IP, BD, or top"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		target_group(c, ip=True, bd=True, top=c_top_synth)
		c.add_argument("--synth", action="store_true",
			help="Generate synthesis hooks (required when using --top)")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.synth:
			cmd_synth_config(cfg, top_name=args.top, bd_name=args.bd, ip_name=args.ip)
		elif args.ip:
			cmd_ip_config(cfg, args.ip)
		elif args.bd:
			cmd_bd_config(cfg, args.bd)
		elif args.top:
			sys.exit("ERROR: --top <name> cannot be specified without --synth")