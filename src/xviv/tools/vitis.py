import contextlib
import logging
import os
import subprocess
import sys
import tempfile

from xviv.config.project import XvivConfig
from xviv.utils.process import run_tool

logger = logging.getLogger(__name__)


def run_xsct(cfg: XvivConfig, config_tcl: str, args: list[str] = []) -> None:
	config_tcl_path: str | None = None
	try:
		with tempfile.NamedTemporaryFile(mode="w", suffix="_xsct_config.tcl", delete=False, prefix="xviv_") as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		cmd = [_xsct_bin(cfg), config_tcl_path, *args]

		try:
			run_tool(cmd, cwd=os.getcwd(), dry_run=cfg.get_vivado().dry_run)
		except subprocess.CalledProcessError as e:
			sys.exit(e.returncode)

	finally:
		if config_tcl_path and not cfg.get_vivado().dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)


def run_xsct_live(cfg: XvivConfig, tcl_script: str, args: list[str] = []) -> None:
	cmd = [_xsct_bin(cfg), tcl_script, *args]
	try:
		run_tool(cmd, cwd=os.getcwd(), dry_run=cfg.get_vivado().dry_run)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)
	except KeyboardInterrupt:
		logger.info("xsct-live stopped by user")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xsct_bin(cfg: XvivConfig) -> str:
	return os.path.join(cfg.get_vivado().path, "bin", "xsct")
