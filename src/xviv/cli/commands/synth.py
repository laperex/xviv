import typing
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_top_hooks
from xviv.tools import vivado
from xviv.utils.git import _git_sha_tag


# -----------------------------------------------------------------------------
# config --top <top_name>
# -----------------------------------------------------------------------------
def cmd_top_config(cfg: ProjectConfig, top_name: str):
	generate_top_hooks(cfg, top_name)


# -----------------------------------------------------------------------------
# synth --top <top_name>
# -----------------------------------------------------------------------------
def cmd_top_synth(cfg: ProjectConfig, top_name: str):
	_, _, tag = _git_sha_tag()

	config_tcl = generate_config_tcl(cfg, top_name=top_name)

	vivado.run_vivado(
		cfg, vivado._find_tcl_script(), "synthesis",
		[top_name, tag],
		config_tcl,
	)


# -----------------------------------------------------------------------------
# open --dcp <dcp_name> --top <top_name>
# -----------------------------------------------------------------------------
def cmd_dcp_open(cfg: ProjectConfig, dcp_name: str, top_name: typing.Optional[str], bd_name: typing.Optional[str], nogui: bool = False):
	config_tcl = generate_config_tcl(cfg, top_name=top_name, bd_name=bd_name)

	dcp_path   = cfg.get_dcp_path(top_name or f"{bd_name}_wrapper", dcp_name)

	# To inspect dcp with custom commnds in terminal
	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "open_dcp", [dcp_path, str(int(not nogui))], config_tcl)
