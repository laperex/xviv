from functools import partial
import logging
import os
from pathlib import Path
import sys
import typing
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
# from xviv.generator.hooks import generate_bd_hooks
from xviv.parsers.bd_json import get_bd_core_list
from xviv.tools import vivado
from xviv.utils.git import _git_sha_tag
from xviv.utils.parallel import run_parallel

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: XvivConfig, *,
	bd_name: str
):
	config = (
		ConfigTclCommands(cfg)
		.create_bd(bd_name, generate=True)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: XvivConfig, *,
	bd_name: str,
	nogui: bool = False
):
	config = (
		ConfigTclCommands(cfg)
		.edit_bd(bd_name, nogui=nogui)
		.build()
	)

	if nogui:
		cfg.get_vivado().mode = 'tcl'

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: XvivConfig, *,
	bd_name: str
):
	config = (
		ConfigTclCommands(cfg)
		.generate_bd(bd_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# synth --bd <bd_name> [--ooc-run]
# -----------------------------------------------------------------------------
def cmd_bd_synth(cfg: XvivConfig, *,
	bd_name: str
):
	# xci_name = bd_cfg.core_list[0].name
	# xci_file = bd_cfg.core_list[0].xci_file

	# dcp_file = os.path.join(cfg.synth_dir, xci_name, f'{xci_name}.dcp')
	# stub_file = os.path.join(cfg.synth_dir, xci_name, f'{xci_name}.v')

	# config = (
	# 	ConfigTclCommands(cfg)
	# 	.synth_xci_out_of_context(
	# 		xci_name, xci_file,
	# 		dcp_file=dcp_file,
	# 		stub_file=stub_file
	# 	)
	# 	.build()
	# )

	config = (
		ConfigTclCommands(cfg)
		.synth(bd=bd_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)

	# print(components[0])

	# def _is_stale(target_dir: Path, xci_path: Path, xci_name: str) -> bool:
	# 	dcp  = target_dir / f"{xci_name}.dcp"
	# 	stub = target_dir / f"{xci_name}.v"

	# 	if not dcp.exists() or not stub.exists():
	# 		logger.info(f"[is_stale] {xci_name}: output missing, rebuild needed")
	# 		return True

	# 	xci_mtime  = xci_path.stat().st_mtime
	# 	dcp_mtime  = dcp.stat().st_mtime
	# 	stub_mtime = stub.stat().st_mtime

	# 	if xci_mtime > dcp_mtime or xci_mtime > stub_mtime:
	# 		logger.info(f"[is_stale] {xci_name}: xci newer than outputs, rebuild needed")
	# 		return True

	# 	logger.info(f"[is_stale] {xci_name}: up to date, skipping")
	# 	return False

	# # config_tcl = generate_config_tcl(cfg, bd_name=bd_name)


	# if components:
	# 	bd_xci_name_list = [i['xci_name'] for i in components]
	# 	bd_xci_path_list = [i['xci_path'] for i in components]
	# 	# bd_inst_hier_path_list = [i['inst_hier_path'] for i in components]
	
	# 	# config_tcl += "\n".join(
	# 	# 	# [
	# 	# 	# 	f'set xviv_bd_xci_name_list		  {_tcl_list(bd_xci_name_list)}',
	# 	# 	# 	f'set xviv_bd_xci_path_list		  {_tcl_list(bd_xci_path_list)}',
	# 	# 	# 	# f'set xviv_bd_inst_hier_path_list {_tcl_list(bd_inst_hier_path_list)}',
	# 	# 	# ]
	# 	# )

	# 	max_workers = 15

	# 	cfg.vivado.mode = 'batch'

	# 	run_parallel(
	# 		[
	# 			(
	# 				partial(vivado.run_vivado,
	# 					# cfg, find_vivado_script(), "standalone_synthesis",
	# 					# [ f"{i}" ],
	# 					# config_tcl,
	# 					# val['xci_name'],
	# 					# cfg.build_dir
	# 				),
	# 				f"vivado.run_vivado - [ {val['xci_name']} ]"
	# 			) for i, val in enumerate(components)
	# 			if _is_stale(Path(cfg.get_bd_ooc_targets_dir(bd_name)), Path(val['xci_path']), val['xci_name'])
	# 		],
	# 		max_workers=max_workers
	# 	)

	# cfg.vivado.mode = 'batch'

	# _, _, tag = _git_sha_tag()

	# vivado.run_vivado(
	# 	# cfg, find_vivado_script(), "synthesis",
	# 	# [f"{bd_name}_wrapper", tag],
	# 	# config_tcl,
	# )
