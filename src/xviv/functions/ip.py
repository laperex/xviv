import os
import sys
import typing
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.generator.wrapper import SystemVerilogWrapper
from xviv.tools import vivado
from xviv.utils.parallel import run_parallel


# -----------------------------------------------------------------------------
# create --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_create(cfg: XvivConfig, *,
	ip_name: str | None = None
):
	cfg = cfg.build_wrappers()

	config = (
		ConfigTclCommands(cfg)
		.create_ip(ip_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)
	
	ip_cfg = cfg.get_ip(ip_name)

	run_parallel([
		(
			lambda i=i: vivado.run_vivado(cfg, config_tcl=(
				ConfigTclCommands(cfg)
				.generate_core(core_name=i.name)
				.build()
			), label=ip_name),
			i.name,
		) for i in cfg._core_list if i.vlnv == ip_cfg.vlnv and os.path.exists(i.xci_file)
	])


# -----------------------------------------------------------------------------
# edit --ip <ip_name>
# -----------------------------------------------------------------------------
def cmd_ip_edit(cfg: XvivConfig, *,
	ip_name: str,
	nogui: bool = False
):
	config = (
		ConfigTclCommands(cfg)
		.edit_ip(ip_name, nogui=nogui)
		.build()
	)

	if nogui:
		cfg.vivado.mode = "tcl"

	vivado.run_vivado(cfg, config_tcl=config)
