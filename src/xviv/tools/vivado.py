from __future__ import annotations

import logging
import tempfile
import typing
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from xviv.config.project import XvivConfig
from xviv.utils.display import _counter, terminal_full_length_divider
from xviv.utils.error import JobFailedError
from xviv.utils.job import Job, run_job_list
from xviv.utils.log import DIM, RESET
from xviv.utils.stream import OutputLine
from xviv.utils.tools import find_vivado_dir_path

logger = logging.getLogger(__name__)


class ToolRunner:
	# Base runner for tools
	_PREFIX_MAP: dict[str, int] = {}
	_DEFAULT_WORKERS: int = 1

	def __init__(self, cfg: XvivConfig) -> None:
		self._cfg = cfg
		self._pairs: list[tuple[Path, Job]] = []
		self.sequential_exec: bool = False

	@classmethod
	def classify(cls, raw: str) -> OutputLine:
		# Map raw output to log level
		line = raw.rstrip()
		for prefix, level in cls._PREFIX_MAP.items():
			if line.startswith(prefix):
				return OutputLine(text=line[len(prefix) :].strip(), level=level, raw=raw)
		return OutputLine(text=line, level=logging.DEBUG, raw=raw)

	@staticmethod
	@contextmanager
	def jobs_ctx(
		pairs: list[tuple[Path, Job] | None],
	) -> Iterator[list[Job]]:
		# Yield jobs and clean up tempfiles
		clean = [p for p in pairs if p is not None]
		paths = [path for path, _ in clean]
		jobs = [job for _, job in clean]
		try:
			yield jobs
		finally:
			for p in paths:
				# try:
				# 	# p.unlink(missing_ok=True)
				# except OSError:
				pass

	def _run_internal(self, jobs: list[Job], *, max_workers: int | None = None) -> None:
		n = max_workers if max_workers is not None else self._DEFAULT_WORKERS
		run_job_list(jobs, max_workers=n, sequential_exec=self.sequential_exec)

	def run(
		self,
		*,
		max_workers: int | None = None,
	) -> None:
		with self.jobs_ctx(self._pairs) as jobs:
			self._run_internal(jobs, max_workers=max_workers)


class XilinxToolRunner(ToolRunner):
	# Base runner for Xilinx tools
	_PREFIX_MAP: dict[str, int] = {
		"ERROR:": logging.ERROR,
		"CRITICAL WARNING:": logging.CRITICAL,
		"CRITICAL:": logging.CRITICAL,
		"WARNING:": logging.WARNING,
		"INFO:": logging.INFO,
	}

	@typing.override
	def _run_internal(self, jobs: list[Job], *, max_workers: int | None = None) -> None:
		n = max_workers if max_workers is not None else self._DEFAULT_WORKERS
		try:
			run_job_list(jobs, max_workers=n)
		except JobFailedError as exc:
			for _, inner in exc.failed:
				if isinstance(inner, FileNotFoundError):
					find_vivado_dir_path(exit_on_fail=True)

	def make_pairs(
		self, names: list[str], tcl_fn: Callable[[str], str], *, label_prefix: str, log_prefix: str, annotate: bool = False
	) -> typing.Self:
		# Build (path, job) pairs
		for idx, name in enumerate(names):
			if annotate:
				print()
				print(_counter(idx + 1, len(names)), f"{label_prefix}_{name}")
				print(f"{DIM}{terminal_full_length_divider()}{RESET}")
			self.job(
				tcl_fn(name),
				label=f"{label_prefix}_{name}",
				log_file=str(Path(self._cfg.log_dir) / f"{log_prefix}_{name}.log"),
			)
			if annotate:
				print(f"{DIM}{terminal_full_length_divider()}{RESET}")
			# if result is not None:
			# 	self._pairs.append((result)

		return self


class VivadoRunner(XilinxToolRunner):
	# Vivado batch/TCL runner
	_DEFAULT_WORKERS: int = 4

	def __init__(self, cfg: XvivConfig):
		super().__init__(cfg)

	def job(
		self,
		tcl: str | None,
		*,
		label: str,
		log_file: str,
	) -> typing.Self:
		# Build Vivado job
		if tcl is None:
			return self

		tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_config.tcl", delete=False, prefix="xviv_vivado_")
		tmp.write(tcl)
		tmp.close()
		tcl_path = Path(tmp.name)
		logger.debug("VivadoRunner.job %s: tcl → %s", label, tcl_path)

		viv = self._cfg.get_vivado()
		self._pairs.append(
			(
				tcl_path,
				Job(
					label=label,
					cmd=(
						viv.vivado_bin,
						"-mode",
						viv.mode,
						"-nolog",
						"-nojournal",
						"-notrace",
						"-quiet",
						"-source",
						str(tcl_path),
					),
					cwd=self._cfg.work_dir,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=viv.mode == "tcl",
					detach=False,
					env=None,
				),
			)
		)


class XvlogRunner(XilinxToolRunner):
	# SystemVerilog compiler
	_DEFAULT_WORKERS: int = 4

	@classmethod
	def classify(cls, raw: str) -> OutputLine:
		# Demote repetitive INFO to DEBUG
		oline = super().classify(raw)
		if oline.level == logging.INFO and oline.text.startswith("Analyzing "):
			return OutputLine(text=oline.text, level=logging.DEBUG, raw=raw)
		return oline

	def job(
		self,
		target_dir: str,
		fileset: list[str],
		xsim_lib: str,
		*,
		label: str,
		log_file: str,
		lib: list[str] | None = None,
		defines: list[str] | None = None,
		include_dirs: list[str] | None = None,
	) -> typing.Self:
		viv = self._cfg.get_vivado()
		cmd: list[str] = [viv.xvlog_bin, "--sv", "--incr", "--work", xsim_lib]

		for d in defines or []:
			cmd += ["-d", d]
		for i in include_dirs or []:
			cmd += ["-i", i]
		for x in lib or []:
			cmd += ["-L", x]

		cmd += fileset

		if viv.glbl_file:
			cmd.append(viv.glbl_file)

		self._pairs.append(
			(
				"",
				Job(
					label=label,
					cmd=tuple(cmd),
					cwd=target_dir,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=False,
					env=None,
				),
			)
		)

		return self


class XelabRunner(XilinxToolRunner):
	# Elaboration tool
	_DEFAULT_WORKERS: int = 2

	@classmethod
	def classify(cls, raw: str) -> OutputLine:
		# Promote success to WARNING for visibility
		oline = super().classify(raw)
		if oline.level == logging.INFO and "Elaboration Successful" in oline.text:
			return OutputLine(text=oline.text, level=logging.WARNING, raw=raw)
		return oline

	def job(
		self,
		target_dir: str,
		units: list[str],
		*,
		label: str,
		log_file: str,
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
	) -> typing.Self:
		cmd: list[str] = [self._cfg.get_vivado().xelab_bin, *units, "--debug", debug]

		for flag, opt in [
			(standalone, "--standalone"),
			(run, "--run"),
			(runall, "--runall"),
			(incr, "--incr"),
			(relax, "--relax"),
			(nolog, "--nolog"),
			(stats, "--stats"),
			(override_timeunit, "--override_timeunit"),
			(override_timeprecision, "--override_timeprecision"),
			(noname_unnamed_generate, "--noname_unnamed_generate"),
			(rangecheck, "--rangecheck"),
			(transform_timing_checkers, "--transform_timing_checkers"),
			(suppress_localparam_override_error, "--suppress_localparam_override_error"),
			(ignore_assertions, "--ignore_assertions"),
			(report_assertion_pass, "--report_assertion_pass"),
			(ignore_coverage, "--ignore_coverage"),
			(nosdfinterconnectdelays, "--nosdfinterconnectdelays"),
			(nospecify, "--nospecify"),
			(notimingchecks, "--notimingchecks"),
			(mindelay, "--mindelay"),
			(maxdelay, "--maxdelay"),
			(typdelay, "--typdelay"),
			(transport_int_delays, "--transport_int_delays"),
			(sdfnoerror, "--sdfnoerror"),
			(sdfnowarn, "--sdfnowarn"),
			(dup_entity_as_module, "--dup_entity_as_module"),
			(dpi_absolute, "--dpi_absolute"),
			(cc_celldefines, "--cc_celldefines"),
			(cc_libs, "--cc_libs"),
			(O0, "--O0"),
		]:
			if flag:
				cmd.append(opt)

		for val, opt in [
			(file, "--file"),
			(log, "--log"),
			(prj, "--prj"),
			(initfile, "--initfile"),
			(ccExclusionFile, "--ccExclusionFile"),
			(uvm_version, "--uvm_version"),
			(timescale, "--timescale"),
			(timeprecision_vhdl, "--timeprecision_vhdl"),
			(snapshot, "--snapshot"),
			(mt, "--mt"),
			(pulse_e_style, "--pulse_e_style"),
			(sdfmax, "--sdfmax"),
			(sdfmin, "--sdfmin"),
			(sdftyp, "--sdftyp"),
			(sdfroot, "--sdfroot"),
			(dpiheader, "--dpiheader"),
			(dpi_stacksize, "--dpi_stacksize"),
			(sc_lib, "--sc_lib"),
			(sv_lib, "--sv_lib"),
			(sv_liblist, "--sv_liblist"),
			(sc_root, "--sc_root"),
			(sv_root, "--sv_root"),
			(cov_db_dir, "--cov_db_dir"),
			(cov_db_name, "--cov_db_name"),
			(cc_type, "--cc_type"),
		]:
			if val is not None:
				cmd += [opt, val]

		for val, opt in [
			(verbose, "--verbose"),
			(maxarraysize, "--maxarraysize"),
			(maxdesigndepth, "--maxdesigndepth"),
			(driver_display_limit, "--driver_display_limit"),
			(pulse_int_e, "--pulse_int_e"),
			(pulse_int_r, "--pulse_int_r"),
			(pulse_e, "--pulse_e"),
			(pulse_r, "--pulse_r"),
		]:
			if val is not None:
				cmd += [opt, str(val)]

		for items, opt in [
			(lib, "-L"),
			(define, "-d"),
			(include, "-i"),
			(svlog, "--svlog"),
			(vlog, "--vlog"),
			(vhdl, "--vhdl"),
			(vhdl2008, "--vhdl2008"),
			(vhdl2019, "--vhdl2019"),
			(generic_top, "--generic_top"),
			(sourcelibdir, "--sourcelibdir"),
			(sourcelibext, "--sourcelibext"),
			(sourcelibfile, "--sourcelibfile"),
		]:
			for x in items or []:
				cmd += [opt, x]

		self._pairs.append(
			(
				"",
				Job(
					label=label,
					cmd=tuple(cmd),
					cwd=target_dir,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=False,
					env=None,
				),
			)
		)

		return self


class XsimRunner(XilinxToolRunner):
	# Simulation runner
	_DEFAULT_WORKERS: int = 4

	@classmethod
	def classify(cls, raw: str) -> OutputLine:
		# Handle SV system tasks
		line = raw.rstrip()
		if line.startswith("$fatal"):
			return OutputLine(text=line, level=logging.CRITICAL, raw=raw)
		if line.startswith("$error"):
			return OutputLine(text=line, level=logging.ERROR, raw=raw)
		if line.startswith("$warning"):
			return OutputLine(text=line, level=logging.WARNING, raw=raw)
		if line.startswith(("$info", "$finish")):
			return OutputLine(text=line, level=logging.INFO, raw=raw)
		return super().classify(raw)

	def job(
		self,
		target_dir: str,
		*,
		label: str,
		log_file: str,
		config_tcl: str | None,
		top: str | None = None,
		wdb_file: str | None = None,
		stats: bool = True,
		nogui: bool = False,
		runall: bool = False,
		popen: bool = False,
		testplusarg: list[str] | None = None,
	) -> typing.Self:
		# Build simulation job
		if config_tcl is None:
			return None

		tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_")
		tmp.write(config_tcl)
		tmp.close()
		tcl_path = Path(tmp.name)

		cmd: list[str] = [self._cfg.get_vivado().xsim_bin]
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
		cmd += ["-t", str(tcl_path)]
		for x in testplusarg or []:
			cmd += ["--testplusarg", x]

		self._pairs.append(
			(
				tcl_path,
				Job(
					label=label,
					cmd=tuple(cmd),
					cwd=target_dir,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=popen,
					env=None,
				),
			)
		)

		return self
