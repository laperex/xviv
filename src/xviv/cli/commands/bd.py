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
# export --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_export(cfg: ProjectConfig, bd_name: str):
	def _strip_bd_tcl(path: str, prefix: list[str]) -> None:
		with open(path, "r") as f:
			data = f.read()
		start = data.find("set bCheckIPsPassed")
		end = data.find("save_bd_design")
		if start == -1 or end == -1:
			raise RuntimeError(
				f"Could not find expected markers in exported BD TCL: {path}\n"
				f"  'set bCheckIPsPassed' found: {start != -1}\n"
				f"  'save_bd_design'     found: {end != -1}"
			)
		with open(path, "w") as f:
			f.write('\n'.join(prefix) + '\n\n' + data[start:end])

	sha, dirty, tag = _git_sha_tag()

	bd         = cfg.get_bd(bd_name)
	export_base = cfg.abs_path(bd.export_tcl)

	os.makedirs(os.path.dirname(export_base), exist_ok=True)

	logger.info("BD export: sha=%s dirty=%s", sha, dirty)
	logger.info("BD export path: %s", export_base)

	if dirty:
		logger.warning(
			"Working tree is dirty - export tagged _dirty. "
			"Commit changes before a production export."
		)

	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "export_bd", [export_base], config_tcl)
	_strip_bd_tcl(export_base, [
		f"# commit: {sha}",
		f"# dirty:  {dirty}",
		f"# bd:     {bd_name}"
	])

	print(f"Exported : {export_base}")


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