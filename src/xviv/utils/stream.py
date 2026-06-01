"""
Pure process-streaming utilities.

This module owns exactly one responsibility: running subprocesses and
yielding their output line-by-line as typed OutputLine objects.

Invariants enforced here:
- subprocess is imported only in this module.
- pty, select, termios, tty are imported only in this module.
- No scheduling logic (sequential vs parallel) lives here.
- No file I/O (log files are the caller's concern).
- No terminal rendering (display is the caller's concern).
"""

from __future__ import annotations

import logging
import os
import pty
import select
import subprocess
import sys
import termios
import tty
from collections.abc import Callable, Iterator
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Output line type
# ---------------------------------------------------------------------------


@dataclass
class OutputLine:
	text: str
	level: int
	raw: str


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------


def identity_classifier(raw: str) -> OutputLine:
	"""Pass-through classifier: all lines are DEBUG level."""
	return OutputLine(text=raw, level=logging.DEBUG, raw=raw)


# ---------------------------------------------------------------------------
# Streaming functions
# ---------------------------------------------------------------------------


def stream_pipe(
	cmd: tuple[str, ...] | list[str],
	*,
	cwd: str,
	env: dict[str, str] | None = None,
	classifier: Callable[[str], OutputLine],
) -> Iterator[OutputLine]:
	with subprocess.Popen(
		list(cmd),
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
		bufsize=1,
		cwd=cwd,
		env=env,
	) as proc:
		assert proc.stdout is not None
		for line in proc.stdout:
			yield classifier(line.rstrip("\r\n"))
	# Popen.__exit__ has called proc.wait(); returncode is now set.
	if proc.returncode != 0:
		raise subprocess.CalledProcessError(proc.returncode, list(cmd))


def stream_pty(
	cmd: tuple[str, ...] | list[str],
	*,
	cwd: str,
	env: dict[str, str] | None = None,
	classifier: Callable[[str], OutputLine],
) -> Iterator[OutputLine]:
	master_fd, slave_fd = pty.openpty()

	proc = subprocess.Popen(
		list(cmd),
		stdin=slave_fd,
		stdout=slave_fd,
		stderr=slave_fd,
		cwd=cwd,
		env=env,
		close_fds=True,
	)
	os.close(slave_fd)

	old_settings: list | None = None
	if sys.stdin.isatty():
		old_settings = termios.tcgetattr(sys.stdin)
		tty.setraw(sys.stdin.fileno())

	buf = b""
	try:
		while True:
			fds = [master_fd]
			if sys.stdin.isatty():
				fds.append(sys.stdin.fileno())

			try:
				r, _, _ = select.select(fds, [], [], 0.05)
			except (ValueError, OSError):
				break

			if master_fd in r:
				try:
					data = os.read(master_fd, 4096)
				except OSError:
					break
				if data:
					buf += data
					while b"\n" in buf:
						raw_bytes, buf = buf.split(b"\n", 1)
						decoded = raw_bytes.rstrip(b"\r").decode(errors="replace")
						yield classifier(decoded)

			if sys.stdin.isatty() and sys.stdin.fileno() in r:
				try:
					data = os.read(sys.stdin.fileno(), 4096)
				except OSError:
					break
				if data:
					os.write(master_fd, data)

			if proc.poll() is not None:
				# Drain any remaining bytes from the master side.
				try:
					while True:
						r2, _, _ = select.select([master_fd], [], [], 0.1)
						if not r2:
							break
						data = os.read(master_fd, 4096)
						if not data:
							break
						buf += data
				except OSError:
					pass
				break

	finally:
		if old_settings is not None:
			termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
		try:
			os.close(master_fd)
		except OSError:
			pass

	# Yield any bytes still in the buffer after the process exited.
	for raw_bytes in buf.split(b"\n"):
		decoded = raw_bytes.rstrip(b"\r").decode(errors="replace")
		if decoded:
			yield classifier(decoded)

	proc.wait()
	if proc.returncode != 0:
		raise subprocess.CalledProcessError(proc.returncode, list(cmd))


def stream_popen(
	cmd: tuple[str, ...] | list[str],
	*,
	cwd: str,
	env: dict[str, str] | None = None,
) -> int:
	proc = subprocess.Popen(list(cmd), cwd=cwd, env=env)
	return proc.pid
