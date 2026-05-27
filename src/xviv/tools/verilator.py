import logging
import os
import shutil
import subprocess

from xviv.utils import error
from xviv.utils.process import run_tool

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


# ---------------------------------------------------------------------------
# Step 1: compile
# ---------------------------------------------------------------------------


def run_verilator_compile(
	work_dir: str,
	fileset: list[str],
	top: str,
	*,
	label: str,
	log_dir: str,
	defines: list[str] = [],
	include_dirs: list[str] = [],
	timescale: str | None = None,
	threads: int = 1,
	trace: bool = False,
	trace_fst: bool = False,
	trace_depth: int | None = None,
	uvm: bool = False,
	uvm_pkg_dir: str | None = None,
	extra_args: list[str] = [],
	dry_run: bool = False,
) -> str:
	verilator_bin = find_verilator_bin()
	obj_dir = os.path.join(work_dir, "obj_dir")
	binary = os.path.join(obj_dir, f"V{top}")

	cmd: list[str] = [
		verilator_bin,
		"--cc",
		"--exe",
		"--build",
		"-sv",
		"--top-module",
		top,
		"--Mdir",
		obj_dir,
		"-o",
		f"V{top}",
	]

	# Parallelism
	if threads > 1:
		cmd += ["--threads", str(threads)]

	# Waveform tracing
	if trace_fst:
		cmd += ["--trace-fst"]
	elif trace:
		cmd += ["--trace"]
	if trace_depth is not None:
		cmd += ["--trace-depth", str(trace_depth)]

	# UVM
	if uvm:
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

	cmd += list(extra_args)
	cmd += fileset

	try:
		run_tool(cmd, label=f"{__name__}_{label}", log_dir=log_dir, cwd=work_dir, dry_run=dry_run)
	except subprocess.CalledProcessError as e:
		raise error.VerilatorCompileError(top, e.returncode) from e

	return binary


# ---------------------------------------------------------------------------
# Step 2: run
# ---------------------------------------------------------------------------


def run_verilator_sim(
	binary: str,
	work_dir: str,
	*,
	label: str,
	log_dir: str,
	plusargs: list[str] = [],
	uvm: bool = False,
	uvm_test: str | None = None,
	uvm_verbosity: str = "UVM_MEDIUM",
	uvm_max_quit_count: int | None = None,
	trace: bool = False,
	trace_fst: bool = False,
	trace_file: str | None = None,
	dry_run: bool = False,
) -> None:
	if not dry_run and not os.path.isfile(binary):
		raise error.VerilatorBinaryMissingError(binary)

	cmd: list[str] = [binary]

	# UVM plusargs
	if uvm:
		if uvm_test is not None:
			cmd += [f"+UVM_TESTNAME={uvm_test}"]
		cmd += [f"+UVM_VERBOSITY={uvm_verbosity}"]
		if uvm_max_quit_count is not None:
			cmd += [f"+UVM_MAX_QUIT_COUNT={uvm_max_quit_count}"]

	if trace or trace_fst:
		tf = trace_file or os.path.join(work_dir, "dump.vcd" if trace else "dump.fst")
		cmd += ["+verilator+rand+reset+2"]
		os.environ["VERILATOR_TRACE_FILE"] = tf

	cmd += [f"+{a}" if not a.startswith("+") else a for a in plusargs]

	run_tool(cmd, label=f"{__name__}_{label}", log_dir=log_dir, cwd=work_dir, dry_run=dry_run, exit_on_fail=True)
