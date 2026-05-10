import argparse
from abc import ABC, abstractmethod
import sys
from typing import Any

from xviv.cli.completers import arg, target_group, c_ip, c_bd, c_app, c_platform, c_core, c_core_instance, c_sim_target
from xviv.config.project import XvivConfig
from xviv.functions.bd import cmd_bd_create, cmd_bd_edit, cmd_bd_generate, cmd_bd_synth
from xviv.functions.core import cmd_core_create, cmd_core_edit, cmd_search_core
from xviv.functions.ip import cmd_ip_create, cmd_ip_edit
from xviv.functions.simulation import cmd_simulate, cmd_wdb_open, cmd_wdb_reload
from xviv.functions.synthesis import cmd_dcp_open, cmd_design_synth
from xviv.functions.xsct import cmd_app_build, cmd_app_create, cmd_platform_build, cmd_platform_create, cmd_processor, cmd_program


class Command(ABC):
	name: str
	help: str
	c: Any

	@classmethod
	@abstractmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		cls.c = sub.add_parser(cls.name, help=cls.help)
		cls.c.add_argument("--dry-run", action="store_true",
			help="Print TCL without executing")

	@abstractmethod
	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		cfg.get_vivado().dry_run = args.dry_run


class CreateCommand(Command):
	name = "create"
	help = "Create an IP, BD, platform, or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, ip=True, bd=True, app=True, platform=True, core=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.ip:
			cmd_ip_create(cfg, ip_name=args.ip)
		elif args.bd:
			cmd_bd_create(cfg, bd_name=args.bd)
		elif args.core:
			cmd_core_create(cfg, core_name=args.core)
		elif args.app:
			cmd_app_create(cfg, app_name=args.app, platform_name=args.platform)
		elif args.platform:
			cmd_platform_create(cfg, platform_name=args.platform)
		else:
			raise RuntimeError("ERROR: one of --ip / --bd / --core / --app / --platform is required")


class BuildCommand(Command):
	name = "build"
	help = "Compile a BSP platform or application"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, app=True, platform=True)

		c.add_argument("--info", action="store_true", help="Print ELF section sizes after build (used with --app)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.platform:
			cmd_platform_build(cfg, args.platform)
		elif args.app:
			cmd_app_build(cfg, args.app, args.info)


class EditCommand(Command):
	name = "edit"
	help = "Open an IP, BD, or core in Vivado for editing"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, ip=True, bd=True, core=True)
		
		c.add_argument("--nogui", action="store_true", help="Do not edit in GUI")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.ip:
			cmd_ip_edit(cfg, ip_name=args.ip, nogui=args.nogui)
		elif args.bd:
			cmd_bd_edit(cfg, bd_name=args.bd, nogui=args.nogui)
		elif args.core:
			cmd_core_edit(cfg, core_name=args.core, nogui=args.nogui)


class GenerateCommand(Command):
	name = "generate"
	help = "Generate output products for a BD"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		arg(c, "--bd", required=True, metavar="NAME", help="BD name", completer=c_bd)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_bd_generate(cfg, args.bd)


class OpenCommand(Command):
	name = "open"
	help = "Open a checkpoint, or waveform DB"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, wdb=True, dcp=True)

		c.add_argument("--nogui", action="store_true", help="Do not open in GUI (TCL mode)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.dcp:
			cmd_dcp_open(cfg, dcp_file=args.dcp, nogui=args.nogui)
		elif args.wdb:
			cmd_wdb_open(cfg, sim_name=args.wdb, nogui=args.nogui)


class ReloadCommand(Command):
	name = "reload"
	help = "Reload a live waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, sim=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_wdb_reload(cfg, sim_name=args.target)


class ProcessorCommand(Command):
	name = "processor"
	help = "Control the embedded processor via JTAG"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		c.add_argument("--reset",  action="store_true", help="Soft-reset the processor")
		c.add_argument("--status", action="store_true", help="Print processor state and registers")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_processor(cfg, reset=args.reset, status=args.status)


class ProgramCommand(Command):
	name = "program"
	help = "Download bitstream and/or ELF to FPGA"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, platform=True, app=True)

		c.add_argument("--bitstream", metavar="PATH", help="Explicit path to .bit file")
		c.add_argument("--elf", metavar="PATH", help="Explicit path to .elf file")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_program(cfg,
			bitstream_file=args.bitstream,
			elf_file=args.elf,
			app_name=args.app,
			platform_name=args.platform,
		)


class SearchCommand(Command):
	name = "search"
	help = "Search Vivado's IP catalog by name, VLNV, or keyword"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)

		c = cls.c
		c.add_argument("query", metavar="QUERY", help="IP name, partial VLNV, or keyword")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_search_core(cfg, query=args.query)


class SimulateCommand(Command):
	name = "simulate"
	help = "Run simulation"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, sim=True)

		c.add_argument("--run", metavar="TIME", help="Simulation run time, e.g. 1000ns")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_simulate(cfg, sim_name=args.target, run=args.run)


class SynthCommand(Command):
	name = "synth"
	help = "Synthesise a BD, Design module"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, bd=True, design=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.bd:
			cmd_bd_synth(cfg, bd_name=args.bd)
		elif args.design:
			cmd_design_synth(cfg, design_name=args.design)
