# functions/simulation.py
#
# Three backends are supported:
#   xsim      - Vivado's xvlog/xelab/xsim toolchain  (with optional UVM)
#   verilator - open-source verilator --binary flow    (with optional UVM)
#
# UVM / xsim
# ----------
# Vivado ships UVM 1.1d and 1.2 pre-compiled under
# $XILINX_VIVADO/data/system_verilog/uvm/<version>/.
# xvlog does not need extra flags for the pre-compiled library.
# xelab links it via -L uvm and --uvm_version.
# xsim receives UVM plusargs on the command line (--testplusarg).
#
# UVM / verilator
# ---------------
# Verilator does not ship a pre-compiled UVM library.  The user must
# include UVM source files in `sources` or point `uvm_pkg_dir` at a
# verilator-compatible UVM root (e.g. antmicro/verilator-uvm).

from xviv.config.model import SimulationConfig
from xviv.generator.tcl.commands import ConfigTclCommands
import logging
import os
import subprocess
import typing
from xviv.config.project import XvivConfig
from xviv.tools import verilator, vivado
# from xviv.tools import verilator as verilator_tool
from xviv.utils import error
from xviv.utils.fifo import _ensure_fifo, _fifo_send
from xviv.utils.fs import assert_file_exists, combined_checksum

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #

def _build_uvm_plusargs(sim_cfg) -> list[str]:
	"""Collect the standard UVM CLI plusargs from a SimulationConfig."""
	args: list[str] = []
	if sim_cfg.uvm:
		if sim_cfg.uvm_test is not None:
			args.append(f"UVM_TESTNAME={sim_cfg.uvm_test}")
		args.append(f"UVM_VERBOSITY={sim_cfg.uvm_verbosity}")
		if sim_cfg.uvm_max_quit_count is not None:
			args.append(f"UVM_MAX_QUIT_COUNT={sim_cfg.uvm_max_quit_count}")
	return args


def _build_xsim_testplusargs(sim_cfg) -> list[str]:
	"""All plusargs for xsim: UVM standard args + user-defined plusargs."""
	args = _build_uvm_plusargs(sim_cfg)
	# User plusargs are stored without leading '+' in the config;
	# strip any accidental '+' prefix for uniform handling.
	args += [a.lstrip("+") for a in sim_cfg.plusargs]
	return args


# --------------------------------------------------------------------------- #
#  simulate                                                                   #
# --------------------------------------------------------------------------- #

def cmd_simulate(cfg: XvivConfig, *,
	sim_name: str,
	run: str | None,
	mode: str = 'default',
	dry_run: bool = False,
):
	sim_cfg = cfg.get_sim(sim_name)

	if run is None:
		run = 'all'

	# -- Resolve source file lists --------------------------------------- #
	svlog_files: list[str] = []
	sdfmax_entries: list[str] = []
	sdfmin_entries: list[str] = []

	if sim_cfg.design:
		if mode == 'default':
			design_cfg = cfg.get_design(sim_cfg.design)
			svlog_files += [i.file for i in design_cfg.sources]
		else:
			synth_cfg = cfg.get_synth(design_name=sim_cfg.design)

			match mode:
				case 'post_synth_functional':
					assert_file_exists(synth_cfg.synth_functional_netlist_file)
					svlog_files.append(synth_cfg.synth_functional_netlist_file)

				case 'post_synth_timing':
					assert_file_exists(synth_cfg.synth_timing_netlist_file)
					svlog_files.append(synth_cfg.synth_timing_netlist_file)

				case 'post_impl_functional':
					assert_file_exists(synth_cfg.impl_functional_netlist_file)
					svlog_files.append(synth_cfg.impl_functional_netlist_file)

				case 'post_impl_timing':
					assert_file_exists(synth_cfg.impl_timing_sdf_file)

					for s in sim_cfg.sdfmax:
						sdfmax_entries.append(f'{s}={synth_cfg.impl_timing_sdf_file}')

					for s in sim_cfg.sdfmin:
						sdfmin_entries.append(f'{s}={synth_cfg.impl_timing_sdf_file}')

					assert_file_exists(synth_cfg.impl_timing_netlist_file)
					svlog_files.append(synth_cfg.impl_timing_netlist_file)

				case _:
					raise error.InvalidSimulationMode(mode)

	svlog_files += [i.file for i in sim_cfg.sources]

	# -- Backend dispatch ------------------------------------------------ #
	match sim_cfg.backend:
		case 'xsim':
			_run_xsim(cfg, sim_cfg, svlog_files, sdfmax_entries, sdfmin_entries, run, dry_run)
		case 'verilator':
			_run_verilator(cfg, sim_cfg, svlog_files, dry_run)
		case _:
			raise error.InvalidSimulationBackend(sim_cfg.backend)


# --------------------------------------------------------------------------- #
#  xsim backend (private)                                                    #
# --------------------------------------------------------------------------- #

def _run_xsim(cfg: XvivConfig, sim_cfg: SimulationConfig, svlog_files, sdfmax_entries, sdfmin_entries, run, dry_run):
	"""
	xvlog → xelab → xsim pipeline with full UVM support.

	UVM library:
	Vivado pre-compiles UVM.  xvlog does not need extra -L flags.
	xelab links it with -L uvm and --uvm_version.
	xsim receives UVM plusargs via --testplusarg on the CLI.
	"""
	xsim_lib = "xv_work"

	# -- 1. xvlog - compile source files ------------------------------- #
	vivado.run_vivado_xvlog(
		cfg,
		sim_cfg.work_dir,
		svlog_files,
		lib=filter(None, [
			"uvm" if sim_cfg.uvm else None
		]),
		xsim_lib=xsim_lib,
		defines=sim_cfg.defines,
		include_dirs=sim_cfg.include_dirs,
	)

	# -- 2. xelab - elaborate ------------------------------------------- #
	elab_libs = ['secureip', 'unimacro_ver', 'unisims_ver']
	if sim_cfg.uvm:
		elab_libs.append('uvm')

	vivado.run_vivado_xelab(
		cfg,
		sim_cfg.work_dir,
		[f'{xsim_lib}.{sim_cfg.top}', f'{xsim_lib}.glbl'],
		timescale=sim_cfg.timescale,
		mt=str(20),
		snapshot=sim_cfg.top,
		lib=elab_libs,
		debug='typical',
		incr=True,
		runall=(run == 'all') and not sim_cfg.uvm,
		# svlog=svlog_files,
		sdfmax=sdfmax_entries[0] if sdfmax_entries else None,
		uvm_version=sim_cfg.uvm_version if sim_cfg.uvm else None,
	)

	# -- 3. xsim - simulate --------------------------------------------- #
	if not (run == 'all') or sim_cfg.uvm:
		x_simulate_tcl = filter(None, [
			"log_wave -recursive *",
			f"run {run}",
			"exit",
		])

		vivado.run_vivado_xsim(
			cfg,
			sim_cfg.work_dir,
			'\n'.join(x_simulate_tcl),
			top=sim_cfg.top,
			stats=True,
			nogui=True,
			popen=False,
			testplusarg=_build_xsim_testplusargs(sim_cfg),
			runall=False
		)


# --------------------------------------------------------------------------- #
#  verilator backend (private)                                               #
# --------------------------------------------------------------------------- #

def _run_verilator(cfg: XvivConfig, sim_cfg: SimulationConfig, svlog_files, dry_run):
	"""
	Verilator --binary flow: compile then execute.

	UVM with verilator requires either:
	a) UVM source files included in sim_cfg.sources, OR
	b) sim_cfg.uvm_pkg_dir pointing at a verilator-compatible UVM root.
	"""
	# -- 1. Compile ----------------------------------------------------- #
	include_dirs = list(sim_cfg.include_dirs)
	if sim_cfg.uvm and sim_cfg.uvm_pkg_dir is not None:
		include_dirs.insert(0, sim_cfg.uvm_pkg_dir)

	binary = verilator.run_verilator_compile(
		work_dir=sim_cfg.work_dir,
		fileset=svlog_files,
		top=sim_cfg.top,
		defines=sim_cfg.defines,
		include_dirs=include_dirs,
		timescale=sim_cfg.timescale,
		threads=sim_cfg.threads,
		trace=sim_cfg.trace,
		trace_fst=sim_cfg.trace_fst,
		trace_depth=sim_cfg.trace_depth,
		uvm=sim_cfg.uvm,
		uvm_pkg_dir=sim_cfg.uvm_pkg_dir,
		extra_args=sim_cfg.verilator_args,
		dry_run=dry_run,
	)

	# -- 2. Simulate ---------------------------------------------------- #
	verilator.run_verilator_sim(
		binary=binary,
		work_dir=sim_cfg.work_dir,
		plusargs=sim_cfg.plusargs,
		uvm=sim_cfg.uvm,
		uvm_test=sim_cfg.uvm_test,
		uvm_verbosity=sim_cfg.uvm_verbosity,
		uvm_max_quit_count=sim_cfg.uvm_max_quit_count,
		trace=sim_cfg.trace,
		trace_fst=sim_cfg.trace_fst,
		dry_run=dry_run,
	)


# --------------------------------------------------------------------------- #
#  open --wdb --top <top_name>                                               #
# --------------------------------------------------------------------------- #

def cmd_wdb_open(cfg: XvivConfig, *,
	sim_name: str,
	nogui: bool = False
):
	sim_cfg = cfg.get_sim(sim_name)

	wdb_file  = os.path.join(sim_cfg.work_dir, f'{sim_cfg.top}.wdb')
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

	pid = vivado.run_vivado_xsim(
		cfg, sim_cfg.work_dir,
		config_tcl=config,
		stats=False,
		wdb_file=wdb_file,
		nogui=nogui,
		popen=True
	)

	if pid is not None:
		logger.info("xsim waveform PID: %d", pid)
	else:
		logger.info("xsim waveform exited (blocking mode)")


# --------------------------------------------------------------------------- #
#  reload --wdb --top <top_name>                                             #
# --------------------------------------------------------------------------- #

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