import logging
import os

from xviv.config.params import EditParams, GenerateParams, IpCreateParams
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools.vivado import VivadoRunner

logger = logging.getLogger(__name__)


def _ip_create_core_generate_list_from_ip_name(cfg: XvivConfig, ip_name: str, regenerate: bool = False):
	ip_list: list[str] = []

	if ip_name == "*":
		ip_list = [i.name for i in cfg._ip_list]
	else:
		ip_list = [cfg.get_ip(ip_name).name]

	core_list = []

	for i in ip_list:
		ip_cfg = cfg.get_ip(i)

		cfg.validate_ip(i)

		if not regenerate:
			continue

		for core in cfg._core_list:
			if core.name in core_list or cfg.get_catalog().lookup(core.vlnv).vlnv != ip_cfg.vlnv or not os.path.exists(core.xci_file):
				continue

			core_list.append(core.name)

	return ip_list, core_list


def cmd_ip_create(cfg: XvivConfig, *, ip_name: str | None = None, params: IpCreateParams):
	ip_list, core_list = _ip_create_core_generate_list_from_ip_name(cfg, ip_name=ip_name, regenerate=params.regenerate)

	if len(ip_list) > 1:
		if params.edit:
			logger.warning("For IP create with multiple jobs, disabled 'edit'")

		params.edit = False

	VivadoRunner(cfg).make_pairs(
		ip_list, lambda name: ConfigTclCommands(cfg).create_ip(name, params).build(), label_prefix="ip", log_prefix="ip_create"
	).run_pairs()

	if core_list and params.regenerate:
		VivadoRunner(cfg).make_pairs(
			core_list,
			lambda name: ConfigTclCommands(cfg).generate_core(name, params=GenerateParams(force=True, reset=True)).build(),
			label_prefix="ip_regenerate_cores",
			log_prefix="ip_create_regenerate_cores",
		).run_pairs()


def cmd_ip_edit(cfg: XvivConfig, *, ip_name: str, params: EditParams):
	if params.nogui:
		cfg.get_vivado().mode = "tcl"

	VivadoRunner(cfg).make_pairs(
		[ip_name],
		lambda name: ConfigTclCommands(cfg).edit_ip(name, params=params).build(),
		label_prefix="ip",
		log_prefix="ip_edit",
	).run_pairs()
