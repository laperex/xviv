import logging
import os
import typing
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_bd_hooks
from xviv.tools import vivado
from xviv.utils.git import _git_sha_tag

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: ProjectConfig, bd_name: str, nogui: bool = False):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_bd", [str(int(not nogui))], config_tcl)


# -----------------------------------------------------------------------------
# config --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_config(cfg: ProjectConfig, bd_name: str, exist_ok=False):
	generate_bd_hooks(cfg, bd_name, exist_ok=exist_ok)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "generate_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# synth --bd <bd_name> [--ooc-run]
# -----------------------------------------------------------------------------
def cmd_bd_synth(cfg: ProjectConfig, bd_name: str, ooc_run: typing.Optional[bool]):
	_, _, tag = _git_sha_tag()

	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(
		cfg, vivado._find_tcl_script(), "synthesis",
		[f"{bd_name}_wrapper", tag],
		config_tcl,
	)