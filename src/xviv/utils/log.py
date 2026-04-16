import logging
import os
import sys

def _setup_logging(log_file: str = "", level_console=logging.INFO) -> None:
	root = logging.getLogger("xviv")
	root.setLevel(logging.DEBUG)
	fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")

	ch = logging.StreamHandler(sys.stdout)
	ch.setLevel(level_console)
	ch.setFormatter(fmt)
	root.addHandler(ch)

	if log_file:
		os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
		fh = logging.FileHandler(log_file, mode="a")
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(fmt)
		root.addHandler(fh)