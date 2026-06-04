import logging
import os
import shutil
import subprocess
import typing

from xviv.tools.vivado import ToolRunner
from xviv.utils import error
from xviv.utils.job import Job

# from xviv.utils.process import run_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Version probe
# ---------------------------------------------------------------------------


def find_verilator_bin() -> str:
	path = shutil.which("verilator")
	if path is None:
		raise error.VerilatorNotFoundError()
	return path


def verilator_version(verilator_bin: str) -> tuple[int, int]:
	try:
		out = subprocess.check_output([verilator_bin, "--version"], text=True, stderr=subprocess.STDOUT)
		token = out.split()[1]
		major, minor = token.split(".")[:2]
		return int(major), int(minor)
	except Exception:
		return (0, 0)


class VerilatorRunner(ToolRunner):
	_DEFAULT_WORKERS: int = 4

	def __init__(self, cfg):
		super().__init__(cfg)

		self.verilator_bin = find_verilator_bin()
		self.obj_dir = os.path.join(cfg.work_dir, "obj_dir")
		self.binary = ""

		self.sequential_exec = True

	def configure(
		self, target_dir: str, label: str, compile_log_file: str, sim_log_file: str, trace_fst: bool = False, trace: bool = False, uvm: bool = False
	) -> typing.Self:
		self._target_dir = target_dir
		self._label = label
		self._compile_log_file = compile_log_file
		self._sim_log_file = sim_log_file
		self._trace_fst = trace_fst
		self._trace = trace
		self._uvm = uvm

		return self

	def compile_job(
		self,
		*,
		top: str,
		defines: list[str] = [],
		include_dirs: list[str] = [],
		timescale: str | None = None,
		fileset: list[str],
		threads: int = 1,
		trace_depth: int | None = None,
		uvm_pkg_dir: str | None = None,
		popen: bool = False,
	) -> typing.Self:
		self.binary = os.path.join(self.obj_dir, f"V{top}")

		cmd: list[str] = [
			self.verilator_bin,
			"--cc",
			"--exe",
			"--build",
			"-sv",
			"--top-module",
			top,
			"--Mdir",
			self.obj_dir,
			"-o",
			f"V{top}",
		]

		# Parallelism
		if threads > 1:
			cmd += ["--threads", str(threads)]

		# Waveform tracing
		if self._trace_fst:
			cmd += ["--trace-fst"]
		elif self._trace:
			cmd += ["--trace"]
		if trace_depth is not None:
			cmd += ["--trace-depth", str(trace_depth)]

		# UVM
		if self._uvm:
			if uvm_pkg_dir is not None:
				cmd += [f"-I{uvm_pkg_dir}"]
			cmd += ["--uvm-prefix", "uvm_"]

		# Preprocessor  (-DFOO and -Idir are single tokens for Verilator)
		for d in defines:
			cmd += [f"-D{d}"]
		for i in include_dirs:
			cmd += [f"-I{i}"]
		if timescale is not None:
			cmd += ["--timescale", timescale]

		# cmd += list(extra_args)
		cmd += fileset

		self._pairs.append(
			(
				"",
				Job(
					label=self._label,
					cmd=tuple(cmd),
					cwd=self._target_dir,
					log_file=self._compile_log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=popen,
					env=None,
				),
			)
		)

		return self

	def sim_job(
		self,
		*,
		uvm_test: str | None = None,
		uvm_verbosity: str = "UVM_MEDIUM",
		uvm_max_quit_count: int | None = None,
		plusargs: list[str] = [],
		trace_file: str | None = None,
		popen: bool = False,
	) -> typing.Self:

		if not self._cfg.dry_run and not os.path.isfile(self.binary):
			raise error.VerilatorBinaryMissingError(self.binary)

		cmd: list[str] = [self.binary]

		# UVM plusargs
		if self._uvm:
			if uvm_test is not None:
				cmd += [f"+UVM_TESTNAME={uvm_test}"]
			cmd += [f"+UVM_VERBOSITY={uvm_verbosity}"]
			if uvm_max_quit_count is not None:
				cmd += [f"+UVM_MAX_QUIT_COUNT={uvm_max_quit_count}"]

		if self._trace or self._trace_fst:
			tf = trace_file or os.path.join(self._target_dir, "dump.vcd" if self._trace else "dump.fst")
			cmd += ["+verilator+rand+reset+2"]
			os.environ["VERILATOR_TRACE_FILE"] = tf

		cmd += [f"+{a}" if not a.startswith("+") else a for a in plusargs]

		self._pairs.append(
			(
				"",
				Job(
					label=self._label,
					cmd=tuple(cmd),
					cwd=self._target_dir,
					log_file=self._sim_log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=popen,
					env=None,
				),
			)
		)

		return self
