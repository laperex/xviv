from __future__ import annotations

import logging
import os

from xviv.config.params import CoreCreateParams, EditParams, GenerateParams, IpCreateParams
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools.vivado import VivadoRunner
from xviv.utils import error
from xviv.utils.ascii_table import AsciiTable
from xviv.utils.theme import theme_cfg
from xviv.utils.tools import find_vivado_dir_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_core_list(
	cfg: XvivConfig,
	core_name: str,
	recursive: bool,
	filter_bd_cores: bool = False,
) -> tuple[list[str], list[str]]:
	if core_name == "*":
		core_list = [i.name for i in cfg._core_list if not i.is_bd_core or not filter_bd_cores]
	else:
		core_list = [cfg.get_core(core_name).name]

	ip_list: list[str] = []
	for i in core_list:
		core_cfg = cfg.get_core(i)

		if not recursive:
			break

		if filter_bd_cores and core_cfg.is_bd_core:
			continue

		if core_entry := cfg.get_catalog().lookup_optional(core_cfg.vlnv):
			if ip_cfg := cfg._get_ip_cfg_optional_by_vlnv(core_entry.vlnv):
				if ip_cfg.name not in ip_list and not os.path.exists(ip_cfg.component_xml_file):
					ip_list.append(ip_cfg.name)
		else:
			if _vlnv_matches := [ip_cfg for ip_cfg in cfg._ip_list if core_cfg.vlnv in ip_cfg.vlnv]:
				if len(_vlnv_matches) == 1:
					ip_list.append(_vlnv_matches.pop().name)
				else:
					raise error.AmbiguousCoreError(id, [i.vlnv for i in _vlnv_matches])
			else:
				break

	return ip_list, core_list


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_core_create(cfg: XvivConfig, *, core_name: str, params: CoreCreateParams) -> None:
	ip_list, core_list = _get_core_list(cfg, core_name=core_name, recursive=params.recursive, filter_bd_cores=True)

	if len(core_list) > 1:
		if params.edit:
			logger.warning("Core create with multiple jobs: disabling 'edit'")
		params.edit = False

	if ip_list:
		VivadoRunner(cfg).make_pairs(
			ip_list,
			lambda name: ConfigTclCommands(cfg).create_ip(name, IpCreateParams(edit=False, nogui=params.nogui)).build(),
			label_prefix="ip",
			log_prefix="ip_create",
		).run()

		cfg.refresh_catalog()

	try:
		VivadoRunner(cfg).make_pairs(
			core_list,
			lambda name: ConfigTclCommands(cfg).create_core(name, params=params).build(),
			label_prefix="core",
			log_prefix="core_create",
		).run()

	except error.CoreVlnvNotInCatalogError:
		try:
			find_vivado_dir_path()
		finally:
			raise


def cmd_core_edit(cfg: XvivConfig, *, core_name: str, params: EditParams) -> None:
	if params.nogui:
		cfg.get_vivado().mode = "tcl"

	VivadoRunner(cfg).make_pairs(
		[core_name],
		lambda name: ConfigTclCommands(cfg).edit_core(name, params=params).build(),
		label_prefix="core",
		log_prefix="core_edit",
	).run()


def cmd_core_generate(cfg: XvivConfig, *, core_name: str, params: GenerateParams) -> None:
	_, core_list = _get_core_list(cfg, core_name=core_name, recursive=False)

	VivadoRunner(cfg).make_pairs(
		core_list,
		lambda name: ConfigTclCommands(cfg).generate_core(name, params=params).build(),
		label_prefix="generate",
		log_prefix="core_generate",
	).run()


def cmd_search_core(cfg: XvivConfig, *, query: str) -> None:
	catalog = cfg.get_catalog()

	needle = query.lower()
	matches = [
		entry
		for entry in sorted(catalog.values(), key=lambda e: e.vlnv)
		if not entry.hidden
		and (
			needle in entry.vlnv.lower()
			or needle in entry.display_name.lower()
			or needle in entry.name.lower()
			or needle in entry.description.lower()
		)
	]

	if not matches:
		print(theme_cfg.error(f"No IPs found matching '{query}'."))
		print(theme_cfg.critical("Tip: try a partial name like 'fifo', 'clk', 'dma', or a vendor like 'xilinx'."))
		return

	t_ascii_table = AsciiTable(
		title="",
		headers=["VLNV", "NAME", "DESCRIPTION"],
	)

	for entry in matches:
		t_ascii_table.add_row(entry.vlnv, entry.display_name, entry.description)

	# 	flags = []
	# 	if entry.hidden:
	# 		flags.append(theme_cfg.warning("internal subcore"))
	# 	if entry.board_dependent:
	# 		flags.append(theme_cfg.warning("board-dep"))
	# 	if entry.ipi_only:
	# 		flags.append(theme_cfg.warning("IPI-only"))
	t_ascii_table.print()

	print(f'\n{len(matches)} result(s). Add to project.toml:  vlnv = "<VLNV>"  in a [[core]] entry.')
