import logging
from xviv.config.project import XvivConfig
from xviv.tools import vivado
from xviv.utils.git import _git_sha_tag
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils.parallel import run_parallel

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# synth (--design <design_name> | --bd <bd_name> | --core <core_name>) |
#	--usr-access-type <usr_access_type>
# -----------------------------------------------------------------------------
def cmd_synth(cfg: XvivConfig, *,
	design_name: str | None = None,
	bd_name: str | None = None,
	core_name: str | None = None,
	usr_access_type: str | None = None,
	resume: str | None = None,
):
	cfg.validate_synth(bd=bd_name, design=design_name, core=core_name)

	synth_cfg = cfg.get_synth(bd_name=bd_name, design_name=design_name, core_name=core_name)

	# if usr_access_type:
	# 	synth_cfg.usr_access_value = usr_access_type

	if synth_cfg.bitstream_file:
		if synth_cfg.usr_access_value is None:
			sha, dirty, _ = _git_sha_tag()

			if not sha:
				raise RuntimeError('Unable to determine git sha - to embed in bitstream. check if git repo is init')

			if dirty:
				logger.warning('the current repo is dirty recommended commit before synth')

			synth_cfg.usr_access_value = int(sha, 16) | (0x10000000 if dirty else 0)

	if synth_cfg.out_of_context_subcores:
		run_parallel([
			(
				lambda i=i: vivado.run_vivado(cfg, config_tcl=(
					ConfigTclCommands(cfg)
					.synth(core=i.core)
					.build()
				), label=bd_name),
				i.core,
			) for i in cfg.get_subcore_list(bd_name=bd_name, design_name=design_name)
		])

	config = (
		ConfigTclCommands(cfg)
		.synth(design=design_name, bd=bd_name, core=core_name,
		 	resume=resume
		)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# open --dcp <dcp_file> | --nogui <False>
# -----------------------------------------------------------------------------
def cmd_dcp_open(cfg: XvivConfig, *,
	dcp_file: str | None,
	nogui: bool = False
):
	config = (
		ConfigTclCommands(cfg)
		.open_dcp(dcp_file=dcp_file)
		.build()
	)

	if nogui:
		cfg.get_vivado().mode = "tcl"

	vivado.run_vivado(cfg, config_tcl=config)
