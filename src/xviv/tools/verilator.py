# Verilator three-step flow
# -------------------------
# 1. verilator --binary  ->  compiles SV and generates + builds the C++ binary
#    (verilator >= 5.0; for older versions use --cc then make separately)
# 2. Run the generated binary with plusargs
#
# UVM with verilator
# ------------------
# Verilator does not ship a pre-compiled UVM library.  The user must:
#   a) point uvm_pkg_dir at a verilator-compatible UVM root
#      (e.g. https://github.com/antmicro/verilator-uvm), OR
#   b) include UVM source files directly in the `sources` list.
# Either way, pass --uvm-prefix to verilator so it finds the C++ stubs.

import logging
import os
import shutil
import subprocess
import sys

from xviv.utils import error

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

	# -- Threads ---------------------------------------------------------- #
	if threads > 1:
		cmd += ["--threads", str(threads)]

	# -- Waveform tracing ----------------------------------------------- #
	if trace_fst:
		cmd += ["--trace-fst"]
	elif trace:
		cmd += ["--trace"]

	if trace_depth is not None:
		cmd += ["--trace-depth", str(trace_depth)]

	# -- UVM ----------------------------------------------------------- #
	if uvm:
		if uvm_pkg_dir is not None:
			cmd += [f"-I{uvm_pkg_dir}"]
		cmd += ["--uvm-prefix", "uvm_"]  # C++ stub prefix expected by verilator-uvm

	# -- Preprocessor ------------------------------------------------- #
	for d in defines:
		cmd += [f"-D{d}"]

	for i in include_dirs:
		cmd += [f"-I{i}"]

	if timescale is not None:
		cmd += ["--timescale", timescale]

	# -- Extra user flags ----------------------------------------------- #
	cmd += list(extra_args)

	# -- Source files (last) -------------------------------------------- #
	cmd += fileset

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(work_dir, exist_ok=True)

	if dry_run:
		logger.info("[dry-run] verilator compile skipped")
		return binary

	try:
		subprocess.run(cmd, check=True, cwd=work_dir)
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

	# -- UVM plusargs ---------------------------------------------------- #
	if uvm:
		if uvm_test is not None:
			cmd += [f"+UVM_TESTNAME={uvm_test}"]
		cmd += [f"+UVM_VERBOSITY={uvm_verbosity}"]
		if uvm_max_quit_count is not None:
			cmd += [f"+UVM_MAX_QUIT_COUNT={uvm_max_quit_count}"]

	# -- Trace output file ----------------------------------------------- #
	if trace or trace_fst:
		tf = trace_file or os.path.join(work_dir, "dump.vcd" if trace else "dump.fst")
		cmd += ["+verilator+rand+reset+2"]  # randomise uninitialised regs
		# verilated binary reads VERILATOR_TRACE_FILE from env, or via --trace
		# The actual filename can also be set via --trace-file at compile time;
		# here we use the env-var approach for maximum flexibility.
		os.environ["VERILATOR_TRACE_FILE"] = tf

	# -- User plusargs --------------------------------------------------- #
	cmd += [f"+{a}" if not a.startswith("+") else a for a in plusargs]

	logger.info("Running: %s", " ".join(cmd))

	if dry_run:
		logger.info("[dry-run] verilator sim skipped")
		return

	try:
		subprocess.run(cmd, check=True, cwd=work_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)
