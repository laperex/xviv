import logging
import os
import re

from xviv.config.params import AppBuildParams, AppCreateParams, PlatformCreateParams, ProcessorParams, ProgramParams
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools.xsct import XsctRunner
from xviv.utils import error
from xviv.utils.job import Job, run_job
from xviv.utils.tools import find_vitis_dir_path

logger = logging.getLogger(__name__)


def cmd_platform_create(cfg: XvivConfig, *, platform_name: str, params: PlatformCreateParams):
	cfg.validate_platform(platform_name=platform_name)

	platform_cfg = cfg.get_platform(name=platform_name)

	XsctRunner(cfg).make_pairs(
		[platform_cfg.name], lambda name: ConfigTclCommands(cfg).create_platform(name).build(), label_prefix="create", log_prefix="create_platform"
	).run()

	logger.info(f"Platform: {platform_cfg.name} - Create complete - {platform_cfg.work_dir}")

	if params.build:
		cmd_platform_build(cfg, platform_name=platform_name)


def cmd_platform_build(cfg: XvivConfig, *, platform_name: str):
	platform_cfg = cfg.get_platform(platform_name)
	cfg.validate_platform(platform_name=platform_name)

	if not os.path.isdir(platform_cfg.work_dir):
		raise error.PlatformBspDirectoryMissingError(platform_cfg.name, platform_cfg.work_dir)

	logger.info("Platform Build: %s", platform_cfg.work_dir)

	run_job(
		Job(
			cmd=["make", f"-j{os.cpu_count() or 4}"],
			cwd=platform_cfg.work_dir,
			env=_get_vitis_env(cfg),
			dry_run=cfg.dry_run,
			label="platform_build_make",
			log_file=os.path.join(cfg.log_dir, "platform_build_make.log"),
		), exit_on_fail=False
	)


def cmd_app_create(cfg: XvivConfig, *, app_name: str, platform_name: str | None, template: str | None = None, params: AppCreateParams):
	app_cfg = cfg.get_app(app_name)

	if template:
		app_cfg.template = template

	if platform_name:
		app_cfg.platform = platform_name

	cfg.validate_app(app_name=app_name, check_elf=False)

	platform_cfg = cfg.get_platform(app_cfg.platform)

	if not os.path.isdir(platform_cfg.work_dir):
		logger.warning("BSP not found - creating platform '%s' first", app_cfg.platform)
		cmd_platform_create(cfg, platform_name=app_cfg.platform, params=PlatformCreateParams())
		cmd_platform_build(cfg, platform_name=app_cfg.platform)

	cfg.validate_platform(platform_name=app_cfg.platform)

	XsctRunner(cfg).make_pairs(
		[app_cfg.name], lambda name: ConfigTclCommands(cfg).create_app(name).build(), label_prefix="create", log_prefix="create_app"
	).run()

	logger.info(f"App: {app_cfg.name} - Create complete - {app_cfg.work_dir}")

	if params.build:
		cmd_app_build(cfg, app_name=app_name, params=AppBuildParams(info=True))


def cmd_app_build(cfg: XvivConfig, *, app_name: str, params: AppBuildParams):
	app_cfg = cfg.get_app(app_name)
	platform_cfg = cfg.get_platform(app_cfg.platform)

	cfg.validate_app(app_name=app_name, check_elf=False, check_sources=True)
	cfg.validate_platform(platform_name=platform_cfg.name)

	_transform_app_makefile(os.path.join(app_cfg.work_dir, "Makefile"))

	bsp_include = os.path.join(platform_cfg.work_dir, platform_cfg.cpu, "include")
	bsp_lib = os.path.join(platform_cfg.work_dir, platform_cfg.cpu, "lib")

	logger.info("App Build %s", app_cfg.work_dir)

	run_job(
		Job(
			cmd=[
				"make",
				f"-j{os.cpu_count() or 4}",
				f"INCLUDEPATH=-I{bsp_include} -I{platform_cfg.work_dir}",
				f"c_SOURCES={' '.join([i.file for i in app_cfg.sources])}",
				f"LIBPATH=-L{bsp_lib}",
			],
			cwd=app_cfg.work_dir,
			env=_get_vitis_env(cfg),
			dry_run=cfg.dry_run,
			label="app_build_make",
			log_file=os.path.join(cfg.log_dir, "app_build_make.log"),
		), exit_on_fail=False
	)

	if not cfg.dry_run:
		cfg.validate_app(app_name=app_name, check_elf=True, check_sources=False)

	if params.info and cfg.get_vitis().path:
		mb_tool_size_bin = os.path.join(cfg.get_vitis().path, "gnu", "microblaze", "lin", "bin", "microblaze-xilinx-elf-size")
		mb_tool_objdump_bin = os.path.join(cfg.get_vitis().path, "gnu", "microblaze", "lin", "bin", "microblaze-xilinx-elf-objdump")

		logger.info("ELF Size: %s", app_cfg.elf)

		run_job(
			Job(
				cmd=[mb_tool_size_bin, app_cfg.elf],
				cwd=app_cfg.work_dir,
				dry_run=cfg.dry_run,
				label="app_build_mbtool_size",
				log_file=os.path.join(cfg.log_dir, "app_build_mbtool_size.log"),
			), exit_on_fail=False
		)

		logger.info("ELF sections: %s", app_cfg.elf)

		run_job(
			Job(
				cmd=[mb_tool_objdump_bin, "-h", app_cfg.elf],
				cwd=app_cfg.work_dir,
				dry_run=cfg.dry_run,
				label="app_build_mbtool_size",
				log_file=os.path.join(cfg.log_dir, "app_build_mbtool_size.log"),
			), exit_on_fail=False
		)


def cmd_program(cfg: XvivConfig, *, params: ProgramParams):
	if params.app_name:
		cfg.validate_app(app_name=params.app_name, check_sources=False)

	bitstream_file = params.bitstream_file
	elf_file = params.elf_file
	platform_name = params.platform_name

	if bitstream_file is None:
		if platform_name is None:
			if params.app_name is not None:
				platform_name = cfg.get_app(params.app_name).platform

		if platform_cfg := cfg._get_platform_cfg_optional(platform_name):
			bitstream_file = platform_cfg.bitstream

	if platform_name:
		cfg.validate_platform(platform_name=platform_name)

	if elf_file is None:
		if params.app_name is not None:
			elf_file = cfg.get_app(params.app_name).elf

	if elf_file is None and bitstream_file is None:
		raise error.ProgramUnspecifiedIdentifiersError()

	if bitstream_file:
		logger.info("Bitstream: %s", bitstream_file)
	if elf_file:
		logger.info("ELF: %s", elf_file)

	XsctRunner(cfg).make_pairs(
		[platform_name],
		lambda _: (
			ConfigTclCommands(cfg)
			.program(
				params=ProgramParams(
					bitstream_file=bitstream_file,
					elf_file=elf_file,
					processor_target_filter=params.processor_target_filter,
					processor_reset_duration=params.processor_reset_duration,
					fpga_target_filter=params.fpga_target_filter,
				)
			)
			.build()
		),
		label_prefix="program",
		log_prefix="program",
	).run()


def cmd_processor(cfg: XvivConfig, *, params: ProcessorParams):
	XsctRunner(cfg).make_pairs(
		[__name__],
		lambda _: ConfigTclCommands(cfg).processor_cntrl(params=params).build(),
		label_prefix="processor",
		log_prefix="processor",
	).run()


def cmd_jtagterminal_open(cfg: XvivConfig, params: ProcessorParams):
	XsctRunner(cfg).make_pairs(
		[__name__],
		lambda _: ConfigTclCommands(cfg).open_jtagterminal(params=params).build(),
		label_prefix="jtagterminal",
		log_prefix="jtagterminal",
	).run()


def _transform_app_makefile(path: str):
	content = open(path, "rt").read()

	content = re.sub(r"(patsubst\s+%\.\w+,\s*)(?!build/)%.o", r"\1build/%.o", content)
	content = re.sub(r"(?<!build/)%.o(:%\.[cSs])", r"build/%.o\1", content)
	content = re.sub(r"(build/%.o:%\.[cSs]\n)(?!\t@mkdir)", r"\1\t@mkdir -p $(dir $@)\n", content)

	open(path, "wt").write(content)


def _get_vitis_env(cfg: XvivConfig) -> dict[str, str]:
	vitis_path = cfg.get_vitis().path

	if vitis_path is None:
		find_vitis_dir_path()

	extra_paths = [
		os.path.join(vitis_path, "gnu", "microblaze", "lin", "bin"),
		os.path.join(vitis_path, "bin"),
		os.path.join(vitis_path, "lib", "lnx64.o"),
	]
	env = os.environ.copy()
	env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

	return env
