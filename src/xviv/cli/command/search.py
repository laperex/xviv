import argparse

from xviv.cli.command.base import Command
from xviv.cli.completers import arg, c_core_vlnv
from xviv.functions.core import cmd_search_core


class SearchCommand(Command):
	name = "search"
	help = "Search Vivado's IP catalog by name, VLNV, or keyword"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		c = sub.add_parser(cls.name, help=cls.help)
		arg(c, "query", metavar="QUERY",
			help="IP name, partial VLNV, or keyword (e.g. 'fifo', 'clk_wiz')",
			completer=c_core_vlnv)

	def run(self, cfg, args: argparse.Namespace) -> None:
		cmd_search_core(cfg, args.query)