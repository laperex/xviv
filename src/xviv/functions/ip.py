import os
import sys
import typing
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.generator.wrapper import SystemVerilogWrapper
from xviv.tools import vivado


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
