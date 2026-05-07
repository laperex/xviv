import typing
from xviv.config.project import XvivConfig
# from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_synth_hooks
# from xviv.tools.util import find_vivado_script
from xviv.utils.git import _git_sha_tag


# -----------------------------------------------------------------------------
# config (--top <top_name> | --bd <bd_name>) --synth
# -----------------------------------------------------------------------------
def cmd_synth_config(cfg: XvivConfig, top_name: str | None, bd_name: str | None, ip_name: str | None):
	generate_synth_hooks(cfg, top_name=top_name, bd_name=bd_name, ip_name=ip_name)


# -----------------------------------------------------------------------------
# synth --top <top_name>
# -----------------------------------------------------------------------------
def cmd_top_synth(cfg: XvivConfig, top_name: str):
	_, _, tag = _git_sha_tag()

	# config_tcl = generate_config_tcl(cfg, top_name=top_name)

	# vivado.run_vivado(
	# 	# cfg, find_vivado_script(), "synthesis",
	# 	[top_name, tag],
	# 	config_tcl,
	# )


# -----------------------------------------------------------------------------
# open --dcp <dcp_name> --top <top_name>
# -----------------------------------------------------------------------------
def cmd_dcp_open(cfg: XvivConfig, dcp_name: str, top_name: str | None, bd_name: str | None, nogui: bool = False):
	# config_tcl = generate_config_tcl(cfg, top_name=top_name, bd_name=bd_name)

	dcp_path   = cfg.get_dcp_path(top_name or f"{bd_name}_wrapper", dcp_name)

	# To inspect dcp with custom commnds in terminal
	if nogui:
		cfg.vivado.mode = "tcl"

	# vivado.run_vivado(cfg, find_vivado_script(), "open_dcp", [dcp_path, str(int(not nogui))], config_tcl)
