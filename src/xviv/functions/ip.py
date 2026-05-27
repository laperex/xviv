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
def cmd_ip_create(cfg: XvivConfig, *, ip_name: str | None = None, edit: bool = False, nogui: bool = False, regenerate: bool = False):
	cfg.validate_ip(ip_name)

	cfg.build_attach_ip_wrapper(ip_name)

	config = ConfigTclCommands(cfg).create_ip(ip_name, edit=edit, nogui=nogui).build()

	vivado.run_vivado(cfg, config_tcl=config, label=__name__)

	if not regenerate:
		return

	ip_cfg = cfg.get_ip(ip_name)

	try:
		tasks = []

		for core in cfg._core_list:
			try:
				if cfg.get_catalog().lookup(core.vlnv).vlnv != ip_cfg.vlnv:
					continue
			except error.VlnvResolveError:
				find_vivado_dir_path()
				raise

			if not os.path.exists(core.xci_file):
				continue

			log_file_path = os.path.join(cfg.log_dir, f"job_synth_{core.name}.log")

			tasks.append(
				(
					lambda core=core, log_file_path=log_file_path: vivado.run_vivado(
						cfg,
						config_tcl=(ConfigTclCommands(cfg).generate_core(core_name=core.name).build()),
						label=f"{__name__}_job_{ip_name}",
						parallel=True,
						log_file_path=log_file_path,
					),
					core.name,
					log_file_path,
				)
			)

		run_parallel(tasks, dry_run=cfg.dry_run)
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

	vivado.run_vivado(cfg, config_tcl=config, label=__name__)
