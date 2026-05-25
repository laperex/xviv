import argparse
import typing
from abc import ABC, abstractmethod

from xviv.cli.completers import target_group
from xviv.config.project import XvivConfig
from xviv.functions.bd import cmd_bd_create, cmd_bd_edit, cmd_bd_generate
from xviv.functions.bsp import (
	cmd_app_build,
	cmd_app_create,
	cmd_platform_build,
	cmd_platform_create,
	cmd_processor,
	cmd_program,
)
from xviv.functions.core import cmd_core_create, cmd_core_edit, cmd_core_generate, cmd_search_core
from xviv.functions.formal import cmd_formal
from xviv.functions.ip import cmd_ip_create, cmd_ip_edit
from xviv.functions.simulation import cmd_simulate, cmd_wdb_open, cmd_wdb_reload
from xviv.functions.synthesis import cmd_dcp_open, cmd_synth
from xviv.utils import error


class Command(ABC):
	name: str
	help: str
	c: typing.Any

	_command_class_registry: typing.ClassVar[list[type[typing.Self]]] = []

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		Command._command_class_registry.append(cls)

	@classmethod
	@abstractmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		cls.c = sub.add_parser(cls.name, help=cls.help)
		cls.c.add_argument("--dry-run", action="store_true", help="Print TCL without executing")
		cls.c.add_argument("--check", action="store_true", help="Check TCL generated outputs")

	@abstractmethod
	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		cfg.dry_run = args.dry_run
		cfg.check = args.check


def register_commands(sub) -> dict[str, Command]:
	registry: dict[str, Command] = {}

	for cls in Command._command_class_registry:
		cls.register(sub)
		registry[cls.name] = cls()

	return registry


class CreateCommand(Command):
	name = "create"
	help = "Create an IP, BD, core, platform, or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, ip=True, bd=True, app=True, platform=True, core=True)

		c.add_argument("--source-file", metavar="FILE", help="Source File [BD]", default=True, required=False)
		c.add_argument(
			"--regenerate", action="store_true", help="Regenerate Instances [IP]", default=False, required=False
		)

		target_group(c, exclusive=True, required=False, generate=True, build=True, edit=True)
		target_group(c, exclusive=False, required=False, nogui=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.ip:
			cmd_ip_create(cfg, ip_name=args.ip, edit=args.edit, nogui=args.nogui, regenerate=args.regenerate)
		elif args.bd:
			cmd_bd_create(
				cfg,
				bd_name=args.bd,
				source_file=args.source_file,
				generate=args.generate,
				edit=args.edit,
				nogui=args.nogui,
			)
		elif args.core:
			cmd_core_create(cfg, core_name=args.core, generate=args.generate, edit=args.edit, nogui=args.nogui)
		elif args.app:
			cmd_app_create(cfg, app_name=args.app, platform_name=args.platform, build=args.build)
		elif args.platform:
			cmd_platform_create(cfg, platform_name=args.platform, build=args.build)


class EditCommand(Command):
	name = "edit"
	help = "Open an IP, BD, or core in Vivado for editing"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, ip=True, bd=True, core=True)

		target_group(c, exclusive=False, required=False, nogui=True)

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
	help = "Generate output products for a BD or core"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, bd=True, core=True)
		target_group(c, exclusive=True, required=False, force=True)
		c.add_argument(
			"--reset",
			action="store_true",
			help="Reset all output products before generate",
			default=False,
			required=False,
		)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.bd:
			cmd_bd_generate(cfg, bd_name=args.bd, force=args.force, reset=args.reset)
		elif args.core:
			cmd_core_generate(cfg, core_name=args.core, force=args.force, reset=args.reset)


class OpenCommand(Command):
	name = "open"
	help = "Open a DCP checkpoint or WDB waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, wdb=True, dcp=True)

		target_group(c, exclusive=True, required=False, bd=True, design=True, core=True)

		target_group(c, exclusive=False, required=False, nogui=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.dcp:
			cmd_dcp_open(cfg, dcp_file=args.dcp, nogui=args.nogui)
		elif args.wdb:
			cmd_wdb_open(cfg, sim_name=args.wdb, nogui=args.nogui)


class ReloadCommand(Command):
	name = "reload"
	help = "Reload a live WDB waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, sim_target=True)

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

		c.add_argument("--reset", action="store_true", help="Soft-reset the processor")
		c.add_argument("--status", action="store_true", help="Print processor state and registers")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_processor(cfg, reset=args.reset, status=args.status)


class BuildCommand(Command):
	name = "build"
	help = "Compile a platform or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, app=True, platform=True)

		c.add_argument("--info", action="store_true", help="Print ELF section sizes after build")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.platform:
			cmd_platform_build(cfg, platform_name=args.platform)
		elif args.app:
			cmd_app_build(cfg, app_name=args.app, info=args.info)


class ProgramCommand(Command):
	name = "program"
	help = "Download bitstream and/or ELF to FPGA"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=False, platform=True, bitstream=True)
		target_group(c, exclusive=True, required=False, app=True, elf=True)

		c.add_argument(
			"--fpga",
			metavar="NAME",
			help="Filter to select FPGA (default: %(default)s)",
			default="xc7a*",
			required=False,
		)
		c.add_argument(
			"--processor",
			metavar="NAME",
			help="Filter to select soft processor (default: %(default)s)",
			default="Microblaze #0*",
			required=False,
		)
		c.add_argument(
			"--reset-duration",
			metavar="MS",
			type=int,
			help="Soft-reset duration in ms (default: %(default)s)",
			default=500,
			required=False,
		)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		try:
			cmd_program(
				cfg,
				bitstream_file=args.bitstream,
				elf_file=args.elf,
				app_name=args.app,
				platform_name=args.platform,
				processor_target_filter=args.processor,
				processor_reset_duration=args.reset_duration,
				fpga_target_filter=args.fpga,
			)
		except error.ProgramUnspecifiedIdentifiersError as e:
			self.c.print_help()
			self.c.exit(2, f"\n{e}\n")


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

		target_group(c, exclusive=True, required=True, sim_target=True)
		target_group(c, exclusive=True, required=False, uvm_test=True)
		c.add_argument(
			"--mode",
			metavar="MODE",
			choices=[
				"post_synth_functional",
				"post_synth_timing",
				"post_impl_functional",
				"post_impl_timing",
				"default",
			],
			default="default",
			help="simulation mode (default: %(default)s)",
			required=False,
		)

		c.add_argument(
			"--run", metavar="TIME", help="Simulation run time (default: %(default)s)", default="all", required=False
		)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_simulate(cfg, sim_name=args.target, uvm_name=args.uvm, run=args.run, mode=args.mode)


class SynthCommand(Command):
	name = "synth"
	help = "Synthesize a BD, core, or design"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, bd=True, design=True, core=True)

		c.add_argument(
			"--usr-access-type",
			metavar="",
			help="Type of value to embed in bitstream (default: %(default)s)",
			default="git",
			required=False,
		)
		c.add_argument(
			"--resume",
			metavar="STAGE",
			choices=["auto", "synth", "place", "route"],
			default=None,
			help="resume synthesis from an existing checkpoint ('auto' detects latest)",
			required=False,
		)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_synth(
			cfg,
			design_name=args.design,
			bd_name=args.bd,
			core_name=args.core,
			usr_access_type=args.usr_access_type,
			resume=args.resume,
		)


class FormalCommand(Command):
	name = "formal"
	help = "Run SymbiYosys formal verification targets"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		target_group(c, exclusive=True, required=True, formal_target=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run()

		cmd_formal(cfg, target=args.target)
