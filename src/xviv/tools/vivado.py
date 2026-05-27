import contextlib
import logging
import os
import tempfile

# from pathlib import Path
from xviv.config.project import XvivConfig
from xviv.utils.process import run_tool
from xviv.utils.tools import find_vivado_dir_path

logger = logging.getLogger(__name__)


def run_vivado_xvlog(
	cfg: XvivConfig,
	target_dir: str,
	fileset: list[str],
	xsim_lib: str,
	*,
	label: str,
	lib: list[str] | None = None,
	defines: list[str] = [],
	include_dirs: list[str] = [],
) -> None:
	# if cfg.get_vivado().path:
	# 	extra_files = [os.path.join(cfg.get_vivado().path, "data/verilog/src/glbl.v")]

	cmd = [cfg.get_vivado().xvlog_bin, "--sv", "--incr", "--work", xsim_lib]

	for d in defines:
		cmd += ["-d", d]
	for i in include_dirs:
		cmd += ["-i", i]
	for x in lib or []:
		cmd += ["-L", x]

	cmd += fileset

	if cfg.get_vivado().glbl_file:
		cmd += [cfg.get_vivado().glbl_file]

	try:
		run_tool(
			cmd,
			cwd=target_dir,
			label=f"{__name__}_{label}",
			log_dir=cfg.log_dir,
			dry_run=cfg.dry_run,
			exit_on_fail=True,
		)
	except FileNotFoundError:
		try:
			find_vivado_dir_path(exit_on_fail=True)
		finally:
			raise


def run_vivado_xelab(
	cfg: XvivConfig,
	target_dir: str,
	units: list[str],
	*,
	label: str,
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
	cmd = [cfg.get_vivado().xelab_bin, *units]

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
		run_tool(
			cmd,
			cwd=target_dir,
			label=f"{__name__}_{label}",
			log_dir=cfg.log_dir,
			dry_run=cfg.dry_run,
			exit_on_fail=True,
		)
	except FileNotFoundError:
		try:
			find_vivado_dir_path(exit_on_fail=True)
		finally:
			raise


def run_vivado_xsim(
	cfg: XvivConfig,
	target_dir: str,
	*,
	label: str,
	config_tcl: str | None,
	top: str | None = None,
	wdb_file: str | None = None,
	stats: bool = True,
	nogui: bool = False,
	runall: bool = False,
	popen: bool = False,
	testplusarg: list[str] | None = None,
	unlink_config_file: bool = True,
) -> int | None:
	if config_tcl is None:
		return None

	logger.debug("%s: %s\n%s", __name__, label, config_tcl)

	config_tcl_path: str | None = None

	try:
		with tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_") as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		cmd = [cfg.get_vivado().xsim_bin]

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
			return run_tool(
				cmd,
				cwd=target_dir,
				label=f"{__name__}_{label}",
				log_dir=cfg.log_dir,
				dry_run=cfg.dry_run,
				popen=popen,
				exit_on_fail=True,
			)
		except FileNotFoundError:
			try:
				find_vivado_dir_path(exit_on_fail=True)
			finally:
				raise

	finally:
		if unlink_config_file and config_tcl_path and not cfg.dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)


def run_vivado(
	cfg: XvivConfig,
	*,
	label: str,
	config_tcl: str | None,
	parallel: bool = False,
	log_file_path: str | None = None,
) -> None:
	if config_tcl is None:
		return

	logger.debug("%s: %s - parallel: %s\n%s", __name__, label, str(parallel), config_tcl)

	config_tcl_path: str | None = None
	_error_occurred = False
	try:
		with tempfile.NamedTemporaryFile(mode="w", suffix="_config.tcl", delete=False, prefix="xviv_vivado_") as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		interactive = cfg.get_vivado().mode == "tcl"
		try:
			run_tool(
				[
					cfg.get_vivado().vivado_bin,
					"-mode",
					cfg.get_vivado().mode,
					"-nolog",
					"-nojournal",
					"-notrace",
					"-quiet",
					"-source",
					config_tcl_path,
				],
				cwd=cfg.work_dir,
				interactive=interactive,
				dry_run=cfg.dry_run,
				exit_on_fail=True,
				parallel=parallel,
				label=f"{__name__}_{label}",
				log_dir=cfg.log_dir if not log_file_path else None,
				log_file_path=log_file_path,
			)
		except FileNotFoundError:
			try:
				find_vivado_dir_path(exit_on_fail=True)
			finally:
				raise
	except BaseException as _:
		_error_occurred = True
		raise
	finally:
		if config_tcl_path and not cfg.dry_run and not _error_occurred:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)
