from __future__ import annotations

import logging
import os
import pty
import re
import select
import subprocess
import sys
import termios
import tty
from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass
class OutputLine:
	text: str
	level: int
	raw: str


def identity_classifier(raw: str) -> OutputLine:
	return OutputLine(text=raw, level=logging.DEBUG, raw=raw)


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
		if proc.returncode != 0 and proc.returncode is not None:
			raise subprocess.CalledProcessError(proc.returncode, list(cmd))


def stream_pty(
	cmd: tuple[str, ...] | list[str],
	*,
	cwd: str,
	env: dict[str, str] | None = None,
	classifier: Callable[[str], OutputLine],
) -> Iterator[OutputLine]:
	if not sys.stdin.isatty():
		yield from stream_pipe(cmd, cwd=cwd, env=env, classifier=classifier)
		return

	master_fd, slave_fd = pty.openpty()

	try:
		import fcntl
		import termios as _t

		winsz = fcntl.ioctl(sys.stdout.fileno(), _t.TIOCGWINSZ, b"\x00" * 8)
		fcntl.ioctl(master_fd, _t.TIOCSWINSZ, winsz)
	except Exception:
		pass

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

	stdin_fd = sys.stdin.fileno()
	stdout_fd = sys.stdout.fileno()

	old_settings = termios.tcgetattr(stdin_fd)
	tty.setraw(stdin_fd)

	received: list[bytes] = []

	try:
		while True:
			try:
				r, _, _ = select.select([master_fd, stdin_fd], [], [], 0.05)
			except (ValueError, OSError):
				break

			if master_fd in r:
				try:
					data = os.read(master_fd, 4096)
				except OSError:
					break
				if data:
					received.append(data)
					os.write(stdout_fd, data)

			if stdin_fd in r:
				try:
					data = os.read(stdin_fd, 4096)
				except OSError:
					break
				if data:
					os.write(master_fd, data)

			if proc.poll() is not None:
				try:
					while True:
						r2, _, _ = select.select([master_fd], [], [], 0.1)
						if not r2:
							break
						data = os.read(master_fd, 4096)
						if not data:
							break
						received.append(data)
						os.write(stdout_fd, data)
				except OSError:
					pass
				break

	finally:
		termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
		try:
			os.close(master_fd)
		except OSError:
			pass

	proc.wait()

	raw_output = b"".join(received)
	text_output = raw_output.decode(errors="replace")
	text_output = text_output.replace("\r\n", "\n").replace("\r", "\n")

	ansi_escape = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
	text_output = ansi_escape.sub("", text_output)

	for raw_line in text_output.splitlines():
		stripped = raw_line.rstrip()
		if stripped:
			yield classifier(stripped)

	if proc.returncode != 0 and proc.returncode:
		raise subprocess.CalledProcessError(proc.returncode, list(cmd))


def stream_popen(
	cmd: tuple[str, ...] | list[str],
	*,
	cwd: str,
	env: dict[str, str] | None = None,
) -> int:
	proc = subprocess.Popen(list(cmd), cwd=cwd, env=env)
	return proc.pid
