import glob
import logging
import os
import re
import subprocess
import sys
import typing

from xviv.config.model import ProjectConfig
from xviv.tools import xsct
from xviv.tools.util import find_xsct_script
from xviv.utils.fs import resolve_globs


logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# create --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_create(cfg: ProjectConfig, platform_name: str):
	plat = cfg.get_platform(platform_name)

	xsa, _ = cfg.get_platform_paths(platform_name)
	bsp    = cfg.get_platform_dir(platform_name)

	if not os.path.exists(xsa):
		sys.exit(
			f"ERROR: XSA not found: {xsa}\n"
			f"  Run synthesis for platform '{platform_name}' first."
		)

	logger.info("Creating BSP platform '%s'", platform_name)
	logger.info("  XSA    : %s", xsa)
	logger.info("  CPU    : %s", plat.cpu)
	logger.info("  OS     : %s", plat.os)
	logger.info("  BSP dir: %s", bsp)

	xsct.run_xsct(cfg, find_xsct_script(), ["create_platform", xsa, plat.cpu, plat.os, bsp])


# -----------------------------------------------------------------------------
# create --app <app_name> [--platform <platform_name>] [--template <template>]
# -----------------------------------------------------------------------------
def cmd_app_create(
	cfg: ProjectConfig,
	app_name: str,
	platform_name: typing.Optional[str],
	template_name: typing.Optional[str],
):
	app  = cfg.get_app(app_name)
	plat_name = platform_name or app.platform
	plat = cfg.get_platform(plat_name)

	xsa, _ = cfg.get_platform_paths(plat_name)
	bsp    = cfg.get_platform_dir(plat_name)

	if not os.path.exists(xsa):
		sys.exit(
			f"ERROR: XSA not found: {xsa}\n"
			f"  Run synthesis for platform '{plat_name}' first."
		)

	# Auto-create BSP if absent
	if not os.path.isdir(bsp):
		logger.info("BSP not found - creating platform '%s' first", plat_name)
		cmd_platform_create(cfg, plat_name)

	# get_app_dir exits if dir missing; use build_dir directly so create works
	app_out_dir = os.path.join(cfg.build_dir, "app", app_name)
	template    = template_name or app.template
	src_dir     = app.src_dir

	logger.info("Creating app '%s' from template '%s'", app_name, template)
	logger.info("  App dir : %s", app_out_dir)

	xsct.run_xsct(
		cfg, find_xsct_script(),
		["create_app", xsa, plat.cpu, plat.os, template, app_out_dir],
	)

	if not os.path.isdir(src_dir):
		logger.warning("src_dir not found, creating %s", src_dir)

	os.makedirs(src_dir, exist_ok=True)


# -----------------------------------------------------------------------------
# build --platform <platform_name>
# -----------------------------------------------------------------------------
def cmd_platform_build(cfg: ProjectConfig, platform_name: str):
	bsp = cfg.get_platform_dir(platform_name)

	if not os.path.isdir(bsp):
		sys.exit(
			f"ERROR: BSP directory not found: {bsp}\n"
			f"  Run: xviv create --platform {platform_name}"
		)

	logger.info("Building BSP: %s", bsp)

	subprocess.run(
		["make", f"-j{os.cpu_count() or 4}"],
		check=True,
		cwd=bsp
	)
	logger.info("BSP build complete")


# -----------------------------------------------------------------------------
# build --app <app_name> [--info]
# -----------------------------------------------------------------------------
def cmd_app_build(cfg: ProjectConfig, app_name: str, info: typing.Optional[bool]):
	app      = cfg.get_app(app_name)
	plat     = cfg.get_platform(app.platform)

	bsp         = cfg.get_platform_dir(app.platform)
	app_out_dir = cfg.get_app_dir(app_name)

	_transform_app_makefile(os.path.join(app_out_dir, "Makefile"))

	bsp_include = os.path.join(bsp, plat.cpu, "include")
	bsp_lib     = os.path.join(bsp, plat.cpu, "lib")

	src_dir   = cfg.abs_path(app.src_dir)
	c_sources = " ".join(resolve_globs(["**/*.c"], src_dir))

	logger.info("Building app '%s'", app_name)
	subprocess.run(
		[
			"make", f"-j{os.cpu_count() or 4}",
			f"INCLUDEPATH=-I{src_dir} -I{bsp_include} -I{bsp}",
			f"c_SOURCES={c_sources}",
			f"LIBPATH=-L{bsp_lib}",
		],
		check=True,
		cwd=app_out_dir
	)

	logger.info("App build complete")

	if info:
		elf = _find_elf(cfg, app_name)

		logger.info("ELF: %s", elf)
		print(f"\n=== ELF size: {os.path.basename(elf)} ===")
		subprocess.run([_mb_tool(cfg, "size"), elf])
		print(f"\n=== ELF sections: {os.path.basename(elf)} ===")
		subprocess.run([_mb_tool(cfg, "objdump"), "-h", elf])


# -----------------------------------------------------------------------------
# program [--app | --platform | --elf | --bitstream]
# -----------------------------------------------------------------------------
def cmd_program(
	cfg: ProjectConfig,
	app_name:      typing.Optional[str],
	platform_name: typing.Optional[str],
	elf:           typing.Optional[str],
	bitstream:     typing.Optional[str],
):
	server = cfg.vivado.hw_server

	bitstream_path = ""

	if bitstream:
		bitstream_path = os.path.abspath(bitstream)

	elif platform_name:
		_, bitstream_path = cfg.get_platform_paths(platform_name)

	elif app_name:
		app = cfg.get_app(app_name)
		_, bitstream_path = cfg.get_platform_paths(app.platform)

	if not os.path.exists(bitstream_path):
		sys.exit(f"ERROR: Bitstream not found: {bitstream_path}")

	elf_path = ""

	if elf:
		elf_path = os.path.abspath(elf)
		if not os.path.exists(elf_path):
			sys.exit(f"ERROR: ELF not found: {elf_path}")

	elif app_name:
		elf_path = _find_elf(cfg, app_name)

	logger.info("Programming FPGA")
	logger.info("  Bitstream : %s", bitstream_path)
	if elf_path:
		logger.info("  ELF       : %s", elf_path)
	logger.info("  hw_server : %s", server)

	xsct.run_xsct(cfg, find_xsct_script(), ["program", bitstream_path, elf_path, server])


# -----------------------------------------------------------------------------
# processor --reset | --status
# -----------------------------------------------------------------------------
def cmd_processor(cfg: ProjectConfig, reset: typing.Optional[bool], status: typing.Optional[bool]):
	server = cfg.vivado.hw_server

	if reset:
		logger.info("Resetting embedded processor via JTAG (%s)", server)
		xsct.run_xsct(cfg, find_xsct_script(), ["processor_reset", server])

	elif status:
		xsct.run_xsct(cfg, find_xsct_script(), ["processor_status", server])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_elf(cfg: ProjectConfig, app_name: str) -> str:
    app_out_dir = cfg.get_app_dir(app_name)

    candidates = [
        os.path.join(app_out_dir, "Debug", f"{app_name}.elf"),
        os.path.join(app_out_dir, f"{app_name}.elf"),
    ]

    for c in candidates:
        if os.path.exists(c):
            return c

    hits = sorted(glob.glob(os.path.join(app_out_dir, "**", "*.elf"), recursive=True))

    if not hits:
        sys.exit(f"No ELF found in {app_out_dir}")

    return hits[0]


def _mb_tool(cfg: ProjectConfig, tool: str) -> str:
    return os.path.join(
        cfg.vivado.path, "gnu", "microblaze", "lin", "bin",
        f"microblaze-xilinx-elf-{tool}",
    )


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