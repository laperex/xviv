import logging
import os

from xviv.config.model import UvmConfig
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools import verilator, vivado
from xviv.utils import error
from xviv.utils.fifo import _ensure_fifo, _fifo_send
from xviv.utils.fs import assert_file_exists

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #


def _build_uvm_plusargs(uvm_cfg: UvmConfig | None) -> list[str]:
	args: list[str] = []

	if uvm_cfg.test is not None:
		args.append(f"UVM_TESTNAME={uvm_cfg.test}")

	args.append(f"UVM_VERBOSITY={uvm_cfg.verbosity}")

	if uvm_cfg.max_quit_count is not None:
		args.append(f"UVM_MAX_QUIT_COUNT={uvm_cfg.max_quit_count}")

	return args


def _build_xsim_testplusargs(cfg: XvivConfig, sim_name: str, uvm_name: str | None) -> list[str]:
	sim_cfg = cfg.get_sim(sim_name)

	if uvm_name:
		args = _build_uvm_plusargs(cfg.get_uvm(uvm_name, sim_name))

	args += [a.lstrip("+") for a in sim_cfg.plusargs]
	return args


# --------------------------------------------------------------------------- #
#  simulate                                                                   #
# --------------------------------------------------------------------------- #


def cmd_simulate(
	cfg: XvivConfig,
	*,
	sim_name: str,
	uvm_name: str | None = None,
	run: str | None = None,
	mode: str = "default",
):
	sim_cfg = cfg.get_sim(sim_name)

	if run is None:
		run = "all"

	# -- Resolve source file lists --------------------------------------- #
	svlog_files: list[str] = []
	sdfmax_entries: list[str] = []
	sdfmin_entries: list[str] = []

	if sim_cfg.design:
		if mode == "default":
			design_cfg = cfg.get_design(sim_cfg.design)
			svlog_files += [i.file for i in design_cfg.sources]
		else:
			synth_cfg = cfg.get_synth(design_name=sim_cfg.design)

			match mode:
				case "post_synth_functional":
					assert_file_exists(synth_cfg.synth_functional_netlist_file)
					svlog_files.append(synth_cfg.synth_functional_netlist_file)

				case "post_synth_timing":
					assert_file_exists(synth_cfg.synth_timing_netlist_file)
					svlog_files.append(synth_cfg.synth_timing_netlist_file)

				case "post_impl_functional":
					assert_file_exists(synth_cfg.impl_functional_netlist_file)
					svlog_files.append(synth_cfg.impl_functional_netlist_file)

				case "post_impl_timing":
					assert_file_exists(synth_cfg.impl_timing_sdf_file)

					for s in sim_cfg.sdfmax:
						sdfmax_entries.append(f"{s}={synth_cfg.impl_timing_sdf_file}")

					for s in sim_cfg.sdfmin:
						sdfmin_entries.append(f"{s}={synth_cfg.impl_timing_sdf_file}")

					assert_file_exists(synth_cfg.impl_timing_netlist_file)
					svlog_files.append(synth_cfg.impl_timing_netlist_file)

				case _:
					raise error.InvalidSimulationMode(mode)

	svlog_files += [i.file for i in sim_cfg.sources]

	# -- Backend dispatch ------------------------------------------------ #
	match sim_cfg.backend:
		case "xsim":
			_run_xsim(cfg, sim_name, uvm_name, svlog_files, sdfmax_entries, sdfmin_entries, run)
		case "verilator":
			_run_verilator(cfg, sim_name, uvm_name, svlog_files)
		case _:
			raise error.InvalidSimulationBackend(sim_cfg.backend)


# --------------------------------------------------------------------------- #
#  xsim backend (private)                                                    #
# --------------------------------------------------------------------------- #


def _run_xsim(
	cfg: XvivConfig,
	sim_name: str,
	uvm_name: str | None,
	svlog_files: list[str],
	sdfmax_entries: list[str],
	sdfmin_entries: list[str],
	run: str,
):
	sim_cfg = cfg.get_sim(sim_name)

	top = sim_cfg.top
	timescale = sim_cfg.timescale
	uvm_version = None

	if uvm_name:
		uvm_cfg = cfg.get_uvm(uvm_name, sim_name)

		top = uvm_cfg.top
		timescale = uvm_cfg.timescale
		uvm_version = uvm_cfg.version

	xsim_lib = "xv_work"

	# -- 1. xvlog - compile source files ------------------------------- #
	vivado.run_vivado_xvlog(
		cfg,
		sim_cfg.work_dir,
		svlog_files,
		lib=filter(None, ["uvm" if uvm_name else None]),
		xsim_lib=xsim_lib,
		defines=sim_cfg.defines,
		include_dirs=sim_cfg.include_dirs,
	)

	# -- 2. xelab - elaborate ------------------------------------------- #
	elab_libs = ["secureip", "unimacro_ver", "unisims_ver"]
	if uvm_name:
		elab_libs.append("uvm")

	vivado.run_vivado_xelab(
		cfg,
		sim_cfg.work_dir,
		[f"{xsim_lib}.{top}", f"{xsim_lib}.glbl"],
		timescale=timescale,
		mt=str(20),
		snapshot=top,
		lib=elab_libs,
		debug="typical",
		incr=True,
		runall=(run == "all") and not uvm_name,
		# svlog=svlog_files,
		sdfmax=sdfmax_entries[0] if sdfmax_entries else None,
		uvm_version=uvm_version,
	)

	# -- 3. xsim - simulate --------------------------------------------- #
	if not (run == "all") or uvm_name:
		x_simulate_tcl = filter(
			None,
			[
				"log_wave -recursive *",
				f"run {run}",
				"exit",
			],
		)

		vivado.run_vivado_xsim(
			cfg,
			target_dir=sim_cfg.work_dir,
			config_tcl="\n".join(x_simulate_tcl),
			top=top,
			stats=True,
			nogui=True,
			popen=False,
			testplusarg=_build_xsim_testplusargs(cfg, sim_name, uvm_name),
			runall=False,
		)


# --------------------------------------------------------------------------- #
#  verilator backend (private)                                                #
# --------------------------------------------------------------------------- #


def _run_verilator(cfg: XvivConfig, sim_name: str, uvm_name: str | None, svlog_files):
	sim_cfg = cfg.get_sim(sim_name)

	top = sim_cfg.top
	timescale = sim_cfg.timescale
	uvm_test = None
	uvm_verbosity = sim_cfg.uvm_verbosity
	uvm_max_quit_count = sim_cfg.uvm_max_quit_count

	if uvm_name:
		uvm_cfg = cfg.get_uvm(uvm_name, sim_name)
		top = uvm_cfg.top
		timescale = uvm_cfg.timescale

		uvm_test = uvm_cfg.test
		uvm_verbosity = uvm_cfg.uvm_verbosity
		uvm_max_quit_count = uvm_cfg.uvm_max_quit_count

	# -- 1. Compile ----------------------------------------------------- #
	include_dirs = list(sim_cfg.include_dirs)
	if uvm_name and sim_cfg.uvm_pkg_dir is not None:
		include_dirs.insert(0, sim_cfg.uvm_pkg_dir)

	binary = verilator.run_verilator_compile(
		work_dir=sim_cfg.work_dir,
		fileset=svlog_files,
		top=top,
		defines=sim_cfg.defines,
		include_dirs=include_dirs,
		timescale=timescale,
		threads=sim_cfg.threads,
		trace=sim_cfg.trace,
		trace_fst=sim_cfg.trace_fst,
		trace_depth=sim_cfg.trace_depth,
		uvm=uvm_name is not None,
		uvm_pkg_dir=sim_cfg.uvm_pkg_dir,
		extra_args=sim_cfg.verilator_args,
		dry_run=cfg.get_vivado().dry_run,
	)

	# -- 2. Simulate ---------------------------------------------------- #
	verilator.run_verilator_sim(
		binary=binary,
		work_dir=sim_cfg.work_dir,
		plusargs=sim_cfg.plusargs,
		uvm=uvm_name is not None,
		uvm_test=uvm_test,
		uvm_verbosity=uvm_verbosity,
		uvm_max_quit_count=uvm_max_quit_count,
		trace=sim_cfg.trace,
		trace_fst=sim_cfg.trace_fst,
		dry_run=cfg.get_vivado().dry_run,
	)


# --------------------------------------------------------------------------- #
#  open --wdb --top <top_name>                                               #
# --------------------------------------------------------------------------- #


def cmd_wdb_open(cfg: XvivConfig, *, sim_name: str, nogui: bool = False):
	sim_cfg = cfg.get_sim(sim_name)

	wdb_file = os.path.join(sim_cfg.work_dir, f"{sim_cfg.top}.wdb")
	wcfg_file = os.path.join(sim_cfg.work_dir, f"{sim_cfg.top}.wcfg")
	fifo_file = os.path.join(sim_cfg.work_dir, f"{sim_cfg.top}.fifo")

	config = (
		ConfigTclCommands(cfg)
		.waveform_setup(wdb_file=wdb_file, top_name=sim_cfg.top, wcfg_file=wcfg_file, fifo_file=fifo_file)
		.build()
	)

	_ensure_fifo(fifo_file)

	pid = vivado.run_vivado_xsim(
		cfg, target_dir=sim_cfg.work_dir, config_tcl=config, stats=False, wdb_file=wdb_file, nogui=nogui, popen=True
	)

	if pid is not None:
		logger.info("xsim waveform PID: %d", pid)
	else:
		logger.info("xsim waveform exited (blocking mode)")


# --------------------------------------------------------------------------- #
#  reload --wdb --top <top_name>                                             #
# --------------------------------------------------------------------------- #


def cmd_wdb_reload(cfg: XvivConfig, *, sim_name: str):
	sim_cfg = cfg.get_sim(sim_name)

	fifo_file = os.path.join(sim_cfg.work_dir, f"{sim_cfg.top}.fifo")

	assert_file_exists(fifo_file)

	cmd = ConfigTclCommands(cfg).waveform_reload().build()

	logger.info("Reloading waveform: %s", fifo_file)
	_fifo_send(fifo_file, cmd)
