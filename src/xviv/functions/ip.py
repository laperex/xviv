import os
from xviv.tools import vivado
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_ip_hooks
from xviv.generator.wrapper import xviv_wrap_top


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(cfg: ProjectConfig, ip_name: str):
	ip = cfg.get_ip(ip_name)

	if ip.create_wrapper:
		ip_top        = ip.top
		ip_rtl_files  = cfg.resolve_globs(ip.rtl)

		xviv_wrap_top(ip_top, cfg.wrapper_dir, ip_rtl_files)

		ip_wrapper_file = os.path.join(cfg.wrapper_dir, f"{ip_top}_wrapper.sv")
		if ip_wrapper_file not in ip_rtl_files:
			ip_rtl_files.append(ip_wrapper_file)

		# Mutate the dataclass so generate_config_tcl picks up the wrapper top/rtl.
		ip.top = f"{ip_top}_wrapper"
		ip.rtl = ip_rtl_files   # absolute paths are glob-safe on POSIX

	config_tcl = generate_config_tcl(cfg, ip_name=ip_name)
	vivado.run_vivado(cfg, vivado.find_vivado_script(), "create_ip", [], config_tcl)

# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: ProjectConfig, ip_name: str, nogui: bool = False):
	config_tcl = generate_config_tcl(cfg, ip_name=ip_name)

	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, vivado.find_vivado_script(), "edit_ip", [str(int(not nogui))], config_tcl)


# -----------------------------------------------------------------------------
# config --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_config(cfg: ProjectConfig, ip_name: str):
	generate_ip_hooks(cfg, ip_name)

# -----------------------------------------------------------------------------
# synth --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_synth(cfg: ProjectConfig, ip_name: str):
	pass