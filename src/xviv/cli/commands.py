import argparse
import typing
from abc import ABC, abstractmethod

from xviv.cli.completers import arg, c_app, c_bd, c_core, c_design, c_formal_target, c_ip, c_platform, c_sim_target, target_group
from xviv.config.params import (
	AppBuildParams,
	AppCreateParams,
	BdCreateParams,
	CoreCreateParams,
	EditParams,
	GenerateParams,
	IpCreateParams,
	OpenParams,
	PlatformCreateParams,
	ProcessorParams,
	ProgramParams,
	SimulateParams,
	SynthParams,
	ValidateParams,
)
from xviv.config.project import XvivConfig

# from xviv.functions.bd import cmd_bd_create, cmd_bd_edit, cmd_bd_generate
# from xviv.functions.bsp import (
# 	cmd_app_build,
# 	cmd_app_create,
# 	cmd_platform_build,
# 	cmd_platform_create,
# 	cmd_processor,
# 	cmd_program,
# )
from xviv.functions.bd import cmd_bd_create, cmd_bd_edit, cmd_bd_generate
from xviv.functions.bsp import (
	cmd_app_build,
	cmd_app_create,
	cmd_jtagterminal_open,
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
from xviv.functions.validate import cmd_validate_synth
from xviv.utils import error

# from xviv.functions.formal import cmd_formal
# from xviv.functions.ip import cmd_ip_create, cmd_ip_edit
# from xviv.functions.simulation import cmd_simulate, cmd_wdb_open, cmd_wdb_reload
# from xviv.functions.synthesis import cmd_dcp_open, cmd_synth

# ---------------------------------------------------------------------------
# Command Base & Registry
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


class CreateCommand(Command):
	name = "create"
	help = "Create an IP, BD, core, platform, or app"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=True, ip=True, bd=True, app=True, platform=True, core=True, _all=["ip", "bd", "core"])
		c.add_argument("--source-file", metavar="FILE", help="Source File [BD]", default=True, required=False)
		c.add_argument("--regenerate", action="store_true", help="Regenerate Cores [IP]", default=False, required=False)
		target_group(c, exclusive=True, required=False, generate=True, build=True, edit=True)
		target_group(c, exclusive=False, required=False, nogui=True, recursive=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		if args.ip or args.all == "ip":
			cmd_ip_create(
				cfg,
				ip_name=args.ip or "*",
				params=IpCreateParams(
					edit=args.edit,
					nogui=args.nogui,
					recursive=args.recursive,
					regenerate=args.regenerate,
				),
			)
		elif args.bd or args.all == "bd":
			cmd_bd_create(
				cfg,
				bd_name=args.bd or "*",
				params=BdCreateParams(
					source_file=args.source_file,
					generate=args.generate,
					edit=args.edit,
					nogui=args.nogui,
					recursive=args.recursive,
				),
			)
		elif args.core or args.all == "core":
			cmd_core_create(
				cfg,
				core_name=args.core or "*",
				params=CoreCreateParams(
					generate=args.generate,
					edit=args.edit,
					nogui=args.nogui,
					recursive=args.recursive,
				),
			)
		elif args.app:
			cmd_app_create(
				cfg,
				app_name=args.app,
				platform_name=args.platform,
				params=AppCreateParams(
					build=args.build,
				),
			)
		elif args.platform:
			cmd_platform_create(
				cfg,
				platform_name=args.platform,
				params=PlatformCreateParams(
					build=args.build,
				),
			)


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
		params = EditParams(nogui=args.nogui)

		if args.ip:
			cmd_ip_edit(cfg, ip_name=args.ip, params=params)
		elif args.bd:
			cmd_bd_edit(cfg, bd_name=args.bd, params=params)
		elif args.core:
			cmd_core_edit(cfg, core_name=args.core, params=params)


class GenerateCommand(Command):
	name = "generate"
	help = "Generate output products for a BD or core"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=True, bd=True, core=True, _all=["bd", "core"])
		target_group(c, exclusive=False, required=False, force=True)
		c.add_argument("--reset", action="store_true", help="Reset all output products before generate", default=False, required=False)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		params = GenerateParams(force=args.force, reset=args.reset)

		if args.bd or args.all == "bd":
			cmd_bd_generate(cfg, bd_name=args.bd or "*", params=params)
		elif args.core or args.all == "core":
			cmd_core_generate(cfg, core_name=args.core or "*", params=params)


class OpenCommand(Command):
	name = "open"
	help = "Open a DCP checkpoint or WDB waveform"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=True, wdb=True, dcp=True, jtagterminal=True)
		target_group(c, exclusive=True, required=False, bd=True, design=True, core=True)
		target_group(c, exclusive=False, required=False, nogui=True)
		target_group(c, exclusive=False, required=False, fpga_filter=True, processor_filter=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		params = OpenParams(nogui=args.nogui)

		if args.dcp:
			cmd_dcp_open(cfg, dcp_file=args.dcp, params=params)
		elif args.wdb:
			cmd_wdb_open(cfg, sim_name=args.wdb, params=params)
		elif args.jtagterminal:
			cmd_jtagterminal_open(cfg, params=ProcessorParams(processor_target_filter=args.processor))


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
		target_group(c, exclusive=False, required=False, processor_filter=True)
		c.add_argument("--reset", action="store_true", help="Soft-reset the processor")
		c.add_argument("--status", action="store_true", help="Print processor state and registers")

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		cmd_processor(cfg, params=ProcessorParams(reset=args.reset, status=args.status, processor_target_filter=args.processor))


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
			cmd_app_build(cfg, app_name=args.app, params=AppBuildParams(info=args.info))


class ProgramCommand(Command):
	name = "program"
	help = "Download bitstream and/or ELF to FPGA"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=False, platform=True, bitstream=True)
		target_group(c, exclusive=True, required=False, app=True, elf=True)
		target_group(c, exclusive=False, required=False, fpga_filter=True, processor_filter=True, write_to_file=True)

		c.add_argument(
			"--reset-duration", metavar="MS", type=int, help="Soft-reset duration in ms (default: %(default)s)", default=500, required=False
		)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		params = ProgramParams(
			bitstream_file=args.bitstream,
			elf_file=args.elf,
			app_name=args.app,
			platform_name=args.platform,
			processor_target_filter=args.processor,
			processor_reset_duration=args.reset_duration,
			fpga_target_filter=args.fpga,
			write_to_file=args.write_to_file,
		)
		try:
			cmd_program(cfg, params=params)
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
			choices=["post_synth_functional", "post_synth_timing", "post_impl_functional", "post_impl_timing", "default"],
			default="default",
			help="simulation mode (default: %(default)s)",
			required=False,
		)
		c.add_argument("--run", metavar="TIME", help="Simulation run time (default: %(default)s)", default="all", required=False)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_simulate(
			cfg,
			sim_name=args.target,
			params=SimulateParams(
				uvm_name=args.uvm,
				run=args.run,
				mode=args.mode,
			),
		)


class SynthCommand(Command):
	name = "synth"
	help = "Synthesize a BD, core, or design"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=True, bd=True, design=True, core=True)
		c.add_argument(
			"--resume",
			metavar="STAGE",
			choices=["auto", "synth", "place", "route"],
			default=None,
			help="resume synthesis from an existing checkpoint ('auto' detects latest)",
			required=False,
		)
		c.add_argument("--parallel", action="store_true", help="Parallel synthesis of sub cores", default=False, required=False)
		c.add_argument("--rebuild", action="store_true", help="Override disable incremental synth", default=False, required=False)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_synth(
			cfg,
			design_name=args.design,
			bd_name=args.bd,
			core_name=args.core,
			params=SynthParams(
				resume=args.resume,
				parallel_subcore_synth=args.parallel,
			),
		)


class FormalCommand(Command):
	name = "formal"
	help = "Run SymbiYosys formal verification targets"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c
		target_group(c, exclusive=True, required=False, formal_target=True)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)
		cmd_formal(cfg, target=args.target)


class ValidateCommand(Command):
	name = "validate"
	help = "Validate XDC constraints against RTL port declarations"

	@classmethod
	def register(cls, sub: argparse._SubParsersAction) -> None:
		super().register(sub)
		c = cls.c

		sub2 = c.add_subparsers(dest="validate_sub", metavar="SUBCOMMAND")
		synth_p = sub2.add_parser("synth", help="Validate a synth target's I/O constraints")

		target_group(synth_p, exclusive=True, required=True, bd=True, design=True, core=True)

		synth_p.add_argument("--io", metavar="INFO", choices=["short", "full"], help="Run I/O constraint check", default=None, required=False)
		synth_p.add_argument("--level", metavar="LEVEL", choices=["error", "info"], help="o/p integrity", default="info", required=False)

	def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
		super().run(cfg, args)

		params = ValidateParams(
			design=getattr(args, "design", None),
			bd=getattr(args, "bd", None),
			core=getattr(args, "core", None),
			io=args.io,
			level=args.level,
		)

		match args.validate_sub:
			case "synth":
				cmd_validate_synth(cfg, params)

			case _:
				self.c.print_help()
				self.c.exit(2, "\nSpecify a sub-command, e.g.:  xviv validate synth --design NAME\n")

class CleanCommand(Command):
    name = "clean"
    help = "Clean build directories and tool artifacts"

    @classmethod
    def register(cls, sub: argparse._SubParsersAction) -> None:
        c = sub.add_parser(cls.name, help=cls.help)

        c.add_argument("-n", "--dry-run", action="store_true", help="Print what would be deleted without deleting")
        c.add_argument("-f", "--force", action="store_true", help="Bypass prompts (handled automatically via safe rm)")

        grp = c.add_mutually_exclusive_group(required=False)
        arg(grp, "--bd", metavar="NAME|all", help="Clean Block Design artifacts", completer=c_bd)
        arg(grp, "--core", metavar="NAME|all", help="Clean Core artifacts", completer=c_core)
        arg(grp, "--ip", metavar="NAME|all", help="Clean IP artifacts", completer=c_ip)
        arg(grp, "--app", metavar="NAME|all", help="Clean App artifacts", completer=c_app)
        arg(grp, "--platform", metavar="NAME|all", help="Clean Platform artifacts", completer=c_platform)

        sub_clean = c.add_subparsers(dest="clean_cmd", metavar="[all|logs|cache|synth|impl|sim|formal]")
        
        sub_clean.add_parser("all", help="Wipe the entire work directory completely")
        sub_clean.add_parser("logs", help="Clean tool logs (*.log, *.jou, *.pb)")
        sub_clean.add_parser("cache", help="Clean Vivado cache directories (.Xil)")
        
        p_synth = sub_clean.add_parser("synth", help="Clean synthesis artifacts")
        grp_s = p_synth.add_mutually_exclusive_group(required=True)
        arg(grp_s, "--design", metavar="NAME", completer=c_design)
        arg(grp_s, "--bd", metavar="NAME", completer=c_bd)
        arg(grp_s, "--core", metavar="NAME", completer=c_core)
        
        p_impl = sub_clean.add_parser("impl", help="Clean implementation artifacts")
        grp_i = p_impl.add_mutually_exclusive_group(required=True)
        arg(grp_i, "--design", metavar="NAME", completer=c_design)

        p_sim = sub_clean.add_parser("sim", help="Clean simulation waveforms and databases")
        arg(p_sim, "--sim", metavar="NAME", required=True, completer=c_sim_target)
        
        p_form = sub_clean.add_parser("formal", help="Clean formal verification traces")
        arg(p_form, "--target", metavar="NAME", required=True, completer=c_formal_target)

        cls.c = c

    def run(self, cfg: XvivConfig, args: argparse.Namespace) -> None:
        from xviv.functions.clean import execute_clean
        execute_clean(cfg, args)
