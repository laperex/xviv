import logging

from xviv.config.params import OpenParams, SynthParams
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools.vivado import VivadoRunner
from xviv.utils import error
from xviv.utils.git import _git_sha_tag
from xviv.utils.tools import find_vivado_dir_path

logger = logging.getLogger(__name__)


def cmd_synth(
	cfg: XvivConfig,
	*,
	design_name: str | None = None,
	bd_name: str | None = None,
	core_name: str | None = None,
	params: SynthParams,
):
	cfg.validate_synth(bd=bd_name, design=design_name, core=core_name)

	synth_cfg = cfg.get_synth(bd_name=bd_name, design_name=design_name, core_name=core_name)

	if synth_cfg.bitstream:
		if synth_cfg.usr_access_value is None:
			match params.usr_access_type:
				case "git":
					sha, dirty, _ = _git_sha_tag()

					if not sha:
						raise error.SynthUsrAccessValueEmbedGitShaError()

					if dirty:
						logger.warning(
							"The Git working directory has uncommitted changes. It is highly recommended to commit before running synthesis."
						)

					synth_cfg.usr_access_value = int(sha, 16) | (0x10000000 if dirty else 0)

	if params.parallel_subcore_synth:
		find_vivado_dir_path(exit_on_fail=True)

		VivadoRunner(cfg).make_pairs(
			[i.core for i in cfg.get_subcore_list(bd_name=bd_name, design_name=design_name)],
			lambda name: ConfigTclCommands(cfg).synth(core=name, params=SynthParams()).build(),
			label_prefix="ooc_synth",
			log_prefix="ooc_synth_core",
			annotate=True,
		).run_pairs()

	VivadoRunner(cfg).make_pairs(
		[i for i in [design_name, bd_name, core_name] if i is not None],
		lambda _: ConfigTclCommands(cfg).synth(design=design_name, bd=bd_name, core=core_name, params=params).build(),
		label_prefix="ooc_synth",
		log_prefix="ooc_synth_core",
	).run_pairs()


def cmd_dcp_open(cfg: XvivConfig, *, dcp_file: str | None, params: OpenParams):
	if params.nogui:
		cfg.get_vivado().mode = "tcl"

	VivadoRunner(cfg).make_pairs(
		[dcp_file],
		lambda name: ConfigTclCommands(cfg).open_dcp(dcp_file=name, params=params).build(),
		label_prefix="dcp_open",
		log_prefix="dcp_open",
	).run_pairs()
