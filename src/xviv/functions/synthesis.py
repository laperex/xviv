from xviv.config.project import XvivConfig
from xviv.tools import vivado
from xviv.utils.git import _git_sha_tag
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils.parallel import run_parallel


# -----------------------------------------------------------------------------
# synth --top <top_name>
# -----------------------------------------------------------------------------
def cmd_synth(cfg: XvivConfig, *,
	design_name: str | None = None,
	bd_name: str | None = None,
	core_name: str | None = None,
):
	cfg.validate_synth(bd=bd_name, design=design_name, core=core_name)

	synth_cfg = cfg.get_synth(bd_name=bd_name, design_name=design_name, core_name=core_name)

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
		.synth(design=design_name, bd=bd_name, core=core_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)


# -----------------------------------------------------------------------------
# open --dcp <dcp_name> --top <top_name>
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
