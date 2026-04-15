import logging
import os
import subprocess
import sys
import typing

from xviv import config, hooks, platform, utils, vitis, vivado, waveform, wrapper
from xviv.config import ProjectConfig, _resolve_globs

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(cfg: ProjectConfig, ip_name: str):
	ip = cfg.get_ip(ip_name)

	if ip.create_wrapper:
		ip_top        = ip.top
		ip_rtl_files  = cfg.resolve_globs(ip.rtl)

		wrapper.xviv_wrap_top(ip_top, cfg.wrapper_dir, ip_rtl_files)

		ip_wrapper_file = os.path.join(cfg.wrapper_dir, f"{ip_top}_wrapper.sv")
		if ip_wrapper_file not in ip_rtl_files:
			ip_rtl_files.append(ip_wrapper_file)

		# Mutate the dataclass so generate_config_tcl picks up the wrapper top/rtl.
		ip.top = f"{ip_top}_wrapper"
		ip.rtl = ip_rtl_files   # absolute paths are glob-safe on POSIX

	config_tcl = config.generate_config_tcl(cfg, ip_name=ip_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_ip", [], config_tcl)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	hooks.generate_bd_hooks(cfg, bd_name, exist_ok=True)
	config_tcl = config.generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_bd", [], config_tcl)


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

	vitis.run_xsct(cfg, vitis._find_xsct_script(), ["create_platform", xsa, plat.cpu, plat.os, bsp])


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

	vitis.run_xsct(
		cfg, vitis._find_xsct_script(),
		["create_app", xsa, plat.cpu, plat.os, template, app_out_dir],
	)

	if not os.path.isdir(src_dir):
		logger.warning("src_dir not found, creating %s", src_dir)

	os.makedirs(src_dir, exist_ok=True)


# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: ProjectConfig, ip_name: str):
	config_tcl = config.generate_config_tcl(cfg, ip_name=ip_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_ip", [], config_tcl)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: ProjectConfig, bd_name: str):
	config_tcl = config.generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# config --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_config(cfg: ProjectConfig, ip_name: str):
	hooks.generate_ip_hooks(cfg, ip_name)


# -----------------------------------------------------------------------------
# config --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_config(cfg: ProjectConfig, bd_name: str):
	hooks.generate_bd_hooks(cfg, bd_name)


# -----------------------------------------------------------------------------
# config --top <top_name>
# -----------------------------------------------------------------------------
def cmd_top_config(cfg: ProjectConfig, top_name: str):
	hooks.generate_top_hooks(cfg, top_name)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: ProjectConfig, bd_name: str):
	config_tcl = config.generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "generate_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# export --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_export(cfg: ProjectConfig, bd_name: str):
	sha, dirty, tag = utils._git_sha_tag()

	bd         = cfg.get_bd(bd_name)
	export_base = cfg.abs_path(bd.export_tcl)
	stem        = os.path.splitext(export_base)[0]
	versioned   = f"{stem}_{tag}.tcl"
	symlink     = export_base

	logger.info("BD export: sha=%s dirty=%s", sha, dirty)
	logger.info("BD export versioned: %s", versioned)
	logger.info("BD export symlink  : %s", symlink)

	if dirty:
		logger.warning(
			"Working tree is dirty - export tagged _dirty. "
			"Commit changes before a production export."
		)

	config_tcl = config.generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "export_bd", [versioned], config_tcl)
	vivado._strip_bd_tcl(versioned)

	utils._atomic_symlink(versioned, symlink)
	logger.info(
		"Symlink updated: %s -> %s",
		os.path.basename(symlink),
		os.path.basename(versioned),
	)

	print(f"Exported : {versioned}")
	print(f"Symlink  : {symlink} -> {os.path.basename(versioned)}")


# -----------------------------------------------------------------------------
# synth --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_synth(cfg: ProjectConfig, ip_name: str):
	pass


# -----------------------------------------------------------------------------
# synth --bd <bd_name> [--ooc-run]
# -----------------------------------------------------------------------------
def cmd_bd_synth(cfg: ProjectConfig, bd_name: str, ooc_run: typing.Optional[bool]):
	_, _, tag = utils._git_sha_tag()

	config_tcl = config.generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(
		cfg, vivado._find_tcl_script(), "synthesis",
		[f"{bd_name}_wrapper", tag],
		config_tcl,
	)


# -----------------------------------------------------------------------------
# synth --top <top_name>
# -----------------------------------------------------------------------------
def cmd_top_synth(cfg: ProjectConfig, top_name: str):
	_, _, tag = utils._git_sha_tag()

	config_tcl = config.generate_config_tcl(cfg, top_name=top_name)

	vivado.run_vivado(
		cfg, vivado._find_tcl_script(), "synthesis",
		[top_name, tag],
		config_tcl,
	)


# -----------------------------------------------------------------------------
# open --dcp <dcp_name> --top <top_name>
# -----------------------------------------------------------------------------
def cmd_dcp_open(cfg: ProjectConfig, dcp_name: str, top_name: str):
	dcp_path   = cfg.get_dcp_path(top_name, dcp_name)
	config_tcl = config.generate_config_tcl(cfg)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "open_dcp", [dcp_path], config_tcl)


# -----------------------------------------------------------------------------
# open --snapshot --top <top_name>
# -----------------------------------------------------------------------------
def cmd_snapshot_open(cfg: ProjectConfig, top_name: str):
	waveform.open_snapshot(cfg, top_name)


# -----------------------------------------------------------------------------
# open --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_open(cfg: ProjectConfig, top_name: str):
	waveform.open_wdb(cfg, top_name)


# -----------------------------------------------------------------------------
# elaborate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_top_elaborate(cfg: ProjectConfig, top_name: str, run: typing.Optional[str]):
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)
	sim_files     = cfg.resolve_globs(cfg.get_simulation(top_name=top_name).rtl)

	xsim_lib  = "xv_work"
	timescale = "1ns/1ps"

	vivado.run_vivado_xvlog(cfg, xlib_work_dir, sim_files, xsim_lib=xsim_lib)
	vivado.run_vivado_xelab(cfg, xlib_work_dir, top_name, timescale=timescale, xsim_lib=xsim_lib)

	if run:
		cmd_top_simulate(cfg, top_name, run)

# -----------------------------------------------------------------------------
# simulate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_top_simulate(cfg: ProjectConfig, top_name: str, run: str = "all"):
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)

	x_simulate_tcl = f"""
		log_wave -recursive *
		run {run}
		exit
	"""

	vivado.run_vivado_xsim(cfg, xlib_work_dir, top_name, x_simulate_tcl)

# -----------------------------------------------------------------------------
# reload --snapshot --top <top_name>
# -----------------------------------------------------------------------------
def cmd_snapshot_reload(cfg: ProjectConfig, top_name: str):
	waveform.reload_snapshot(cfg, top_name)


# -----------------------------------------------------------------------------
# reload --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_reload(cfg: ProjectConfig, top_name: str):
	waveform.reload_wdb(cfg, top_name)


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
		cwd=bsp,
		env=vitis._get_vitis_env(cfg),
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
	env         = vitis._get_vitis_env(cfg)

	platform._transform_app_makefile(os.path.join(app_out_dir, "Makefile"))

	bsp_include = os.path.join(bsp, plat.cpu, "include")
	bsp_lib     = os.path.join(bsp, plat.cpu, "lib")

	src_dir   = cfg.abs_path(app.src_dir)
	c_sources = " ".join(_resolve_globs(["**/*.c"], src_dir))

	logger.info("Building app '%s'", app_name)
	subprocess.run(
		[
			"make", f"-j{os.cpu_count() or 4}",
			f"INCLUDEPATH=-I{src_dir} -I{bsp_include} -I{bsp}",
			f"c_SOURCES={c_sources}",
			f"LIBPATH=-L{bsp_lib}",
		],
		check=True,
		cwd=app_out_dir,
		env=env,
	)

	logger.info("App build complete")

	if info:
		elf = platform._find_elf(cfg, app_name)

		logger.info("ELF: %s", elf)
		print(f"\n=== ELF size: {os.path.basename(elf)} ===")
		subprocess.run([platform._mb_tool(cfg, "size"), elf])
		print(f"\n=== ELF sections: {os.path.basename(elf)} ===")
		subprocess.run([platform._mb_tool(cfg, "objdump"), "-h", elf])


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
		elf_path = platform._find_elf(cfg, app_name)

	logger.info("Programming FPGA")
	logger.info("  Bitstream : %s", bitstream_path)
	if elf_path:
		logger.info("  ELF       : %s", elf_path)
	logger.info("  hw_server : %s", server)

	vitis.run_xsct(cfg, vitis._find_xsct_script(), ["program", bitstream_path, elf_path, server])


# -----------------------------------------------------------------------------
# processor --reset | --status
# -----------------------------------------------------------------------------
def cmd_processor(cfg: ProjectConfig, reset: typing.Optional[bool], status: typing.Optional[bool]):
	server = cfg.vivado.hw_server

	if reset:
		logger.info("Resetting embedded processor via JTAG (%s)", server)
		vitis.run_xsct(cfg, vitis._find_xsct_script(), ["processor_reset", server])

	elif status:
		vitis.run_xsct(cfg, vitis._find_xsct_script(), ["processor_status", server])