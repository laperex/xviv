import logging

from xviv.config.project import XvivConfig
from xviv.functions.core import _run_from_name_list
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils import error
from xviv.utils.git import _git_sha_tag
from xviv.utils.tools import find_vivado_dir_path

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# synth (--design <design_name> | --bd <bd_name> | --core <core_name>) |
# --usr-access-type <usr_access_type>
# -----------------------------------------------------------------------------
def cmd_synth(
	cfg: XvivConfig,
	*,
	design_name: str | None = None,
	bd_name: str | None = None,
	core_name: str | None = None,
	usr_access_type: str | None = None,
	resume: str | None = None,
	parallel_subcore_synth: bool | None = None,
):
	cfg.validate_synth(bd=bd_name, design=design_name, core=core_name)

	synth_cfg = cfg.get_synth(bd_name=bd_name, design_name=design_name, core_name=core_name)

	if synth_cfg.bitstream:
		if synth_cfg.usr_access_value is None:
			match usr_access_type:
				case "git":
					sha, dirty, _ = _git_sha_tag()

					if not sha:
						raise error.SynthUsrAccessValueEmbedGitShaError()

					if dirty:
						logger.warning(
							"The Git working directory has uncommitted changes. It is highly recommended to commit before running synthesis."
						)

					synth_cfg.usr_access_value = int(sha, 16) | (0x10000000 if dirty else 0)

	if parallel_subcore_synth:
		find_vivado_dir_path(exit_on_fail=True)

		_run_from_name_list(
			cfg,
			[i.core for i in cfg.get_subcore_list(bd_name=bd_name, design_name=design_name)],
			lambda name: ConfigTclCommands(cfg).synth(core=name).build(),
			__name__,
			# run_config_tcl_function_in_task=True
		)

	_run_from_name_list(
		cfg,
		[i for i in [design_name, bd_name, core_name] if i is not None],
		lambda _: (
			ConfigTclCommands(cfg)
			.synth(design=design_name, bd=bd_name, core=core_name, resume=resume, parallel_subcore_synth=parallel_subcore_synth)
			.build()
		),
		__name__,
	)


# -----------------------------------------------------------------------------
# open --dcp <dcp_file> | --nogui <False>
# -----------------------------------------------------------------------------
def cmd_dcp_open(cfg: XvivConfig, *, dcp_file: str | None, nogui: bool = False):
	if nogui:
		cfg.get_vivado().mode = "tcl"

	_run_from_name_list(cfg, [dcp_file], lambda name: ConfigTclCommands(cfg).open_dcp(dcp_file=name).build(), __name__)
