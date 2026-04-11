

import logging
import os
import subprocess
import sys
import typing

from xviv import config, hooks, platform, utils, vitis, vivado, waveform, wrapper

logger = logging.getLogger(__name__)


#--------------------------------------------------------------------------------------------------------------
#- create --ip <ip_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_ip_create(cfg: dict, project_dir: str, ip_name: str):
	build_cfg = cfg.get("build", {})
	ip_wrapper_dir = os.path.abspath(os.path.join(project_dir, build_cfg.get("wrapper_dir", config.DEFAULT_BUILD_WRAPPER_DIR)))

	ip_list = cfg.get("ip", [])
	ip_cfg = next((i for i in ip_list if i["name"] == ip_name), None)
	if ip_cfg is None:
		sys.exit(f"ERROR: IP '{ip_name}' not found in project.toml [[ip]] entries")

	if ip_cfg.get('create-wrapper', False):
		ip_rtl_files = config._resolve_globs(ip_cfg.get("rtl", []), project_dir)
		ip_top = ip_cfg.get("top", ip_cfg["name"])

		wrapper.xviv_wrap_top(ip_top, ip_wrapper_dir, ip_rtl_files)

		ip_wrapper_file = os.path.join(ip_wrapper_dir, f"{ip_top}_wrapper.sv")
		if ip_wrapper_file not in ip_rtl_files:
			ip_rtl_files.append(ip_wrapper_file)

		ip_cfg["top"] = f"{ip_top}_wrapper"
		ip_cfg["rtl"] = ip_rtl_files

	config_tcl = config.generate_config_tcl(cfg, project_dir, ip_name=ip_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_ip", [], config_tcl)


#--------------------------------------------------------------------------------------------------------------
#- create --bd <bd_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_create(cfg: dict, project_dir: str, bd_name: str):
	hooks.generate_bd_hooks(cfg, project_dir, bd_name, exist_ok=True)
	config_tcl = config.generate_config_tcl(cfg, project_dir, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_bd", [], config_tcl)


#--------------------------------------------------------------------------------------------------------------
#- create --platform <platform_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_platform_create(cfg: dict, project_dir: str, platform_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	plat_cfg = platform._resolve_platform_cfg(cfg, platform_name)
	xsa, _ = platform._platform_paths(cfg, project_dir, build_dir, plat_cfg)
	bsp = platform._bsp_dir(build_dir, platform_name)
	cpu = plat_cfg["cpu"]
	os_name = plat_cfg.get("os", "standalone")

	if not os.path.exists(xsa):
		sys.exit(
			f"ERROR: XSA not found: {xsa}\n"
			f"  Run synthesis for platform '{platform_name}' first."
		)

	logger.info("Creating BSP platform '%s'", platform_name)
	logger.info("  XSA    : %s", xsa)
	logger.info("  CPU    : %s", cpu)
	logger.info("  OS     : %s", os_name)
	logger.info("  BSP dir: %s", bsp)

	vitis.run_xsct(cfg, vitis._find_xsct_script(), ["create_platform", xsa, cpu, os_name, bsp])


#--------------------------------------------------------------------------------------------------------------
#- create --app <app_name> | --platform <platform_name> | --template <template_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_app_create(cfg: dict, project_dir: str, app_name: str, platform_name: typing.Optional[str], template_name: typing.Optional[str]):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))
	
	app_cfg = platform._resolve_app_cfg(cfg, app_name)
	
	plat_name = platform_name or app_cfg["platform"]
	# plat_name = app_cfg["platform"]

	plat_cfg = platform._resolve_platform_cfg(cfg, plat_name)
	xsa, _ = platform._platform_paths(cfg, project_dir, build_dir, plat_cfg)
	bsp = platform._bsp_dir(build_dir, plat_name)

	if not os.path.exists(xsa):
		sys.exit(
			f"ERROR: XSA not found: {xsa}\n"
			f"  Run synthesis for platform '{plat_name}' first."
		)

	# Auto-create BSP if absent
	if not os.path.isdir(bsp):
		logger.info("BSP not found - creating platform '%s' first", plat_name)
		cmd_platform_create(cfg, project_dir, plat_name)


	app_out_dir = platform._app_dir(build_dir, app_name)
	cpu = plat_cfg["cpu"]
	os_name = plat_cfg.get("os", "standalone")

	template = template_name or app_cfg.get("template", "empty_application")
	src_dir = app_cfg.get("src_dir", f"srcs/sw/{app_name}")

	logger.info("Creating app '%s' from template '%s'", app_name, template)
	logger.info("  App dir : %s", app_out_dir)

	vitis.run_xsct(cfg, vitis._find_xsct_script(), ["create_app", xsa, cpu, os_name, template, app_out_dir])

	if not os.path.isdir(src_dir):
		logger.warning(f"src_dir not found, creating {src_dir}")

	os.makedirs(src_dir, exist_ok=True)



#--------------------------------------------------------------------------------------------------------------
#- edit --ip <ip_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_ip_edit(cfg: dict, project_dir: str, ip_name: str):
	config_tcl = config.generate_config_tcl(cfg, project_dir, ip_name=ip_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_ip", [], config_tcl)


#--------------------------------------------------------------------------------------------------------------
#- edit --bd <bd_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_edit(cfg: dict, project_dir: str, bd_name: str):
	config_tcl = config.generate_config_tcl(cfg, project_dir, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_bd", [], config_tcl)



#--------------------------------------------------------------------------------------------------------------
#- config --ip <ip_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_ip_config(cfg: dict, project_dir: str, ip_name: str):
	hooks.generate_ip_hooks(cfg, project_dir, ip_name)


#--------------------------------------------------------------------------------------------------------------
#- config --bd <bd_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_config(cfg: dict, project_dir: str, bd_name: str):
	hooks.generate_bd_hooks(cfg, project_dir, bd_name)

#--------------------------------------------------------------------------------------------------------------
#- config --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_top_config(cfg: dict, project_dir: str, top_name: str):
	hooks.generate_top_hooks(cfg, project_dir, top_name)



#--------------------------------------------------------------------------------------------------------------
#- generate --bd <bd_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_generate(cfg: dict, project_dir: str, bd_name: str):
	config_tcl = config.generate_config_tcl(cfg, project_dir, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "generate_bd", [], config_tcl)



#--------------------------------------------------------------------------------------------------------------
#- export --bd <bd_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_save(cfg: dict, project_dir: str, bd_name: str):
	sha, dirty, tag = utils._git_sha_tag()

	bd_list = cfg.get("bd", [])
	bd_cfg = next((b for b in bd_list if b["name"] == bd_name), None)
	if bd_cfg is None:
		sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

	export_base = bd_cfg.get("export_tcl", f"scripts/bd/{bd_name}.tcl")
	export_base = os.path.abspath(os.path.join(project_dir, export_base))
	stem = os.path.splitext(export_base)[0]
	versioned = f"{stem}_{tag}.tcl"
	symlink = export_base

	logger.info("BD export: sha=%s dirty=%s", sha, dirty)
	logger.info("BD export versioned: %s", versioned)
	logger.info("BD export symlink  : %s", symlink)

	if dirty:
		logger.warning(
			"Working tree is dirty - export tagged _dirty. "
			"Commit changes before a production export."
		)

	config_tcl = config.generate_config_tcl(
		cfg, project_dir,
		bd_name=bd_name,
		bd_export_path=versioned,
	)

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "export_bd", [], config_tcl)
	vivado._strip_bd_tcl(versioned)

	utils._atomic_symlink(versioned, symlink)
	logger.info(
		"Symlink updated: %s -> %s",
		os.path.basename(symlink),
		os.path.basename(versioned),
	)

	print(f"Exported : {versioned}")
	print(f"Symlink  : {symlink} -> {os.path.basename(versioned)}")



#--------------------------------------------------------------------------------------------------------------
#- synth --ip <ip_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_ip_synth(cfg: dict, project_dir: str, ip_name: str):
	pass

#--------------------------------------------------------------------------------------------------------------
#- synth --bd <bd_name> | --ooc_run
#--------------------------------------------------------------------------------------------------------------
def cmd_bd_synth(cfg: dict, project_dir: str, bd_name: str, ooc_run: typing.Optional[bool]):
	_, _, tag = utils._git_sha_tag()

	if bd_name:
		bd_list = cfg.get("bd", [])
		bd_cfg  = next((b for b in bd_list if b["name"] == bd_name), None)
		if bd_cfg is None:
			sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

		bd_wrapper_top = f"{bd_name}_wrapper"

		config_tcl = config.generate_config_tcl(
			cfg, project_dir,
			bd_name=bd_name,
			# top_name=bd_wrapper_top,
			# synth_out_of_context_synth=args.out_of_context_synth,
			# synth_report_all=args.report_all,
			# synth_report_synth=args.report_synth,
			# synth_report_place=args.report_place,
			# synth_report_rout=args.report_route,
			# synth_generate_netlist=args.generate_netlist,
		)

		vivado.run_vivado(
			cfg, vivado._find_tcl_script(), "synthesis",
			[bd_wrapper_top, tag],
			config_tcl,
		)

		# ip_args: list[str] = []

		# if args.out_of_context_run:
		# 	ip_infos = find_all_ip_ooc_info(cfg, project_dir, bd_name)

		# 	if ip_infos:
		# 		logger.info("IPs requiring OOC synthesis (%d):", len(ip_infos))
		# 		for info in ip_infos:
		# 			logger.info("  %-55s  top=%-35s  rtl=%d files", info.xci_name, info.top_module, len(info.rtl_files))
		# 	else:
		# 		logger.info(
		# 			"No leaf IPs found in BD '%s' - "
		# 			"proceeding directly to wrapper synthesis",
		# 			bd_name,
		# 		)
		# 	# Per-IP args - protocol (no inst_name field):
		# 	#   xci_name  top_module  dcp_dir  component_xml
		# 	#   n_rtl  [rtl_file ...]
		# 	#   n_inc  [inc_dir ...]
		# 	#   n_xdc  [xdc_file ...]
		# 	for info in ip_infos:
		# 		dcp_dir = os.path.join(build_dir, "synth", info.top_module, "ooc")
		# 		ip_args += [
		# 			info.xci_name,
		# 			info.top_module,
		# 			dcp_dir,
		# 			info.xml_path,
		# 			info.xci_file,                   # NEW
		# 			"1" if info.is_xilinx else "0",  # NEW
		# 			str(len(info.rtl_files)),
		# 			*info.rtl_files,
		# 			str(len(info.include_dirs)),
		# 			*info.include_dirs,
		# 			str(len(info.ooc_xdc_files)),
		# 			*info.ooc_xdc_files,
		# 		]


#--------------------------------------------------------------------------------------------------------------
#- synth --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_top_synth(cfg: dict, project_dir: str, top_name: str):
	_, _, tag = utils._git_sha_tag()

	config_tcl = config.generate_config_tcl(
		cfg, project_dir,
		top_name=top_name,
		# synth_out_of_context_synth=args.out_of_context,
		# synth_report_all=args.report_all,
		# synth_report_synth=args.report_synth,
		# synth_report_place=args.report_place,
		# synth_report_rout=args.report_route,
		# synth_generate_netlist=args.generate_netlist,
	)

	vivado.run_vivado(
		cfg, vivado._find_tcl_script(), "synthesis",
		[top_name, tag],
		config_tcl,
	)


#--------------------------------------------------------------------------------------------------------------
#- open --dcp <dcp_name> --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_dcp_open(cfg: dict, project_dir: str, dcp_name: str, top_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))
	dcp_path = os.path.abspath(os.path.join(build_dir, top_name, f"{dcp_name}.dcp"))

	config_tcl = config.generate_config_tcl(cfg, project_dir)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "open_dcp", [dcp_path], config_tcl)


#--------------------------------------------------------------------------------------------------------------
#- open --snapshot  --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_snapshot_open(cfg: dict, project_dir: str, top_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	waveform.open_snapshot(cfg, top_name, build_dir)


#--------------------------------------------------------------------------------------------------------------
#- open --wdb  --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_wdb_open(cfg: dict, project_dir: str, top_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	waveform.open_wdb(cfg, top_name, build_dir)


#--------------------------------------------------------------------------------------------------------------
#- elab --top <top_name> --run <time in ns>
#--------------------------------------------------------------------------------------------------------------
def cmd_top_elab(cfg: dict, project_dir: str, top_name: str, run: typing.Optional[str]):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))
	work_dir = os.path.join(build_dir, "elab", top_name)

	sources_cfg = cfg.get("sources", {})
	sim_files = config._resolve_globs(sources_cfg.get("sim", []), project_dir)

	vivado.run_vivado_xvlog(cfg, work_dir, sim_files)
	vivado.run_vivado_xelab(cfg, work_dir, top_name)

	if run:
		x_simulate_tcl = f"""
			log_wave -recursive *
			run {run}
			exit
		"""

		vivado.run_vivado_xsim(cfg, work_dir, top_name, x_simulate_tcl)



#--------------------------------------------------------------------------------------------------------------
#- reload --snapshot  --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_snapshot_reload(cfg: dict, project_dir: str, top_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	waveform.reload_snapshot(build_dir, top_name)


#--------------------------------------------------------------------------------------------------------------
#- reload --wdb  --top <top_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_wdb_reload(cfg: dict, project_dir: str, top_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	waveform.reload_wdb(build_dir, top_name)



#--------------------------------------------------------------------------------------------------------------
#- build --platform <platform_name>
#--------------------------------------------------------------------------------------------------------------
def cmd_platform_build(cfg: dict, project_dir: str, platform_name: str):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	# plat_cfg = platform._resolve_platform_cfg(cfg, platform_name)
	bsp = platform._bsp_dir(build_dir, platform_name)

	env = vitis._get_vitis_env(cfg)

	if not os.path.isdir(bsp):
		sys.exit(
			f"ERROR: BSP directory not found: {bsp}\n"
			f"  Run: xviv create-platform --platform {platform_name}"
		)

	logger.info("Building BSP: %s", bsp)
	subprocess.run(
		["make", f"-j{os.cpu_count() or 4}"],
		check=True,
		cwd=bsp,
		env=env
	)
	logger.info("BSP build complete")


#--------------------------------------------------------------------------------------------------------------
#- build --app <app_name> | --info
#--------------------------------------------------------------------------------------------------------------
def cmd_app_build(cfg: dict, project_dir: str, app_name: str, info: typing.Optional[bool]):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))

	app_cfg = platform._resolve_app_cfg(cfg, app_name)
	plat_name = app_cfg["platform"]
	plat_cfg = platform._resolve_platform_cfg(cfg, plat_name)
	bsp = platform._bsp_dir(build_dir, plat_name)
	cpu = plat_cfg["cpu"]
	app_out_dir = platform._app_dir(build_dir, app_name)
	src_dir = os.path.abspath(app_cfg.get("src_dir", f"srcs/sw/{app_name}"))
	env = vitis._get_vitis_env(cfg)

	platform._transform_app_makefile(os.path.join(app_out_dir, "Makefile"))

	if not os.path.isdir(app_out_dir):
		sys.exit(
			f"ERROR: App directory not found: {app_out_dir}\n"
			f"  Run: xviv create-app --app {app_name}"
		)

	bsp_include = os.path.join(bsp, cpu, "include")
	bsp_lib = os.path.join(bsp, cpu, "lib")

	c_sources = " ".join(config._resolve_globs(["**/*.c"], src_dir))

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
		env=env
	)
	logger.info("App build complete")

	if info:
		elf = platform._find_elf(app_out_dir, app_name)
		if elf:
			logger.info("ELF: %s", elf)
			print(f"\n=== ELF size: {os.path.basename(elf)} ===")
			subprocess.run([platform._mb_tool(cfg, "size"), elf])
			print(f"\n=== ELF sections: {os.path.basename(elf)} ===")
			subprocess.run([platform._mb_tool(cfg, "objdump"), "-h", elf])
		else:
			logger.warning("No ELF found in %s", app_out_dir)



#--------------------------------------------------------------------------------------------------------------
#- program | --app <app_name> | --platform <platform_name> | --elf <elf_path> | --bitstream <bitstream_path>
#--------------------------------------------------------------------------------------------------------------
def cmd_program(cfg: dict, project_dir: str, app_name: typing.Optional[str], platform_name: typing.Optional[str], elf: typing.Optional[str], bitstream: typing.Optional[str]):
	build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))
	
	server = platform._hw_server(cfg)
	
	bitstream_path = ""

	if bitstream:
		bitstream_path = os.path.abspath(bitstream)

	elif platform_name:
		plat_cfg = platform._resolve_platform_cfg(cfg, platform_name)
		_, bitstream_path = platform._platform_paths(cfg, project_dir, build_dir, plat_cfg)

	elif app_name:
		app_cfg = platform._resolve_app_cfg(cfg, app_name)
		plat_cfg = platform._resolve_platform_cfg(cfg, app_cfg.get("platform", None))
		_, bitstream_path = platform._platform_paths(cfg, project_dir, build_dir, plat_cfg)

	if not os.path.exists(bitstream_path):
		sys.exit(f"ERROR: Bitstream not found: {bitstream_path}")

	elf_path = ""

	if elf:
		elf_path = os.path.abspath(elf) or ""

		if not os.path.exists(elf_path):
			sys.exit(f"ERROR: ELF not found: {elf_path}")

	elif app_name:
		app_cfg = platform._resolve_app_cfg(cfg, app_name)
		app_out_dir = platform._app_dir(build_dir, app_name)
		elf_path = platform._find_elf(app_out_dir, app_name) or ""

		if not elf_path:
			sys.exit(
				f"ERROR: No ELF found in {app_out_dir}\n"
				f"  Run: xviv app-program --app {app_name}"
			)

	logger.info("Programming FPGA")
	logger.info("  Bitstream : %s", bitstream_path)

	if elf_path:
		logger.info("  ELF       : %s", elf_path)

	logger.info("  hw_server : %s", server)

	vitis.run_xsct(cfg, vitis._find_xsct_script(), ["program", bitstream_path, elf_path, server])


#--------------------------------------------------------------------------------------------------------------
#- processor | --reset | --status
#--------------------------------------------------------------------------------------------------------------
def cmd_processor(cfg: dict, reset: typing.Optional[bool], status: typing.Optional[bool]):
	server = platform._hw_server(cfg)

	if reset:
		logger.info("Resetting embedded processor via JTAG (%s)", server)
		vitis.run_xsct(cfg, vitis._find_xsct_script(), ["processor_reset", server])

	elif status:
		vitis.run_xsct(cfg, vitis._find_xsct_script(), ["processor_status", server])


# jtag-monitor

# 	server = _hw_server(cfg)
# 	logger.info("Starting JTAG UART monitor (Ctrl-C to stop)")
# 	logger.info("  hw_server : %s", server)
# 	run_xsct_live(cfg, xsct_script, ["jtag_uart", server])