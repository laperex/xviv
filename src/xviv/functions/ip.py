import logging
import os

from xviv.config.project import XvivConfig
from xviv.functions.core import _run_from_name_list
from xviv.generator.tcl.commands import ConfigTclCommands

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


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(cfg: XvivConfig, *, ip_name: str | None = None, edit: bool = False, nogui: bool = False, regenerate: bool = False):
	ip_list, core_list = _ip_create_core_generate_list_from_ip_name(cfg, ip_name=ip_name, regenerate=regenerate)

	if len(ip_list) > 1:
		if edit:
			logger.warning("For IP create with multiple jobs, disabled 'edit'")

		edit = False

	_run_from_name_list(cfg, ip_list, lambda name: ConfigTclCommands(cfg).create_ip(name, edit=edit, nogui=nogui).build(), __name__)

	if core_list and regenerate:
		_run_from_name_list(
			cfg,
			core_list,
			config_tcl_function=lambda name: ConfigTclCommands(cfg).generate_core(name, force=True, reset=True).build(),
			log_file_prefix=__name__,
		)


# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: XvivConfig, *, ip_name: str, nogui: bool = False):
	if nogui:
		cfg.get_vivado().mode = "tcl"

	_run_from_name_list(cfg, [ip_name], lambda name: ConfigTclCommands(cfg).edit_ip(name, nogui=nogui).build(), __name__)
