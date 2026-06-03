import copy
import logging
import os
import sys

from xviv.utils.theme import theme_cfg


class ColorFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		record = copy.copy(record)

		record.levelname = theme_cfg.bold(theme_cfg.level(record.levelname, record.levelno))
		record.name = theme_cfg.dim(record.name)

		if record.levelno in [logging.ERROR, logging.CRITICAL, logging.WARNING]:
			theme_cfg.level(record.msg, record.levelno)

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
