import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import target_group, c_top_synth
from xviv.cli.command.bd    import cmd_bd_synth
from xviv.functions.ip    import cmd_ip_synth
from xviv.functions.synthesis import cmd_top_synth


class SynthCommand(Command):
	name = "synth"
	help = "Synthesise an IP, BD, or top module"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		target_group(c, ip=True, bd=True, top=c_top_synth)
		c.add_argument("--ooc-run", action="store_true", dest="ooc_run",
			help="Run out-of-context synthesis for leaf IPs (BD only)")

	def run(self, cfg, args: argparse.Namespace) -> None:
		if args.ip:
			cmd_ip_synth(cfg, args.ip)
		elif args.bd:
			cmd_bd_synth(cfg, args.bd, args.ooc_run)
		elif args.top:
			cmd_top_synth(cfg, args.top)