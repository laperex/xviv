import logging
import os
import pty
import select
import subprocess
import sys
import termios
import tty

from xviv.utils.log import BOLD, DIM, LEVEL_COLORS, RESET
from xviv.utils.term import print_terminal_divider

logger = logging.getLogger("xviv.vivado")

VIVADO_PREFIX_MAP = {
	"ERROR:": LEVEL_COLORS[logging.ERROR],
	"CRITICAL WARNING:": LEVEL_COLORS[logging.CRITICAL],
	"CRITICAL:": LEVEL_COLORS[logging.CRITICAL],
	"WARNING:": LEVEL_COLORS[logging.WARNING],
	"INFO:": LEVEL_COLORS[logging.INFO],
}


def colorize(line: str) -> str:
	for prefix, color in VIVADO_PREFIX_MAP.items():
		if line.startswith(prefix):
			if color == LEVEL_COLORS[logging.INFO]:
				return f"{color}{BOLD}{prefix}{RESET} {line[len(prefix) :].strip()}"
			else:
				return f"{color}{BOLD}{prefix}{RESET} {color}{line[len(prefix) :].strip()}{RESET}"
	return line


def _process_pty_output(data: bytes, log_file, stdout_print: bool) -> None:
	if log_file:
		log_file.write(data.decode(errors="replace"))
		log_file.flush()

	if not stdout_print:
		return

	chunks = data.split(b"\n")
	out = b""

	for chunk in chunks[:-1]:
		clean = chunk.rstrip(b"\r").decode(errors="replace")
		colorized = colorize(clean)
		if colorized != clean:
			out += colorized.encode() + b"\r\n"
		else:
			out += chunk + b"\n"

	out += chunks[-1]

	sys.stdout.buffer.write(out)
	sys.stdout.buffer.flush()


def _run_interactive_pty(
	cmd: list[str],
	*,
	cwd: str,
	env: dict[str, str] | None,
	log_file,
	stdout_print: bool,
) -> subprocess.Popen:
	master_fd, slave_fd = pty.openpty()

	proc = subprocess.Popen(
		cmd,
		stdin=slave_fd,
		stdout=slave_fd,
		stderr=slave_fd,
		cwd=cwd,
		env=env,
		close_fds=True,
	)
	os.close(slave_fd)

	old_settings = None
	if sys.stdin.isatty():
		old_settings = termios.tcgetattr(sys.stdin)
		tty.setraw(sys.stdin.fileno())

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
					_process_pty_output(data, log_file, stdout_print)

			if sys.stdin.isatty() and sys.stdin.fileno() in r:
				try:
					data = os.read(sys.stdin.fileno(), 4096)
				except OSError:
					break
				if data:
					os.write(master_fd, data)

			if proc.poll() is not None:
				try:
					while True:
						r, _, _ = select.select([master_fd], [], [], 0.1)
						if not r:
							break
						data = os.read(master_fd, 4096)
						if not data:
							break
						_process_pty_output(data, log_file, stdout_print)
				except OSError:
					pass
				break

	finally:
		if old_settings:
			termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
		try:
			os.close(master_fd)
		except OSError:
			pass

	proc.wait()
	return proc


def run_tool(
	cmd: list[str],
	*,
	cwd: str,
	label: str,
	log_dir: str | None = None,
	log_file_path: str | None = None,
	env: dict[str, str] | None = None,
	parallel: bool = False,
	popen: bool = False,
	interactive: bool = False,
	exit_on_fail: bool = False,
	dry_run: bool = False,
) -> int | None:
	logger = logging.getLogger(__name__)
	if label:
		logger = logger.getChild(label)

	_loglevel = logging.INFO if parallel or dry_run else logging.DEBUG
	logger.log(_loglevel, "Running: %s", " ".join(cmd))

	if dry_run:
		return None

	os.makedirs(cwd, exist_ok=True)

	log_file = None
	_log_printed = False
	proc = None

	try:
		if log_dir:
			log_file_path = os.path.join(log_dir, f"{label.replace('.', '_')}.log")
			os.makedirs(log_dir, exist_ok=True)

		if log_file_path:
			log_file = open(log_file_path, "w")
			logger.info("Log: %s", log_file_path)

		if popen:
			return subprocess.Popen(cmd, cwd=cwd).pid

		if not parallel:
			print_terminal_divider()
			print(f"{BOLD}{DIM}▶{RESET} {BOLD}{' '.join(cmd)}{RESET}")

		# if parallel:
		# 	print(f'{LEVEL_COLORS[logging.CRITICAL]}START JOB{RESET} {BOLD}{label}{RESET} - {DIM}{log_file_path}{RESET}')

		if interactive:
			proc = _run_interactive_pty(
				cmd,
				cwd=cwd,
				env=env,
				log_file=log_file,
				stdout_print=not parallel,
			)
		else:
			with subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
				cwd=cwd,
				env=env,
			) as proc:
				assert proc.stdout is not None
				for line in proc.stdout:
					stripped = line.rstrip()
					logger.debug(stripped)

					if not parallel:
						print(colorize(stripped))

					if log_file:
						log_file.write(line)
						log_file.flush()

				proc.wait()

		if not parallel:
			if log_file_path:
				print(f"{DIM}{BOLD}LOG{RESET} {DIM}{log_file_path}{RESET}")
			_log_printed = True
			print_terminal_divider()

		if proc.returncode != 0:
			raise subprocess.CalledProcessError(proc.returncode, cmd)

		return proc.returncode

	except subprocess.CalledProcessError as e:
		if exit_on_fail:
			if not parallel:
				logger.error(
					"Command '%s' returned non-zero exit status %s",
					" ".join(cmd),
					e.returncode,
				)
			else:
				logger.error("Command returned non-zero exit status %s", e.returncode)
			sys.exit(e.returncode)
		raise

	except KeyboardInterrupt:
		if proc is not None and proc.poll() is None:
			proc.terminate()
			try:
				proc.wait(timeout=5)
			except subprocess.TimeoutExpired:
				proc.kill()
		sys.exit(1)

	finally:
		if log_file:
			log_file.close()
		if not _log_printed and log_file_path:
			if not parallel:
				print(f"{DIM}{BOLD}LOG{RESET} {DIM}{log_file_path}{RESET}")

	return None
