import copy
import logging
import os
import sys

LEVEL_COLORS = {
	logging.DEBUG: "\033[36m",  # cyan
	logging.INFO: "\033[32m",  # green
	logging.WARNING: "\033[33m",  # yellow
	logging.ERROR: "\033[31m",  # red
	logging.CRITICAL: "\033[35m",  # magenta
}

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
DIM = "\033[2m"


class ColorFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		record = copy.copy(record)
		color = LEVEL_COLORS.get(record.levelno, "")
		record.levelname = f"{color}{BOLD}{record.levelname}{RESET}"
		record.name = f"\033[2m{record.name}{RESET}"

		if record.levelno == logging.ERROR:
			record.msg = f"{LEVEL_COLORS[logging.ERROR]}{record.msg}{RESET}"
		if record.levelno == logging.CRITICAL:
			record.msg = f"{LEVEL_COLORS[logging.CRITICAL]}{record.msg}{RESET}"
		if record.levelno == logging.WARNING:
			record.msg = f"{LEVEL_COLORS[logging.WARNING]}{record.msg}{RESET}"

		return super().format(record)


def _supports_color() -> bool:
	if os.environ.get("NO_COLOR"):
		return False
	if os.environ.get("FORCE_COLOR"):
		return True
	return sys.stdout.isatty()


def _file_formatter():
	return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def get_log_formatter(format: str = "%(levelname)s %(message)s"):
	if _supports_color():
		return ColorFormatter(format)

	return logging.Formatter(format)


def setup_logging(log_file: str | None = None, level_console=logging.INFO) -> None:
	root = logging.getLogger("xviv")
	if root.handlers:
		return

	root.setLevel(logging.DEBUG)

	ch = logging.StreamHandler(sys.stdout)
	ch.setLevel(level_console)
	ch.setFormatter(get_log_formatter())
	root.addHandler(ch)

	if log_file:
		os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
		fh = logging.FileHandler(log_file, mode="w")
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(_file_formatter())
		root.addHandler(fh)
