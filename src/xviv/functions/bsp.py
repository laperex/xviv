import logging
import os
import re

from xviv.config.project import XvivConfig
from xviv.functions.bd import ConfigTclCommands
from xviv.tools.xsct import run_xsct
from xviv.utils import error
from xviv.utils.process import run_tool
from xviv.utils.tools import find_vitis_dir_path

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_create(cfg: XvivConfig, *, platform_name: str, build: bool = False):
	cfg.validate_platform(platform_name=platform_name)

	config = ConfigTclCommands(cfg).create_platform(platform_name).build()

	run_xsct(cfg, config_tcl=config)
	
	platform_cfg = cfg.get_platform(name=platform_name)

	logger.info(f"Platform: {platform_cfg.name} - Create complete - {platform_cfg.dir}")

	if build:
		cmd_platform_build(cfg, platform_name=platform_name)


# -----------------------------------------------------------------------------
# build --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_build(cfg: XvivConfig, *, platform_name: str):
	platform_cfg = cfg.get_platform(platform_name)
	cfg.validate_platform(platform_name=platform_name)

	if not os.path.isdir(platform_cfg.dir):
		raise error.PlatformBspDirectoryMissingError(platform_cfg.name, platform_cfg.dir)

	logger.info("Platform Build: %s", platform_cfg.dir)

	run_tool(
		["make", f"-j{os.cpu_count() or 4}"],
		cwd=platform_cfg.dir,
		env=_get_vitis_env(cfg),
		dry_run=cfg.dry_run,
		exit_on_fail=True,
	)


# -----------------------------------------------------------------------------
# create --app <app_name> [--platform <platform_name>] [--template <template>]
# -----------------------------------------------------------------------------
def cmd_app_create(
	cfg: XvivConfig, *, app_name: str, platform_name: str | None, template: str | None = None, build: bool = False
):
	app_cfg = cfg.get_app(app_name)

	if template:
		app_cfg.template = template

	if platform_name:
		app_cfg.platform = platform_name

	cfg.validate_app(app_name=app_name, check_elf=False)

	platform_cfg = cfg.get_platform(app_cfg.platform)

	if not os.path.isdir(platform_cfg.dir):
		logger.warning("BSP not found - creating platform '%s' first", app_cfg.platform)
		cmd_platform_create(cfg, platform_name=app_cfg.platform)

	cfg.validate_platform(platform_name=app_cfg.platform)

	config = ConfigTclCommands(cfg).create_app(app_name).build()

	run_xsct(cfg, config_tcl=config)

	logger.info(f"App: {app_cfg.name} - Create complete - {app_cfg.dir}")

	if build:
		cmd_app_build(cfg, app_name=app_name, info=True)


# -----------------------------------------------------------------------------
# build --app <app_name> [--info]
# -----------------------------------------------------------------------------
def cmd_app_build(cfg: XvivConfig, *, app_name: str, info: bool = False):
	app_cfg = cfg.get_app(app_name)
	platform_cfg = cfg.get_platform(app_cfg.platform)

	cfg.validate_app(app_name=app_name, check_elf=False, check_sources=True)
	cfg.validate_platform(platform_name=platform_cfg.name)

	_transform_app_makefile(os.path.join(app_cfg.dir, "Makefile"))

	bsp_include = os.path.join(platform_cfg.dir, platform_cfg.cpu, "include")
	bsp_lib = os.path.join(platform_cfg.dir, platform_cfg.cpu, "lib")

	logger.info("App Build %s", app_cfg.dir)

	run_tool(
		[
			"make",
			f"-j{os.cpu_count() or 4}",
			f"INCLUDEPATH=-I{bsp_include} -I{platform_cfg.dir}",
			f"c_SOURCES={' '.join([i.file for i in app_cfg.sources])}",
			f"LIBPATH=-L{bsp_lib}",
		],
		cwd=app_cfg.dir,
		env=_get_vitis_env(cfg),
		dry_run=cfg.dry_run,
		exit_on_fail=True,
	)

	if not cfg.dry_run:
		cfg.validate_app(app_name=app_name, check_elf=True, check_sources=False)

	if info and cfg.get_vitis().path:
		mb_tool_size_bin = os.path.join(
			cfg.get_vitis().path, "gnu", "microblaze", "lin", "bin", "microblaze-xilinx-elf-size"
		)
		mb_tool_objdump_bin = os.path.join(
			cfg.get_vitis().path, "gnu", "microblaze", "lin", "bin", "microblaze-xilinx-elf-objdump"
		)

		logger.info("ELF Size: %s", app_cfg.elf_file)

		run_tool([mb_tool_size_bin, app_cfg.elf_file], cwd=app_cfg.dir, dry_run=cfg.dry_run, exit_on_fail=True)

		logger.info("ELF sections: %s", app_cfg.elf_file)

		run_tool([mb_tool_objdump_bin, "-h", app_cfg.elf_file], cwd=app_cfg.dir, dry_run=cfg.dry_run, exit_on_fail=True)


# -----------------------------------------------------------------------------
# program [--app | --platform | --elf | --bitstream]
# -----------------------------------------------------------------------------
def cmd_program(
	cfg: XvivConfig,
	*,
	bitstream_file: str | None = None,
	elf_file: str | None = None,
	app_name: str | None = None,
	platform_name: str | None = None,
	processor_target_filter: str | None = None,
	processor_reset_duration: int | None = None,
	fpga_target_filter: str | None = None,
):
	if app_name:
		cfg.validate_app(app_name=app_name, check_sources=False)

	if bitstream_file is None:
		if platform_name is None:
			if app_name is not None:
				platform_name = cfg.get_app(app_name).platform

		if platform_cfg := cfg._get_platform_cfg_optional(platform_name):
			bitstream_file = platform_cfg.bitstream_file

	if platform_name:
		cfg.validate_platform(platform_name=platform_name)

	if elf_file is None:
		if app_name is not None:
			elf_file = cfg.get_app(app_name).elf_file

	if elf_file is None and bitstream_file is None:
		raise error.ProgramUnspecifiedIdentifiersError()

	config = (
		ConfigTclCommands(cfg)
		.program(
			bitstream_file=bitstream_file,
			elf_file=elf_file,
			processor_target_filter=processor_target_filter,
			processor_reset_duration=processor_reset_duration,
			fpga_target_filter=fpga_target_filter,
		)
		.build()
	)

	if bitstream_file:
		logger.info("Bitstream: %s", bitstream_file)
	if elf_file:
		logger.info("ELF: %s", elf_file)

	run_xsct(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# processor --reset | --status
# -----------------------------------------------------------------------------
def cmd_processor(cfg: XvivConfig, *, reset: bool | None, status: bool | None):
	config = ConfigTclCommands(cfg).processor_cntrl(reset=reset, status=status).build()

	run_xsct(cfg, config_tcl=config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
		os.path.join(vitis_path, "gnu", "microblaze", "lin", "bin"),  # mb-gcc
		os.path.join(vitis_path, "bin"),
		os.path.join(vitis_path, "lib", "lnx64.o"),
	]
	env = os.environ.copy()
	env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

	return env
