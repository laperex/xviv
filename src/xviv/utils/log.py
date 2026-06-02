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

COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_DIM = "\033[2m"

COLOR_MAGENTA: str = LEVEL_COLORS[logging.CRITICAL]
COLOR_YELLOW: str = LEVEL_COLORS[logging.WARNING]


class ColorFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		record = copy.copy(record)
		color = LEVEL_COLORS.get(record.levelno, "")
		record.levelname = f"{color}{COLOR_BOLD}{record.levelname}{COLOR_RESET}"
		record.name = f"{COLOR_DIM}{record.name}{COLOR_RESET}"
		if record.levelno == logging.ERROR:
			record.msg = f"{LEVEL_COLORS[logging.ERROR]}{record.msg}{COLOR_RESET}"
		elif record.levelno == logging.CRITICAL:
			record.msg = f"{LEVEL_COLORS[logging.CRITICAL]}{record.msg}{COLOR_RESET}"
		elif record.levelno == logging.WARNING:
			record.msg = f"{LEVEL_COLORS[logging.WARNING]}{record.msg}{COLOR_RESET}"
		return super().format(record)


def _supports_color() -> bool:
	if os.environ.get("NO_COLOR"):
		return False
	if os.environ.get("FORCE_COLOR"):
		return True
	return sys.stdout.isatty()


def _file_formatter() -> logging.Formatter:
	return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def get_log_formatter(format: str = "%(levelname)s %(message)s") -> logging.Formatter:
	if _supports_color():
		return ColorFormatter(format)
	return logging.Formatter(format)


def setup_logging(log_file: str | None = None, level_console: int = logging.INFO) -> None:
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
