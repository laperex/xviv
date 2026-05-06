import logging
import os
import sys
import typing

from xviv.config.project import XvivConfig


logger = logging.getLogger(__name__)


def generate_ip_hooks(cfg: XvivConfig, ip_name: str, exist_ok: bool = False) -> typing.Optional[str]:
	ip = cfg.get_ip(ip_name)

	hooks_path = cfg.abs_path(ip.hooks)

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
""")
	logger.info("IP hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_bd_hooks(cfg: XvivConfig, bd_name: str, exist_ok: bool = False) -> typing.Optional[str]:
	bd = cfg.get_bd(bd_name)

	hooks_path = cfg.abs_path(bd.hooks)

	if os.path.exists(hooks_path):
		if exist_ok:
			logger.debug("BD hooks already exist, skipping - %s", hooks_path)
			return None
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# Hook procs - xviv create-bd / edit-bd - {bd_name}

proc bd_design_config {{ parentCell }} {{
	
}}
""")
	logger.info("BD hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_synth_hooks(cfg: XvivConfig, *, top_name: typing.Optional[str] = None, bd_name: typing.Optional[str] = None, ip_name: typing.Optional[str] = None) -> None:
	synth = cfg.get_synth(top_name=top_name, bd_name=bd_name, ip_name=ip_name)

	hooks_path = cfg.abs_path(synth.hooks)

	if os.path.exists(hooks_path):
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)

	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# Hook procs - xviv synthesis - {top_name or bd_name or ip_name or ""}

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