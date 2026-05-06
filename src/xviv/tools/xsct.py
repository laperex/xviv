import logging
import os
import subprocess

from xviv.config.project import XvivConfig

logger = logging.getLogger(__name__)


def run_xsct(cfg: XvivConfig, tcl_script: str, args: list[str]) -> None:
	cmd = [_xsct_bin(cfg), tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	subprocess.run(cmd, check=True)


def run_xsct_live(cfg: XvivConfig, tcl_script: str, args: list[str]) -> None:
	cmd = [_xsct_bin(cfg), tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))

	try:
		subprocess.run(cmd, check=True)
	except KeyboardInterrupt:
		logger.info("jtag-monitor stopped by user")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xsct_bin(cfg: XvivConfig) -> str:
	return os.path.join(cfg.vitis.path, "bin", "xsct")
