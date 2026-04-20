import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_top_sim
from xviv.functions.simulation import cmd_top_simulate


class SimulateCommand(Command):
	name = "simulate"
	help = "Run simulation"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		arg(c, "--top", required=True, metavar="NAME",
			help="Simulation top module", completer=c_top_sim)
		c.add_argument("--run", metavar="TIME", default="",
			help="Simulation run time, e.g. 1000ns")

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_top_simulate(cfg, args.top, args.run)