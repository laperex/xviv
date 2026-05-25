from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools import vivado


# -----------------------------------------------------------------------------
# create --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_create(
	cfg: XvivConfig,
	*,
	bd_name: str,
	source_file: str | bool = True,
	generate: bool = True,
	edit: bool = False,
	nogui: bool = False,
):
	config = (
		ConfigTclCommands(cfg)
		.create_bd(bd_name, source_file=source_file, generate=generate, edit=edit, nogui=nogui)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# edit --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_edit(cfg: XvivConfig, *, bd_name: str, nogui: bool = False):
	config = ConfigTclCommands(cfg).edit_bd(bd_name, nogui=nogui).build()

	if nogui:
		cfg.get_vivado().mode = "tcl"

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# generate --bd <bd_name>
# -----------------------------------------------------------------------------
def cmd_bd_generate(cfg: XvivConfig, *, bd_name: str, force: bool = True, reset: bool = True):
	config = ConfigTclCommands(cfg).generate_bd(bd_name, force=force, reset=reset).build()

	vivado.run_vivado(cfg, config_tcl=config)
