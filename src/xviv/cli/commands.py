import argparse
from abc import ABC, abstractmethod
import sys
from typing import Any

from xviv.cli.completers import arg, dcp_stems_completer, target_group, c_ip, c_bd, c_app, c_platform, c_core, c_top_all, c_top_synth, c_top_sim, c_core_instance
from xviv.config.project import XvivConfig
from xviv.functions.all import cmd_all_create, cmd_bd_create, cmd_ip_create
from xviv.functions.bd import cmd_bd_config, cmd_bd_edit, cmd_bd_generate, cmd_bd_synth
from xviv.functions.core import cmd_core_create, cmd_core_edit, cmd_search_core
from xviv.functions.ip import cmd_ip_config, cmd_ip_edit, cmd_ip_synth
from xviv.functions.simulation import cmd_top_elaborate, cmd_top_simulate, cmd_wdb_open, cmd_wdb_reload
from xviv.functions.synthesis import cmd_dcp_open, cmd_synth_config, cmd_top_synth
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


class BuildCommand(Command):
	name = "build"
	help = "Compile a BSP platform or application"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		mg = c.add_mutually_exclusive_group(required=True)
		arg(mg, "--platform", metavar="NAME", help="Platform name", completer=c_platform)
		arg(mg, "--app",      metavar="NAME", help="App name",      completer=c_app)
		c.add_argument("--info", action="store_true",
			help="Print ELF section sizes after build (used with --app)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.platform:
			cmd_platform_build(cfg, args.platform)
		elif args.app:
			cmd_app_build(cfg, args.app, args.info)


class ConfigCommand(Command):
	name = "config"
	help = "Generate starter hooks for an IP, BD, or top"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, ip=True, bd=True, top=c_top_synth)
		c.add_argument("--synth", action="store_true",
			help="Generate synthesis hooks (required when using --top)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.synth:
			cmd_synth_config(cfg, top_name=args.top, bd_name=args.bd, ip_name=args.ip)
		elif args.ip:
			cmd_ip_config(cfg, args.ip)
		elif args.bd:
			cmd_bd_config(cfg, args.bd)
		elif args.top:
			sys.exit("ERROR: --top <name> cannot be specified without --synth")


class CreateCommand(Command):
	name = "create"
	help = "Create an IP, BD, platform, or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
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
		c.add_argument("--all", action="store_true", help="Create all targets specified in project.toml")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.all:
			cmd_all_create(cfg)
		elif args.ip:
			cmd_ip_create(cfg, args.ip)
		elif args.bd:
			cmd_bd_create(cfg, args.bd)
		elif args.core is not None:
			cmd_core_create(cfg, args.core or "", args.vlnv, args.edit)
		elif args.app:
			cmd_app_create(cfg, args.app, args.platform, args.template)
		elif args.platform:
			cmd_platform_create(cfg, args.platform)
		else:
			sys.exit("ERROR: one of --ip / --bd / --app / --platform / --core is required")


class EditCommand(Command):
	name = "edit"
	help = "Open an IP, BD, or core in Vivado for editing"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		mg = target_group(c, ip=True, bd=True)
		arg(mg, "--core", metavar="NAME", help="Core name", completer=c_core)
		c.add_argument("--nogui", action="store_true", help="Do not open in GUI (TCL mode)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.ip:
			cmd_ip_edit(cfg, args.ip, nogui=args.nogui)
		elif args.bd:
			cmd_bd_edit(cfg, args.bd, nogui=args.nogui)
		elif args.core:
			cmd_core_edit(cfg, args.core, nogui=args.nogui)


class ElaborateCommand(Command):
	name = "elaborate"
	help = "Compile and optionally run simulation"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		arg(c, "--top", required=True, metavar="NAME",
			help="Simulation top module", completer=c_top_sim)
		c.add_argument("--run", metavar="TIME", default="",
			help="Simulation run time, e.g. 1000ns")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_top_elaborate(cfg, args.top, args.run)


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
		mode = c.add_mutually_exclusive_group(required=True)
		arg(mode, "--dcp", metavar="STEM",
			help="Checkpoint stem (e.g. post_synth)",
			completer=dcp_stems_completer)
		mode.add_argument("--wdb", action="store_true",
			help="Open waveform DB in xsim GUI")
		target_group(c, ip=True, bd=True, top=c_top_all)
		c.add_argument("--nogui", action="store_true", help="Do not open in GUI (TCL mode)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.dcp:
			cmd_dcp_open(cfg, args.dcp, top_name=args.top, bd_name=args.bd, nogui=args.nogui)
		elif args.wdb:
			cmd_wdb_open(cfg, args.top, nogui=args.nogui)


class ProcessorCommand(Command):
	name = "processor"
	help = "Control the embedded processor via JTAG"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		mg = c.add_mutually_exclusive_group(required=True)
		mg.add_argument("--reset",  action="store_true", help="Soft-reset the processor")
		mg.add_argument("--status", action="store_true", help="Print processor state and registers")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_processor(cfg, args.reset, args.status)


class ProgramCommand(Command):
	name = "program"
	help = "Download bitstream and/or ELF to FPGA"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		bit = c.add_mutually_exclusive_group()
		arg(bit, "--platform", metavar="NAME",
			help="Derive bitstream from [[platform]] entry", completer=c_platform)
		bit.add_argument("--bitstream", metavar="PATH", help="Explicit path to .bit file")
		elf = c.add_mutually_exclusive_group()
		arg(elf, "--app", metavar="NAME",
			help="Derive ELF from [[app]] build dir", completer=c_app)
		elf.add_argument("--elf", metavar="PATH", help="Explicit path to .elf file")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_program(cfg, args.app, args.platform, args.elf, args.bitstream)


class ReloadCommand(Command):
	name = "reload"
	help = "Reload a live waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		arg(c, "--top", required=True, metavar="NAME", help="Simulation top module", completer=c_top_synth)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_wdb_reload(cfg, args.top)


class SearchCommand(Command):
	name = "search"
	help = "Search Vivado's IP catalog by name, VLNV, or keyword"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		arg(c, "query", metavar="QUERY", help="IP name, partial VLNV, or keyword")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_search_core(cfg, args.query)


class SimulateCommand(Command):
	name = "simulate"
	help = "Run simulation"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		arg(c, "--top", required=True, metavar="NAME",
			help="Simulation top module", completer=c_top_sim)
		c.add_argument("--run", metavar="TIME", default="",
			help="Simulation run time, e.g. 1000ns")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_top_simulate(cfg, args.top, args.run)


class SynthCommand(Command):
	name = "synth"
	help = "Synthesise an IP, BD, or top module"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, ip=True, bd=True, top=c_top_synth)
		c.add_argument("--ooc-run", action="store_true", dest="ooc_run",
			help="Run out-of-context synthesis for leaf IPs (BD only)")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		if args.ip:
			cmd_ip_synth(cfg, args.ip)
		elif args.bd:
			cmd_bd_synth(cfg, args.bd, args.ooc_run)
		elif args.top:
			cmd_top_synth(cfg, args.top)