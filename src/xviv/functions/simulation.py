from xviv.generator.tcl.commands import ConfigTclCommands
import logging
import os
import subprocess
import typing
from xviv.config.project import XvivConfig
from xviv.tools import vivado
from xviv.utils.fifo import _ensure_fifo, _fifo_send
from xviv.utils.fs import combined_checksum

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# simulate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_top_simulate(cfg: XvivConfig, sim_name: str, run: str = "all"):
	sim_cfg = cfg.get_sim(sim_name)

	sim_files = []
	
	if sim_cfg.design:
		design_cfg = cfg.get_design(sim_cfg.design)

		sim_files += design_cfg.sources

	sim_files += sim_cfg.sources
	
	# print(combined_checksum(sim_files))

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

			vivado.run_vivado_xsim(cfg, sim_cfg.work_dir, sim_cfg.top, x_simulate_tcl)
	else:
		#! InvalidSimulationBackend
		raise RuntimeError(f'ERROR: invalid sim backend {sim_cfg.backend}')

# WAVEFORM

_XSIM_WDB_TCL = """
set xsi_sim_wdb_file  {wdb}
set xsi_sim_wcfg_file {wcfg}
set xviv_fifo_path    {fifo_path}
set xviv_ready        0

if {{[file exists $xsi_sim_wcfg_file]}} {{
	catch {{open_wave_config $xsi_sim_wcfg_file}}
}} else {{
	add_wave {top}
	save_wave_config $xsi_sim_wcfg_file
}}

set xviv_ready 1

set xviv_fifo_fh [open $xviv_fifo_path r+]
fconfigure $xviv_fifo_fh -blocking 0 -buffering line

proc _fifo_reopen {{}} {{
	global xviv_fifo_fh xviv_fifo_path
	catch {{close $xviv_fifo_fh}}
	set xviv_fifo_fh [open $xviv_fifo_path r+]
	fconfigure $xviv_fifo_fh -blocking 0 -buffering line
	fileevent  $xviv_fifo_fh readable _fifo_handle
}}

proc _fifo_handle {{}} {{
	global xviv_fifo_fh xviv_ready
	if {{!$xviv_ready}} {{ return }}

	if {{[eof $xviv_fifo_fh]}} {{
		fileevent $xviv_fifo_fh readable {{}}
		_fifo_reopen
		return
	}}

	set len [gets $xviv_fifo_fh cmd]
	if {{$len <= 0}} {{ return }}

	puts "xviv: $cmd"
	catch {{uplevel #0 $cmd}} result
	puts "xviv: -> $result"
}}

fileevent $xviv_fifo_fh readable _fifo_handle
puts "xviv: FIFO ready at $xviv_fifo_path"
"""

# -----------------------------------------------------------------------------
# open --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_open(cfg: XvivConfig, top_name: str, nogui: bool = False):
	wdb_file  = f"/home/laperex/Programming/image_processing/build/test_sim_wdb/{top_name}.wdb"
	wcfg_file = f"/home/laperex/Programming/image_processing/build/test_sim_wdb/{top_name}.wcfg"
	fifo_file = f"/home/laperex/Programming/image_processing/build/test_sim_wdb/{top_name}.fifo"
	
	config = (
		ConfigTclCommands(cfg)
		.xsim_wdb(
			wdb_file=wdb_file,
			top_name=top_name,
			wcfg_file=wcfg_file,
			fifo_file=fifo_file
		)
		.build()
	)
	
	print(config)
	
	# xsim_bin = os.path.join(cfg.vivado.path, "bin", "xsim")
	# xlib_work_dir = cfg.get_xlib_work_dir(top_name)

	# tcl_file  = os.path.join(xlib_work_dir, "waveform_config.tcl")

	# os.makedirs(xlib_work_dir, exist_ok=True)
	# fifo = cfg.get_control_fifo_path(top_name)
	# _ensure_fifo(fifo)

	# with open(tcl_file, "w") as f:
	# 	f.write(
	# 	_XSIM_WDB_TCL.format(wdb=wdb_file, wcfg=wcfg_file, top=top_name, fifo_path=fifo)
	# )

	# proc = subprocess.Popen(
	# 	[xsim_bin, wdb_file, "-t", tcl_file, "" if nogui else "-g"],
	# 	cwd=xlib_work_dir,
	# )
	# logger.info("xsim waveform PID: %d", proc.pid)


# -----------------------------------------------------------------------------
# reload --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_reload(cfg: XvivConfig, top_name: str):
	path = cfg.get_control_fifo_path(top_name)
	cmd = (
		"after 300 {"
			"\tset _wcfg [get_property FILE_PATH [current_wave_config]]; "
			"\tsave_wave_config [current_wave_config];"
			"\tclose_wave_config [current_wave_config];"
			"\topen_wave_database $xsi_sim_wdb_file; "
			"\tcatch {open_wave_config $_wcfg}"
		"}"
	)
	logger.info("Reloading waveform: %s", path)
	_fifo_send(path, cmd)