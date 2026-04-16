import logging
import os
import typing
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.generator.hooks import generate_bd_hooks
from xviv.tools import vivado
from xviv.utils.fs import _atomic_symlink
from xviv.utils.git import _git_sha_tag

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	cmd_bd_config(cfg, bd_name)
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_bd", [], config_tcl)
	

# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# config --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_config(cfg: ProjectConfig, bd_name: str):
	generate_bd_hooks(cfg, bd_name)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)
	vivado.run_vivado(cfg, vivado._find_tcl_script(), "generate_bd", [], config_tcl)


# -----------------------------------------------------------------------------
# export --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_export(cfg: ProjectConfig, bd_name: str):
	sha, dirty, tag = _git_sha_tag()

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

	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "export_bd", [versioned], config_tcl)
	vivado._strip_bd_tcl(versioned)

	_atomic_symlink(versioned, symlink)
	logger.info(
		"Symlink updated: %s -> %s",
		os.path.basename(symlink),
		os.path.basename(versioned),
	)

	print(f"Exported : {versioned}")
	print(f"Symlink  : {symlink} -> {os.path.basename(versioned)}")


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