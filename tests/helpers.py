"""Pure helper functions for the xviv test suite (no fixtures)."""

from __future__ import annotations

from xviv.utils.job import Job
from xviv.utils.stream import identity_classifier


def has_cmd(tcl: str, command: str) -> bool:
	"""True if *command* appears at the start of any line (word-boundary)."""
	for line in tcl.splitlines():
		stripped = line.lstrip()
		if stripped == command or stripped.startswith(command + " ") or stripped.startswith(command + "\t"):
			return True
	return False


def lacks_cmd(tcl: str, command: str) -> bool:
	"""Inverse of has_cmd."""
	return not has_cmd(tcl, command)


def line_index(tcl: str, command: str) -> int:
	"""Index of first line where *command* is the leading token.

	Matches at the start of the stripped line to avoid false positives from
	path names that happen to contain the command string (e.g. a tmp_path
	that includes 'phys_opt_design' because the test function is named that).
	Raises ValueError if not found.
	"""
	for i, line in enumerate(tcl.splitlines()):
		stripped = line.lstrip()
		if stripped == command or stripped.startswith(command + " ") or stripped.startswith(command + "\t"):
			return i
	raise ValueError(f"command {command!r} not found in TCL:\n{tcl}")


def make_job(**kwargs) -> Job:
	"""Construct a Job with safe defaults for fields the test doesn't care about."""
	defaults = dict(
		label="test_job",
		cmd=("echo", "hello"),
		cwd="/tmp",
		classifier=identity_classifier,
		dry_run=False,
		interactive=False,
		detach=False,
		log_file="",
		env=None,
	)
	defaults.update(kwargs)
	return Job(**defaults)
