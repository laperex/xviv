from xviv.generator.tcl.commands import ConfigTclCommands
import logging
import os
import subprocess
import typing
from xviv.config.project import XvivConfig
from xviv.tools import vivado
from xviv.utils.fifo import _ensure_fifo, _fifo_send
from xviv.utils.fs import assert_file_exists, combined_checksum

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# simulate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_simulate(cfg: XvivConfig, *, sim_name: str, run: str | None):
	sim_cfg = cfg.get_sim(sim_name)

	if run is None:
		run = 'all'

	sim_files = []
	if sim_cfg.design:
		design_cfg = cfg.get_design(sim_cfg.design)

		sim_files += design_cfg.sources

	sim_files += sim_cfg.sources

	if sim_cfg.backend == 'xsim':
		xsim_lib  = "xv_work"
		vivado.run_vivado_xvlog(cfg, sim_cfg.work_dir, sim_files, xsim_lib=xsim_lib)
		vivado.run_vivado_xelab(cfg, sim_cfg.work_dir, sim_cfg.top, timescale=sim_cfg.timescale, xsim_lib=xsim_lib, run_all=(run == 'all'))

		if not (run == 'all'):
			x_simulate_tcl = f"""
				log_wave -recursive *
				run {run}
				exit
			"""

			vivado.run_vivado_xsim(cfg, sim_cfg.work_dir, x_simulate_tcl, top=sim_cfg.top, stats=True, nogui=True, popen=False)
	else:
		#! InvalidSimulationBackend
		raise RuntimeError(f'ERROR: invalid sim backend {sim_cfg.backend}')

# -----------------------------------------------------------------------------
# open --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_open(cfg: XvivConfig, *,
	sim_name: str,
	nogui: bool = False
):
	sim_cfg = cfg.get_sim(sim_name)

	wdb_file = os.path.join(sim_cfg.work_dir, f'{sim_cfg.top}.wdb')
	wcfg_file = os.path.join(sim_cfg.work_dir, f'{sim_cfg.top}.wcfg')
	fifo_file = os.path.join(sim_cfg.work_dir, f'{sim_cfg.top}.fifo')

	config = (
		ConfigTclCommands(cfg)
		.waveform_setup(
			wdb_file=wdb_file,
			top_name=sim_cfg.top,
			wcfg_file=wcfg_file,
			fifo_file=fifo_file
		)
		.build()
	)

	_ensure_fifo(fifo_file)

	pid = vivado.run_vivado_xsim(cfg, sim_cfg.work_dir, config_tcl=config, stats=False, wdb_file=wdb_file, nogui=nogui, popen=True)

	if pid is not None:
		logger.info("xsim waveform PID: %d", pid)
	else:
		logger.info("xsim waveform exited (blocking mode)")


# -----------------------------------------------------------------------------
# reload --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_reload(cfg: XvivConfig, *,
	sim_name: str
):
	sim_cfg = cfg.get_sim(sim_name)

	fifo_file = os.path.join(sim_cfg.work_dir, f'{sim_cfg.top}.fifo')
	
	assert_file_exists(fifo_file)

	cmd = (
		ConfigTclCommands(cfg)
		.waveform_reload()
		.build()
	)

	logger.info("Reloading waveform: %s", fifo_file)
	_fifo_send(fifo_file, cmd)