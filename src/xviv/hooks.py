import logging
import os
import sys
import typing

from xviv import config

logger = logging.getLogger(__name__)


def generate_ip_hooks(cfg: dict, project_dir: str, ip_name: str, exist_ok: bool = False) -> typing.Optional[str]:
	ip_cfg = config._get_ip_cfg(cfg, ip_name)

	hooks_path = config._get_ip_hooks(ip_cfg)

	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		if exist_ok:
			logger.debug("IP hooks already exist, skipping - %s", hooks_path)

			return None
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)

	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# Hook procs - xviv create-ip - {ip_name}

# Called after the IP edit project is opened.
# Add your RTL source files to the edit project here.
proc ipx_add_files {{}} {{
	add_files [glob -nocomplain ./srcs/rtl/*.sv]
	add_files [glob -nocomplain ./srcs/rtl/*.v]
}}

# Called after ipx::merge_project_changes.
proc ipx_merge_changes {{}} {{

}}

# Called after the default axis/aximm inference.
# Add inferences for any other bus standards your IP uses.
proc ipx_infer_bus_interfaces {{}} {{
	# example:
	# ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]
}}

# Called after HDL parameters are added to the IP GUI.
# Use to reorder, group, or add display conditions.
proc ipx_add_params {{}} {{
	# example:
	# ipgui::move_param -component [ipx::current_core] \\
	#     -order 0 [ipgui::get_guiparamspec -name "DATA_WIDTH" \\
	#     -component [ipx::current_core]] \\
	#     -parent [ipgui::get_pagespec -name "Page 0" -component [ipx::current_core]]
}}

# Called after bus interfaces are set up.
proc ipx_add_memory_map {{}} {{

}}


# Hook procs - xviv synthesis - {ip_name}

proc synth_pre {{}} {{

}}

proc synth_post {{}} {{

}}

proc place_post {{}} {{

}}

proc route_post {{}} {{

}}

proc bitstream_post {{}} {{

}}
""")
	logger.info("IP hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_bd_hooks(cfg: dict, project_dir: str, bd_name: str, exist_ok: bool = False) -> typing.Optional[str]:
	bd_cfg = config._get_bd_cfg(cfg, bd_name)

	hooks_path = config._get_bd_hooks(bd_cfg)
	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		if exist_ok:
			logger.debug("BD hooks already exist, skipping - %s", hooks_path)
			return None
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	export_tcl_abs = os.path.abspath(os.path.join(project_dir, config._get_bd_export_tcl(bd_cfg)))
	export_tcl_rel = os.path.relpath(export_tcl_abs, os.path.dirname(hooks_path))

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# Hook procs - xviv create-bd / edit-bd - {bd_name}
set ::_bd_design_tcl [file join [file dirname [info script]] "{export_tcl_rel}"]

proc bd_design_config {{ parentCell }} {{
	global _bd_design_tcl

	if {{[file exists $_bd_design_tcl]}} {{
		puts "INFO: Sourcing exported BD TCL - $_bd_design_tcl"
		source $_bd_design_tcl

		xviv_refresh_bd_addresses
		validate_bd_design
		save_bd_design
		exit 0

	}} else {{
		puts "INFO: No exported BD TCL found at $_bd_design_tcl"
		puts "INFO: Opening GUI for interactive design."
		puts "INFO: When done, run:  xviv export-bd --bd {bd_name}"
		start_gui
	}}
}}

# Hook procs - xviv synthesis - {bd_name}

proc synth_pre {{}} {{

}}

proc synth_post {{}} {{

}}

proc place_post {{}} {{

}}

proc route_post {{}} {{

}}

proc bitstream_post {{}} {{

}}
""")
	logger.info("BD hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_synth_hooks(cfg: dict, project_dir: str, top_name: str) -> None:
	synth_cfg = config._get_synth_cfg(cfg, top_name)

	hooks_path = config._get_synth_hooks(synth_cfg)
	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)

	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# Hook procs - xviv synthesis - {top_name}

proc synth_pre {{}} {{

}}

proc synth_post {{}} {{

}}

proc place_post {{}} {{

}}

proc route_post {{}} {{

}}

proc bitstream_post {{}} {{

}}

""")
	logger.info("Synthesis hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
