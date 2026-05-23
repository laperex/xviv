import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from xviv.config.project import XvivConfig

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

	define_flags = [f"-d {d}" for d in defines]
	include_flags = [f"-i {i}" for i in include_dirs]

	cmd = [
		xvlog_bin,
		"-sv",
		"-incr",
		"-work",
		xsim_lib,
		*define_flags,
		*include_flags,
		*fileset,
		*extra_files,
	]

	for x in lib or []:
		cmd += ["--lib", x]

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	if cfg.get_vivado().dry_run:
		return

	try:
		subprocess.run(cmd, check=True, cwd=target_dir)
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
	params: list[str] = []

	params += ["--debug", debug]

	if standalone:
		params += ["--standalone"]
	if run:
		params += ["--run"]
	if runall:
		params += ["--runall"]
	if incr:
		params += ["--incr"]
	if relax:
		params += ["--relax"]
	if nolog:
		params += ["--nolog"]
	if stats:
		params += ["--stats"]
	if override_timeunit:
		params += ["--override_timeunit"]
	if override_timeprecision:
		params += ["--override_timeprecision"]
	if noname_unnamed_generate:
		params += ["--noname_unnamed_generate"]
	if rangecheck:
		params += ["--rangecheck"]
	if transform_timing_checkers:
		params += ["--transform_timing_checkers"]
	if suppress_localparam_override_error:
		params += ["--suppress_localparam_override_error"]
	if ignore_assertions:
		params += ["--ignore_assertions"]
	if report_assertion_pass:
		params += ["--report_assertion_pass"]
	if ignore_coverage:
		params += ["--ignore_coverage"]
	if nosdfinterconnectdelays:
		params += ["--nosdfinterconnectdelays"]
	if nospecify:
		params += ["--nospecify"]
	if notimingchecks:
		params += ["--notimingchecks"]
	if mindelay:
		params += ["--mindelay"]
	if maxdelay:
		params += ["--maxdelay"]
	if typdelay:
		params += ["--typdelay"]
	if transport_int_delays:
		params += ["--transport_int_delays"]
	if sdfnoerror:
		params += ["--sdfnoerror"]
	if sdfnowarn:
		params += ["--sdfnowarn"]
	if dup_entity_as_module:
		params += ["--dup_entity_as_module"]
	if dpi_absolute:
		params += ["--dpi_absolute"]
	if cc_celldefines:
		params += ["--cc_celldefines"]
	if cc_libs:
		params += ["--cc_libs"]
	if O0:
		params += ["--O0"]

	if file:
		params += ["--file", file]
	if log:
		params += ["--log", log]
	if prj:
		params += ["--prj", prj]
	if initfile:
		params += ["--initfile", initfile]
	if ccExclusionFile:
		params += ["--ccExclusionFile", ccExclusionFile]
	if uvm_version:
		params += ["--uvm_version", uvm_version]
	if timescale:
		params += ["--timescale", timescale]
	if timeprecision_vhdl:
		params += ["--timeprecision_vhdl", timeprecision_vhdl]
	if snapshot:
		params += ["--snapshot", snapshot]
	if mt:
		params += ["--mt", str(mt)]
	if pulse_e_style:
		params += ["--pulse_e_style", pulse_e_style]
	if sdfmax:
		params += ["--sdfmax", sdfmax]
	if sdfmin:
		params += ["--sdfmin", sdfmin]
	if sdftyp:
		params += ["--sdftyp", sdftyp]
	if sdfroot:
		params += ["--sdfroot", sdfroot]
	if dpiheader:
		params += ["--dpiheader", dpiheader]
	if dpi_stacksize:
		params += ["--dpi_stacksize", dpi_stacksize]
	if sc_lib:
		params += ["--sc_lib", sc_lib]
	if sv_lib:
		params += ["--sv_lib", sv_lib]
	if sv_liblist:
		params += ["--sv_liblist", sv_liblist]
	if sc_root:
		params += ["--sc_root", sc_root]
	if sv_root:
		params += ["--sv_root", sv_root]
	if cov_db_dir:
		params += ["--cov_db_dir", cov_db_dir]
	if cov_db_name:
		params += ["--cov_db_name", cov_db_name]
	if cc_type:
		params += ["--cc_type", cc_type]

	if verbose is not None:
		params += ["--verbose", str(verbose)]
	if maxarraysize is not None:
		params += ["--maxarraysize", str(maxarraysize)]
	if maxdesigndepth is not None:
		params += ["--maxdesigndepth", str(maxdesigndepth)]
	if driver_display_limit is not None:
		params += ["--driver_display_limit", str(driver_display_limit)]
	if pulse_int_e is not None:
		params += ["--pulse_int_e", str(pulse_int_e)]
	if pulse_int_r is not None:
		params += ["--pulse_int_r", str(pulse_int_r)]
	if pulse_e is not None:
		params += ["--pulse_e", str(pulse_e)]
	if pulse_r is not None:
		params += ["--pulse_r", str(pulse_r)]

	for x in lib or []:
		params += ["--lib", x]
	for x in define or []:
		params += ["--define", x]
	for x in svlog or []:
		params += ["--svlog", x]
	for x in vlog or []:
		params += ["--vlog", x]
	for x in vhdl or []:
		params += ["--vhdl", x]
	for x in vhdl2008 or []:
		params += ["--vhdl2008", x]
	for x in vhdl2019 or []:
		params += ["--vhdl2019", x]
	for x in include or []:
		params += ["--include", x]
	for x in generic_top or []:
		params += ["--generic_top", x]
	for x in sourcelibdir or []:
		params += ["--sourcelibdir", x]
	for x in sourcelibext or []:
		params += ["--sourcelibext", x]
	for x in sourcelibfile or []:
		params += ["--sourcelibfile", x]

	cmd = [os.path.join(cfg.get_vivado().path, "bin", "xelab"), *units, *params]

	logger.info("Running: %s", " ".join(cmd))

	if cfg.get_vivado().dry_run:
		return

	os.makedirs(target_dir, exist_ok=True)

	try:
		subprocess.run(cmd, check=True, cwd=target_dir)
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
	xsim_bin = os.path.join(cfg.get_vivado().path, "bin", "xsim")

	if config_tcl is None:
		return

	pid = None

	with tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_") as tmp:
		tmp.write(config_tcl)
		config_tcl_path = tmp.name

	cmd = list(
		filter(
			None,
			[
				xsim_bin,
				"--stats" if stats else None,
				top if top else None,
				wdb_file if wdb_file else None,
				"-t",
				config_tcl_path,
				"-g" if not nogui else None,
			],
		)
	)

	for x in testplusarg or []:
		cmd += ["--testplusarg", x]

	if runall:
		cmd += ["--runall"]

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	if cfg.get_vivado().dry_run:
		return

	try:
		if popen:
			proc = subprocess.Popen(cmd, cwd=target_dir)

			pid = proc.pid
		else:
			subprocess.run(cmd, check=True, cwd=target_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)

	return pid


def run_vivado(
	cfg: XvivConfig,
	*,
	config_tcl: str | None,
	extra_args: list[str] | None = None,
	label: str | None = None,
	log_dir: str | None = None,
) -> None:
	if config_tcl is None:
		return

	vivado_bin = os.path.join(cfg.get_vivado().path, "bin", "vivado")
	job_log = logger.getChild(label) if label else logger

	config_tcl_path: str | None = None
	log_file = None

	try:
		# Write TCL to a named temp file
		with tempfile.NamedTemporaryFile(
			mode="w", suffix="_config.tcl", delete=False, prefix=f"xviv_{label or ''}_"
		) as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		if cfg.get_vivado().dry_run:
			job_log.info("[dry-run] TCL written to: %s", config_tcl_path)
			job_log.debug("[dry-run] TCL contents:\n%s", config_tcl)
			return

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
			*(extra_args or []),
		]
		job_log.info("Running: %s", " ".join(cmd))

		# TCL interactive mode - attach directly to terminal
		if cfg.get_vivado().mode == "tcl":
			result = subprocess.run(cmd)
			if result.returncode != 0:
				raise subprocess.CalledProcessError(result.returncode, cmd)
			return

		# Batch mode - stream output and write per-job log
		log_stem = label or "vivado"
		log_path = Path(log_dir or cfg.work_dir) / f"{log_stem}.log"
		log_path.parent.mkdir(parents=True, exist_ok=True)
		log_file = log_path.open("w")

		job_log.info("Log: %s", log_path)

		with subprocess.Popen(
			cmd,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1,
		) as proc:
			if proc.stdout is None:
				raise RuntimeError("stdout pipe unexpectedly None")

			for line in proc.stdout:
				stripped = line.rstrip()
				print(stripped)
				job_log.debug(stripped)
				log_file.write(line)
				log_file.flush()
			proc.wait()

		if proc.returncode != 0:
			job_log.error("Vivado exited with code %d (log: %s)", proc.returncode, log_path)
			raise subprocess.CalledProcessError(proc.returncode, cmd)

	finally:
		if log_file:
			log_file.close()
		if config_tcl_path and not cfg.get_vivado().dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)
