import os

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools import vivado
from xviv.utils import error
from xviv.utils.parallel import run_parallel
from xviv.utils.tools import find_vivado_dir_path


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(
	cfg: XvivConfig, *, ip_name: str | None = None, edit: bool = False, nogui: bool = False, regenerate: bool = False
):
	cfg.validate_ip(ip_name)

	cfg.build_attach_ip_wrapper(ip_name)

	config = ConfigTclCommands(cfg).create_ip(ip_name, edit=edit, nogui=nogui).build()

	vivado.run_vivado(cfg, config_tcl=config)

	if not regenerate:
		return

	ip_cfg = cfg.get_ip(ip_name)

	try:
		run_parallel(
			[
				(
					lambda i=i: vivado.run_vivado(
						cfg, config_tcl=(ConfigTclCommands(cfg).generate_core(core_name=i.name).build()), label=ip_name
					),
					i.name,
				)
				for i in cfg._core_list
				if cfg.get_catalog().lookup(i.vlnv).vlnv == ip_cfg.vlnv and os.path.exists(i.xci_file)
			]
		)

	except error.VlnvResolveError:
		try:
			find_vivado_dir_path()
		finally:
			raise


# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: XvivConfig, *, ip_name: str, nogui: bool = False):
	config = ConfigTclCommands(cfg).edit_ip(ip_name, nogui=nogui).build()

	if nogui:
		cfg.get_vivado().mode = "tcl"

	vivado.run_vivado(cfg, config_tcl=config)
