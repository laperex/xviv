import contextlib
import logging
import os
import subprocess
import sys
import tempfile

from xviv.config.project import XvivConfig
from xviv.utils.process import run_tool
from xviv.utils.tools import find_vitis_dir_path

logger = logging.getLogger(__name__)


def run_xsct(cfg: XvivConfig, config_tcl: str, args: list[str] = []) -> None:
	config_tcl_path: str | None = None
	try:
		with tempfile.NamedTemporaryFile(mode="w", suffix="_xsct_config.tcl", delete=False, prefix="xviv_") as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		cmd = [cfg.get_vitis().xsct_bin, config_tcl_path, *args]

		try:
			run_tool(cmd, cwd=os.getcwd(), dry_run=cfg.dry_run)
		except subprocess.CalledProcessError as e:
			sys.exit(e.returncode)
		except FileNotFoundError:
			try:
				find_vitis_dir_path(exit_on_fail=True)
			finally:
				raise

	finally:
		if config_tcl_path and not cfg.dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)


def run_xsct_live(cfg: XvivConfig, tcl_script: str, args: list[str] = []) -> None:
	cmd = [cfg.get_vitis().xsct_bin, tcl_script, *args]
	try:
		run_tool(cmd, cwd=os.getcwd(), dry_run=cfg.dry_run)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)
	except KeyboardInterrupt:
		logger.info("xsct-live stopped by user")
	except FileNotFoundError:
		try:
			find_vitis_dir_path(exit_on_fail=True)
		finally:
			raise
