import logging
import os
import subprocess
import tempfile

from xviv.config.project import XvivConfig

logger = logging.getLogger(__name__)


def run_xsct(cfg: XvivConfig, config_tcl: str, args: list[str] = []) -> None:
	config_tcl_path = None

	with tempfile.NamedTemporaryFile(
		mode="w", suffix="_xsct_config.tcl", delete=False, prefix="xviv_"
	) as tmp:
		tmp.write(config_tcl)
		config_tcl_path = tmp.name
	
	if config_tcl_path is None:
		#! ConfigPathInvalid
		raise RuntimeError("ERROR: config_tcl_path is invalid (None)")

	if cfg.get_vivado().dry_run:
		return

	cmd = [_xsct_bin(cfg), config_tcl_path, *args]
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
	return os.path.join(cfg.get_vitis().path, "bin", "xsct")
