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
