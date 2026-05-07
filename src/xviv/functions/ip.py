import os
import sys
import typing
from xviv.config.project import XvivConfig
from xviv.generator.hooks import generate_ip_hooks
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.generator.wrapper import SystemVerilogWrapper
from xviv.tools import vivado


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(cfg: XvivConfig, ip_name: typing.Optional[str] = None, ip_vlnv: typing.Optional[str] = None):
	ip = cfg.get_ip(ip_name)

	config = (
		ConfigTclCommands(cfg)
		.create_ip(ip_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config, dry_run=True)

	# if ip is None:
	# 	sys.exit(f"ERROR: Unable to Resolve IP from ip_name: {ip_name}, ip_vlnv: {ip_vlnv}")

	# if ip.create_wrapper:
	# 	ip_top        = ip.top
	# 	ip_rtl_files  = cfg.resolve_globs(ip.rtl)

	# 	xviv_wrap_top(ip_top, cfg.wrapper_dir, ip_rtl_files)

	# 	ip_wrapper_file = os.path.join(cfg.wrapper_dir, f"{ip_top}_wrapper.sv")
	# 	if ip_wrapper_file not in ip_rtl_files:
	# 		ip_rtl_files.append(ip_wrapper_file)

	# 	ip.top = f"{ip_top}_wrapper"
	# 	ip.rtl = ip_rtl_files

	# config_tcl = generate_config_tcl(cfg, ip_name=ip.name)
	# vivado.run_vivado(cfg, find_vivado_script(), "create_ip", [], config_tcl)

# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: XvivConfig, ip_name: str, nogui: bool = False):
	config = (
		ConfigTclCommands(cfg)
		.edit_ip(ip_name, nogui=nogui)
		.build()
	)

	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, config_tcl=config)

	# vivado.run_vivado(cfg, find_vivado_script(), "edit_ip", [str(int(not nogui))], config_tcl)


# -----------------------------------------------------------------------------
# config --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_config(cfg: XvivConfig, ip_name: str):
	generate_ip_hooks(cfg, ip_name)

# -----------------------------------------------------------------------------
# synth --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_synth(cfg: XvivConfig, ip_name: str):
	pass