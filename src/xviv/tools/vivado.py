import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from xviv.config.project import XvivConfig
from xviv.utils.process import run_tool

logger = logging.getLogger(__name__)


def run_vivado_xvlog(
	cfg: XvivConfig,
	target_dir: str,
	fileset: list[str],
	xsim_lib: str,
	*,
	lib: list[str] | None = None,
	defines: list[str] = [],
	include_dirs: list[str] = [],
) -> None:
	xvlog_bin = os.path.join(cfg.get_vivado().path, "bin", "xvlog")
	extra_files = [os.path.join(cfg.get_vivado().path, "data/verilog/src/glbl.v")]

	cmd = [xvlog_bin, "--sv", "--incr", "--work", xsim_lib]

	for d in defines:
		cmd += ["-d", d]
	for i in include_dirs:
		cmd += ["-i", i]
	for x in lib or []:
		cmd += ["-L", x]

	cmd += fileset
	cmd += extra_files

	try:
		run_tool(cmd, cwd=target_dir, dry_run=cfg.get_vivado().dry_run)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)


def run_vivado_xelab(
	cfg: XvivConfig,
	target_dir: str,
	units: list[str],
	*,
	debug: str = "off",
	incr: bool = False,
	run: bool = False,
	runall: bool = False,
	standalone: bool = False,
	relax: bool = False,
	nolog: bool = False,
	stats: bool = False,
	override_timeunit: bool = False,
	override_timeprecision: bool = False,
	noname_unnamed_generate: bool = False,
	rangecheck: bool = False,
	transform_timing_checkers: bool = False,
	suppress_localparam_override_error: bool = False,
	ignore_assertions: bool = False,
	report_assertion_pass: bool = False,
	ignore_coverage: bool = False,
	maxdelay: bool = False,
	mindelay: bool = False,
	typdelay: bool = False,
	nosdfinterconnectdelays: bool = False,
	nospecify: bool = False,
	notimingchecks: bool = False,
	transport_int_delays: bool = False,
	sdfnoerror: bool = False,
	sdfnowarn: bool = False,
	dup_entity_as_module: bool = False,
	dpi_absolute: bool = False,
	cc_celldefines: bool = False,
	cc_libs: bool = False,
	O0: bool = False,
	file: str | None = None,
	log: str | None = None,
	initfile: str | None = None,
	mt: str | None = None,
	snapshot: str | None = None,
	timescale: str | None = None,
	uvm_version: str | None = None,
	ccExclusionFile: str | None = None,
	prj: str | None = None,
	timeprecision_vhdl: str | None = None,
	sdfmax: str | None = None,
	sdfmin: str | None = None,
	sdftyp: str | None = None,
	sdfroot: str | None = None,
	pulse_e_style: str | None = None,
	dpiheader: str | None = None,
	dpi_stacksize: str | None = None,
	sc_lib: str | None = None,
	sv_lib: str | None = None,
	sv_liblist: str | None = None,
	sc_root: str | None = None,
	sv_root: str | None = None,
	cov_db_dir: str | None = None,
	cov_db_name: str | None = None,
	cc_type: str | None = None,
	verbose: int | None = None,
	maxarraysize: int | None = None,
	maxdesigndepth: int | None = None,
	driver_display_limit: int | None = None,
	pulse_int_e: int | None = None,
	pulse_int_r: int | None = None,
	pulse_e: int | None = None,
	pulse_r: int | None = None,
	define: list[str] | None = None,
	lib: list[str] | None = None,
	include: list[str] | None = None,
	svlog: list[str] | None = None,
	vlog: list[str] | None = None,
	vhdl: list[str] | None = None,
	vhdl2008: list[str] | None = None,
	vhdl2019: list[str] | None = None,
	generic_top: list[str] | None = None,
	sourcelibdir: list[str] | None = None,
	sourcelibext: list[str] | None = None,
	sourcelibfile: list[str] | None = None,
) -> None:
	cmd = [os.path.join(cfg.get_vivado().path, "bin", "xelab"), *units]

	cmd += ["--debug", debug]

	# Boolean flags
	if standalone:
		cmd += ["--standalone"]
	if run:
		cmd += ["--run"]
	if runall:
		cmd += ["--runall"]
	if incr:
		cmd += ["--incr"]
	if relax:
		cmd += ["--relax"]
	if nolog:
		cmd += ["--nolog"]
	if stats:
		cmd += ["--stats"]
	if override_timeunit:
		cmd += ["--override_timeunit"]
	if override_timeprecision:
		cmd += ["--override_timeprecision"]
	if noname_unnamed_generate:
		cmd += ["--noname_unnamed_generate"]
	if rangecheck:
		cmd += ["--rangecheck"]
	if transform_timing_checkers:
		cmd += ["--transform_timing_checkers"]
	if suppress_localparam_override_error:
		cmd += ["--suppress_localparam_override_error"]
	if ignore_assertions:
		cmd += ["--ignore_assertions"]
	if report_assertion_pass:
		cmd += ["--report_assertion_pass"]
	if ignore_coverage:
		cmd += ["--ignore_coverage"]
	if nosdfinterconnectdelays:
		cmd += ["--nosdfinterconnectdelays"]
	if nospecify:
		cmd += ["--nospecify"]
	if notimingchecks:
		cmd += ["--notimingchecks"]
	if mindelay:
		cmd += ["--mindelay"]
	if maxdelay:
		cmd += ["--maxdelay"]
	if typdelay:
		cmd += ["--typdelay"]
	if transport_int_delays:
		cmd += ["--transport_int_delays"]
	if sdfnoerror:
		cmd += ["--sdfnoerror"]
	if sdfnowarn:
		cmd += ["--sdfnowarn"]
	if dup_entity_as_module:
		cmd += ["--dup_entity_as_module"]
	if dpi_absolute:
		cmd += ["--dpi_absolute"]
	if cc_celldefines:
		cmd += ["--cc_celldefines"]
	if cc_libs:
		cmd += ["--cc_libs"]
	if O0:
		cmd += ["--O0"]

	# String options
	if file:
		cmd += ["--file", file]
	if log:
		cmd += ["--log", log]
	if prj:
		cmd += ["--prj", prj]
	if initfile:
		cmd += ["--initfile", initfile]
	if ccExclusionFile:
		cmd += ["--ccExclusionFile", ccExclusionFile]
	if uvm_version:
		cmd += ["--uvm_version", uvm_version]
	if timescale:
		cmd += ["--timescale", timescale]
	if timeprecision_vhdl:
		cmd += ["--timeprecision_vhdl", timeprecision_vhdl]
	if snapshot:
		cmd += ["--snapshot", snapshot]
	if mt:
		cmd += ["--mt", mt]
	if pulse_e_style:
		cmd += ["--pulse_e_style", pulse_e_style]
	if sdfmax:
		cmd += ["--sdfmax", sdfmax]
	if sdfmin:
		cmd += ["--sdfmin", sdfmin]
	if sdftyp:
		cmd += ["--sdftyp", sdftyp]
	if sdfroot:
		cmd += ["--sdfroot", sdfroot]
	if dpiheader:
		cmd += ["--dpiheader", dpiheader]
	if dpi_stacksize:
		cmd += ["--dpi_stacksize", dpi_stacksize]
	if sc_lib:
		cmd += ["--sc_lib", sc_lib]
	if sv_lib:
		cmd += ["--sv_lib", sv_lib]
	if sv_liblist:
		cmd += ["--sv_liblist", sv_liblist]
	if sc_root:
		cmd += ["--sc_root", sc_root]
	if sv_root:
		cmd += ["--sv_root", sv_root]
	if cov_db_dir:
		cmd += ["--cov_db_dir", cov_db_dir]
	if cov_db_name:
		cmd += ["--cov_db_name", cov_db_name]
	if cc_type:
		cmd += ["--cc_type", cc_type]

	# Integer options
	if verbose is not None:
		cmd += ["--verbose", str(verbose)]
	if maxarraysize is not None:
		cmd += ["--maxarraysize", str(maxarraysize)]
	if maxdesigndepth is not None:
		cmd += ["--maxdesigndepth", str(maxdesigndepth)]
	if driver_display_limit is not None:
		cmd += ["--driver_display_limit", str(driver_display_limit)]
	if pulse_int_e is not None:
		cmd += ["--pulse_int_e", str(pulse_int_e)]
	if pulse_int_r is not None:
		cmd += ["--pulse_int_r", str(pulse_int_r)]
	if pulse_e is not None:
		cmd += ["--pulse_e", str(pulse_e)]
	if pulse_r is not None:
		cmd += ["--pulse_r", str(pulse_r)]

	# Repeatable options
	for x in lib or []:
		cmd += ["-L", x]
	for x in define or []:
		cmd += ["-d", x]
	for x in svlog or []:
		cmd += ["--svlog", x]
	for x in vlog or []:
		cmd += ["--vlog", x]
	for x in vhdl or []:
		cmd += ["--vhdl", x]
	for x in vhdl2008 or []:
		cmd += ["--vhdl2008", x]
	for x in vhdl2019 or []:
		cmd += ["--vhdl2019", x]
	for x in include or []:
		cmd += ["-i", x]
	for x in generic_top or []:
		cmd += ["--generic_top", x]
	for x in sourcelibdir or []:
		cmd += ["--sourcelibdir", x]
	for x in sourcelibext or []:
		cmd += ["--sourcelibext", x]
	for x in sourcelibfile or []:
		cmd += ["--sourcelibfile", x]

	try:
		run_tool(cmd, cwd=target_dir, dry_run=cfg.get_vivado().dry_run)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)


def run_vivado_xsim(
	cfg: XvivConfig,
	*,
	target_dir: str,
	config_tcl: str | None,
	top: str | None = None,
	wdb_file: str | None = None,
	stats: bool = True,
	nogui: bool = False,
	runall: bool = False,
	popen: bool = False,
	testplusarg: list[str] | None = None,
) -> int | None:
	if config_tcl is None:
		return None

	xsim_bin = os.path.join(cfg.get_vivado().path, "bin", "xsim")
	config_tcl_path: str | None = None

	try:
		with tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_") as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		cmd = [xsim_bin]

		if top:
			cmd += [top]
		if wdb_file:
			cmd += ["--wdb", wdb_file]
		if stats:
			cmd += ["--stats"]
		if not nogui:
			cmd += ["-g"]
		if runall:
			cmd += ["--runall"]

		cmd += ["-t", config_tcl_path]

		for x in testplusarg or []:
			cmd += ["--testplusarg", x]

		try:
			return run_tool(cmd, cwd=target_dir, dry_run=cfg.get_vivado().dry_run, popen=popen)
		except subprocess.CalledProcessError as e:
			sys.exit(e.returncode)

	finally:
		if config_tcl_path and not cfg.get_vivado().dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)


def run_vivado(
	cfg: XvivConfig,
	*,
	config_tcl: str | None,
	label: str | None = None,
	log_dir: str | None = None,
) -> None:
	if config_tcl is None:
		return

	vivado_bin = os.path.join(cfg.get_vivado().path, "bin", "vivado")
	job_log = logger.getChild(label) if label else logger
	config_tcl_path: str | None = None

	try:
		with tempfile.NamedTemporaryFile(
			mode="w", suffix="_config.tcl", delete=False, prefix=f"xviv_{label or ''}_"
		) as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		cmd = [
			vivado_bin,
			"-mode",
			cfg.get_vivado().mode,
			"-nolog",
			"-nojournal",
			"-notrace",
			"-quiet",
			"-source",
			config_tcl_path,
		]

		is_tcl = cfg.get_vivado().mode == "tcl"
		log_path: Path | None = None
		if not is_tcl:
			log_stem = label or "vivado"
			log_path = Path(log_dir or cfg.work_dir) / f"{log_stem}.log"

		try:
			run_tool(
				cmd,
				cwd=cfg.work_dir,
				log=job_log,
				log_path=log_path,
				interactive=is_tcl,
				dry_run=cfg.get_vivado().dry_run,
			)
		except subprocess.CalledProcessError as e:
			job_log.error("Vivado exited with code %d", e.returncode)
			sys.exit(e.returncode)

	finally:
		if config_tcl_path and not cfg.get_vivado().dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)
