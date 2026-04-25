import logging
import sys
import typing
from xviv.catalog.catalog import get_catalog
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_bd_hooks
from xviv.tools import vivado
from xviv.tools.util import find_vivado_script
from xviv.utils.git import _git_sha_tag

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	bd_cfg = cfg.get_bd(bd_name)

	catalog = get_catalog(cfg.vivado.path, [ cfg.ip_repo ])

	required_ips = bd_cfg.vlnv_list

	unresolved_ips = [i for i in required_ips if not catalog.get(i)]
	if unresolved_ips:
		sys.exit(f"ERROR: These IP's cannot be resolved: {unresolved_ips}")

	required_ips_create_list = [i for i in required_ips if i in [k.vlnv for k in cfg.ips]]
	if required_ips_create_list:
		pass

	vivado.run_vivado(cfg, find_vivado_script(), "create_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: ProjectConfig, bd_name: str, nogui: bool = False):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, find_vivado_script(), "edit_bd", [str(int(not nogui))], config_tcl)


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
	vivado.run_vivado(cfg, find_vivado_script(), "generate_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# synth --bd <bd_name> [--ooc-run]
# -----------------------------------------------------------------------------
def cmd_bd_synth(cfg: ProjectConfig, bd_name: str, ooc_run: typing.Optional[bool]):
	_, _, tag = _git_sha_tag()

	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(
		cfg, find_vivado_script(), "synthesis",
		[f"{bd_name}_wrapper", tag],
		config_tcl,
	)