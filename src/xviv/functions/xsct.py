import logging
import os
import re
import subprocess

from xviv.config.project import XvivConfig
from xviv.functions.bd import ConfigTclCommands
from xviv.tools.vitis import run_xsct
from xviv.utils.tools import mb_tool, get_vitis_env


logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# create --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_create(cfg: XvivConfig, *,
	platform_name: str
):
	config = (
		ConfigTclCommands(cfg)
		.create_platform(platform_name)
		.build()
	)

	run_xsct(cfg, config_tcl=config)

# -----------------------------------------------------------------------------
# build --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_build(cfg: XvivConfig, platform_name: str):
	platform_cfg = cfg.get_platform(platform_name)

	if not os.path.isdir(platform_cfg.dir):
		#! BspDirectoryNotFound
		raise RuntimeError(
			f"ERROR: BSP directory not found: {platform_cfg.dir}\n"
			f"  Run: xviv create --platform {platform_name}"
		)

	logger.info("Building BSP: %s", platform_cfg.dir)

	subprocess.run(
		["make", f"-j{os.cpu_count() or 4}"],
		check=True,
		cwd=platform_cfg.dir,
		env=get_vitis_env()
	)

	logger.info("BSP build complete")

# -----------------------------------------------------------------------------
# create --app <app_name> [--platform <platform_name>] [--template <template>]
# -----------------------------------------------------------------------------
def cmd_app_create(cfg: XvivConfig, *,
	app_name: str,
	platform_name: str | None,
	template: str | None = None,
):
	app_cfg = cfg.get_app(app_name)

	if template:
		app_cfg.template = template
	
	if platform_name:
		app_cfg.platform = platform_name

	platform_cfg = cfg.get_platform(app_cfg.platform)

	if not os.path.isdir(platform_cfg.dir):
		logger.info("BSP not found - creating platform '%s' first", app_cfg.platform)
		cmd_platform_create(cfg, app_cfg.platform)

	config = (
		ConfigTclCommands(cfg)
		.create_app(app_name)
		.build()
	)

	run_xsct(cfg, config_tcl=config)

	logger.info(f"App: {app_cfg.name} - Create complete - {app_cfg.dir}")


# -----------------------------------------------------------------------------
# build --app <app_name> [--info]
# -----------------------------------------------------------------------------
def cmd_app_build(cfg: XvivConfig, app_name: str, info: bool | None):
	app_cfg = cfg.get_app(app_name)
	platform_cfg = cfg.get_platform(app_cfg.platform)

	_transform_app_makefile(os.path.join(app_cfg.dir, "Makefile"))

	bsp_include = os.path.join(platform_cfg.dir, platform_cfg.cpu, "include")
	bsp_lib = os.path.join(platform_cfg.dir, platform_cfg.cpu, "lib")

	subprocess.run(
		[
			"make", f"-j{os.cpu_count() or 4}",
			f"INCLUDEPATH=-I{bsp_include} -I{platform_cfg.dir}",
			f"c_SOURCES={' '.join(app_cfg.sources)}",
			f"LIBPATH=-L{bsp_lib}",
		],
		check=True,
		cwd=app_cfg.dir,
		env=get_vitis_env(),
	)

	logger.info("App build complete")

	if not os.path.exists(app_cfg.elf_file):
		#! ElfNotCreated
		raise RuntimeError(f'ERROR: elf file not created for app: {app_name} at {app_cfg.elf_file} in {app_cfg.dir}')

	if info:
		logger.info("ELF: %s", app_cfg.elf_file)
		print(f"\n=== ELF size: {os.path.basename(app_cfg.elf_file)} ===")
		subprocess.run([mb_tool("size"), app_cfg.elf_file])
		print(f"\n=== ELF sections: {os.path.basename(app_cfg.elf_file)} ===")
		subprocess.run([mb_tool("objdump"), "-h", app_cfg.elf_file])


# -----------------------------------------------------------------------------
# program [--app | --platform | --elf | --bitstream]
# -----------------------------------------------------------------------------
def cmd_program(cfg: XvivConfig, *,
	bitstream_file: str | None = None,
	elf_file: str | None = None,
	app_name: str | None = None,
	platform_name: str | None = None
):
	if bitstream_file is None:
		if platform_name is None:
			if app_name is not None:
				platform_name = cfg.get_app(app_name).platform

		bitstream_file = cfg.get_platform(platform_name).bitstream_file

	if elf_file is None:
		if app_name is not None:
			elf_file = cfg.get_app(app_name).elf_file

	config = (
		ConfigTclCommands(cfg)
		.program(bitstream_file=bitstream_file, elf_file=elf_file)
		.build()
	)

	logger.info("Bitstream : %s", bitstream_file)
	if elf_file:
		logger.info("ELF : %s", elf_file)

	run_xsct(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# processor --reset | --status
# -----------------------------------------------------------------------------
def cmd_processor(cfg: XvivConfig, *,
	reset: bool | None,
	status: bool | None
):
	config = (
		ConfigTclCommands(cfg)
		.processor_cntrl(reset=reset, status=status)
		.build()
	)

	run_xsct(cfg, config_tcl=config)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _transform_app_makefile(path: str):
    content = open(path, "rt").read()

    content = re.sub(
        r'(patsubst\s+%\.\w+,\s*)(?!build/)%.o',
        r'\1build/%.o',
        content
    )

    content = re.sub(
        r'(?<!build/)%.o(:%\.[cSs])',
        r'build/%.o\1',
        content
    )

    content = re.sub(
        r'(build/%.o:%\.[cSs]\n)(?!\t@mkdir)',
        r'\1\t@mkdir -p $(dir $@)\n',
        content
    )

    open(path, 'wt').write(content)