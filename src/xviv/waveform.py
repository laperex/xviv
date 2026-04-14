import logging
import os
import stat
import subprocess

from xviv.config import ProjectConfig

logger = logging.getLogger(__name__)

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

def _ensure_fifo(path: str) -> None:
	if os.path.exists(path):
		if not stat.S_ISFIFO(os.stat(path).st_mode):
			os.unlink(path)
			os.mkfifo(path)
	else:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		os.mkfifo(path)


def _fifo_send(path: str, command: str) -> None:
	try:
		fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
		with os.fdopen(fd, "w") as fh:
			fh.write(command + "\n")
	except OSError as e:
		logger.warning("FIFO send failed (%s) - is xsim running?", e)


def reload_wdb(cfg: ProjectConfig, top_name: str) -> None:
	path = cfg.get_control_fifo_path(top_name)
	cmd = (
		"after 300 {"
		"set _wcfg [get_property FILE_PATH [current_wave_config]]; "
		"save_wave_config [current_wave_config];"
		"close_wave_config [current_wave_config];"
		"open_wave_database $xsi_sim_wdb_file; "
		"catch {open_wave_config $_wcfg}"
		"}"
	)
	logger.info("Reloading waveform: %s", path)
	_fifo_send(path, cmd)


def reload_snapshot(cfg: ProjectConfig, top_name: str) -> None:
	path = cfg.get_control_fifo_path(top_name)
	cmd = (
		"set _wcfg [get_property FILE_PATH [current_wave_config]]; "
		"save_wave_config $_wcfg; "
		f"xsim {top_name};"
		"log_wave -recursive *; "
		"run all; "
		"open_wave_config $_wcfg"
	)
	logger.info("Reloading snapshot: %s", path)
	_fifo_send(path, cmd)


def open_wdb(cfg: ProjectConfig, top_name: str) -> None:
	xsim_bin = os.path.join(cfg.vivado.path, "bin", "xsim")
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)

	wdb_file  = "waveform.wdb"
	wcfg_file = "waveform.wcfg"
	tcl_file  = os.path.join(xlib_work_dir, "waveform_config.tcl")

	os.makedirs(xlib_work_dir, exist_ok=True)
	fifo = cfg.get_control_fifo_path(top_name)
	_ensure_fifo(fifo)

	open(tcl_file, "w").write(
		_XSIM_WDB_TCL.format(wdb=wdb_file, wcfg=wcfg_file, top=top_name, fifo_path=fifo)
	)

	proc = subprocess.Popen(
		[xsim_bin, wdb_file, "-t", tcl_file, "-g"],
		cwd=xlib_work_dir,
	)
	logger.info("xsim waveform PID: %d", proc.pid)


def open_snapshot(cfg: ProjectConfig, top_name: str) -> None:
	xsim_bin = os.path.join(cfg.vivado.path, "bin", "xsim")
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)

	wdb_file  = os.path.join(xlib_work_dir, "waveform.wdb")
	wcfg_file = os.path.join(xlib_work_dir, "waveform.wcfg")
	tcl_file  = os.path.join(xlib_work_dir, "waveform_config.tcl")

	os.makedirs(xlib_work_dir, exist_ok=True)
	control_fifo_path = cfg.get_control_fifo_path(top_name)
	_ensure_fifo(control_fifo_path)

	open(tcl_file, "w").write(
		_XSIM_WDB_TCL.format(
			wdb=wdb_file, wcfg=wcfg_file,
			top=top_name, fifo_path=control_fifo_path,
		)
	)

	proc = subprocess.Popen(
		[xsim_bin, top_name, "-t", tcl_file, "-g"],
		cwd=xlib_work_dir,
	)
	logger.info("xsim waveform PID: %d", proc.pid)