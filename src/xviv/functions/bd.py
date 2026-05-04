from functools import partial
import json
import logging
import os
from pathlib import Path
import sys
import typing
from xviv.catalog.catalog import get_catalog
from xviv.config.model import ProjectConfig
# from xviv.config.tcl import ConfigTclCommands, _tcl_list, generate_config_tcl
from xviv.config.tcl import ConfigTclCommands
from xviv.functions.ip import cmd_ip_create
from xviv.generator.hooks import generate_bd_hooks
from xviv.parsers.bd_json import get_bd_core_dict
from xviv.tools import vivado
from xviv.tools.util import find_vivado_script
from xviv.utils.git import _git_sha_tag
from xviv.utils.parallel import run_parallel

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	config = (
		ConfigTclCommands(cfg)
		.create_bd(bd_name)
		.build()
	)

	# bd_cfg = cfg.get_bd(bd_name)

	# catalog = cfg.get_catalog()

	# required_ips = bd_cfg.vlnv_list
	
	# if required_ips:
	# 	logger.info(f"Determined IP depenedency list for BD {bd_name}. Running Automatic Paralllel BD Create flow\n- {'\n- '.join(required_ips)}")

	# 	logger.info("IPs to be created in parallel jobs:")

	# 	required_ips_create_list = []
	# 	for i in required_ips:
	# 		if i in [k.vlnv for k in cfg.ips]:
	# 			logger.info(f"\t- {i}")
	# 			required_ips_create_list.append(i)

	# 	unresolved_ips = [i for i in required_ips if not catalog.get(i) and i not in required_ips_create_list]

	# 	if unresolved_ips:
	# 		sys.exit(f"ERROR: These IP's cannot be resolved: {unresolved_ips}")

	# 	if required_ips_create_list:
	# 		max_workers = cfg.build.max_parallel_jobs

	# 		run_parallel(
	# 			[(partial(cmd_ip_create, cfg, ip_vlnv=v), f"cmd_ip_create({v})") for v in required_ips_create_list],
	# 		max_workers=max_workers)
	# else:
	# 	logger.info("Unable to Determine IP depenedency for BD. Running Manual BD Create flow")

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: ProjectConfig, bd_name: str, nogui: bool = False):
	config = (
		ConfigTclCommands(cfg)
		.edit_bd(bd_name, nogui=nogui)
		.build()
	)

	if nogui:
		cfg.vivado.mode = 'tcl'

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# config --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_config(cfg: ProjectConfig, bd_name: str, exist_ok=False):
	generate_bd_hooks(cfg, bd_name, exist_ok=exist_ok)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: ProjectConfig, bd_name: str):
	config = (
		ConfigTclCommands(cfg)
		.generate_bd(bd_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# synth --bd <bd_name> [--ooc-run]
# -----------------------------------------------------------------------------
def cmd_bd_synth(cfg: ProjectConfig, bd_name: str, ooc_run: typing.Optional[bool]):
	def _is_stale(target_dir: Path, xci_path: Path, xci_name: str) -> bool:
		dcp  = target_dir / f"{xci_name}.dcp"
		stub = target_dir / f"{xci_name}.v"

		if not dcp.exists() or not stub.exists():
			logger.info(f"[is_stale] {xci_name}: output missing, rebuild needed")
			return True

		xci_mtime  = xci_path.stat().st_mtime
		dcp_mtime  = dcp.stat().st_mtime
		stub_mtime = stub.stat().st_mtime

		if xci_mtime > dcp_mtime or xci_mtime > stub_mtime:
			logger.info(f"[is_stale] {xci_name}: xci newer than outputs, rebuild needed")
			return True

		logger.info(f"[is_stale] {xci_name}: up to date, skipping")
		return False

	# config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	components = get_bd_core_dict(cfg, bd_name)

	if components:
		bd_xci_name_list = [i['xci_name'] for i in components]
		bd_xci_path_list = [i['xci_path'] for i in components]
		# bd_inst_hier_path_list = [i['inst_hier_path'] for i in components]
	
		config_tcl += "\n".join(
			[
				f'set xviv_bd_xci_name_list		  {_tcl_list(bd_xci_name_list)}',
				f'set xviv_bd_xci_path_list		  {_tcl_list(bd_xci_path_list)}',
				# f'set xviv_bd_inst_hier_path_list {_tcl_list(bd_inst_hier_path_list)}',
			]
		)

		max_workers = 15

		cfg.vivado.mode = 'batch'

		run_parallel(
			[
				(
					partial(vivado.run_vivado,
						cfg, find_vivado_script(), "standalone_synthesis",
						[ f"{i}" ],
						config_tcl,
						val['xci_name'],
						cfg.build_dir
					),
					f"vivado.run_vivado - [ {val['xci_name']} ]"
				) for i, val in enumerate(components)
				if _is_stale(Path(cfg.get_bd_ooc_targets_dir(bd_name)), Path(val['xci_path']), val['xci_name'])
			],
			max_workers=max_workers
		)

	cfg.vivado.mode = 'batch'

	_, _, tag = _git_sha_tag()

	vivado.run_vivado(
		cfg, find_vivado_script(), "synthesis",
		[f"{bd_name}_wrapper", tag],
		config_tcl,
	)
