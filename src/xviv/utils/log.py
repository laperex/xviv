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


def _setup_logging(log_file: str = "", level_console=logging.INFO) -> None:
	root = logging.getLogger("xviv")
	if root.handlers:
		return

	root.setLevel(logging.DEBUG)

	plain_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
	color_fmt = ColorFormatter("%(levelname)s %(message)s")

	ch = logging.StreamHandler(sys.stdout)
	ch.setLevel(level_console)
	ch.setFormatter(color_fmt if _supports_color() else plain_fmt)
	root.addHandler(ch)

	if log_file:
		os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
		fh = logging.FileHandler(log_file, mode="a")
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(plain_fmt)  # ← plain, always
		root.addHandler(fh)
