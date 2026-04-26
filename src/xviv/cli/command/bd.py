from functools import partial
import json
import logging
import os
import sys
import typing
from xviv.catalog.catalog import get_catalog
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.functions.ip import cmd_ip_create
from xviv.generator.hooks import generate_bd_hooks
from xviv.parsers.bd_file import get_bd_core_dict
from xviv.tools import vivado
from xviv.tools.util import find_vivado_script
from xviv.utils.git import _git_sha_tag
from xviv.utils.parallel import run_parallel

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(cfg: ProjectConfig, bd_name: str):
	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	bd_cfg = cfg.get_bd(bd_name)

	catalog = get_catalog(cfg.vivado.path, [ cfg.ip_repo ])

	required_ips = bd_cfg.vlnv_list
	
	if required_ips:
		logger.info(f"Determined IP depenedency list for BD {bd_name}. Running Automatic Paralllel BD Create flow\n- {'\n- '.join(required_ips)}")

		logger.info("IPs to be created in parallel jobs:")

		required_ips_create_list = []
		for i in required_ips:
			if i in [k.vlnv for k in cfg.ips]:
				logger.info(f"\t- {i}")
				required_ips_create_list.append(i)

		unresolved_ips = [i for i in required_ips if not catalog.get(i) and i not in required_ips_create_list]

		if unresolved_ips:
			sys.exit(f"ERROR: These IP's cannot be resolved: {unresolved_ips}")

		if required_ips_create_list:
			max_workers = cfg.build.max_parallel_jobs

			run_parallel(
				[(partial(cmd_ip_create, cfg, ip_vlnv=v), f"cmd_ip_create({v})") for v in required_ips_create_list],
			max_workers=max_workers)
	else:
		logger.info("Unable to Determine IP depenedency for BD. Running Manual BD Create flow")

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
	# _, _, tag = _git_sha_tag()

	# config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	# vivado.run_vivado(
	# 	cfg, find_vivado_script(), "synthesis",
	# 	[f"{bd_name}_wrapper", tag],
	# 	config_tcl,
	# )
	# _, _, tag = _git_sha_tag()

	config_tcl = generate_config_tcl(cfg, bd_name=bd_name)

	components = get_bd_core_dict(cfg, bd_name)

	cfg.vivado.mode = 'batch'

	if components:
		max_workers = 15

		target_dir = cfg.get_bd_ooc_targets_dir_path(bd_name)

		run_parallel(
			[
				(
					partial(vivado.run_vivado,
						cfg, find_vivado_script(), "standalone_synthesis",
						[ c['vlnv'], c['xci_name'], c['xci_path'], c['inst_hier_path'], target_dir ],
						config_tcl,
						c['xci_name'],
						cfg.build_dir
					),
					f"vivado.run_vivado - [ {c['vlnv']}, {c['xci_name']}, {c['xci_path']}, {c['inst_hier_path']} ]"
				) for c in components
			],
			max_workers=max_workers
		)
