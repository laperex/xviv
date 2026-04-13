
import importlib.resources
import logging
import os
import subprocess
import typing

from xviv import config
from xviv import utils

logger = logging.getLogger(__name__)


_vitis_env_cache: typing.Optional[dict[str, str]] = None

def _get_vitis_env(cfg: dict) -> dict[str, str]:
	global _vitis_env_cache
	if _vitis_env_cache is None:
		vitis_path = config._get_vitis_path(cfg)
		settings_sh = os.path.join(vitis_path, "settings64.sh")
		_vitis_env_cache = utils._shell_env(settings_sh)
		_vitis_env_cache['PATH'] += f":{vitis_path}/gnu/microblaze/lin/bin"
		logger.debug("Vivado environment sourced from %s", settings_sh)
	return _vitis_env_cache


def _xsct_bin(cfg: dict) -> str:
	vitis_path = config._get_vitis_path(cfg)
	return os.path.join(vitis_path, "bin", "xsct")


def _find_xsct_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "xviv_xsct.tcl"
	with importlib.resources.as_file(ref) as path:
		return str(path)


def run_xsct(cfg: dict, tcl_script: str, args: list[str]) -> None:
	xsct_bin = _xsct_bin(cfg)
	cmd = [xsct_bin, tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	subprocess.run(cmd, check=True)


def run_xsct_live(cfg: dict, tcl_script: str, args: list[str]) -> None:
	xsct_bin = _xsct_bin(cfg)
	cmd = [xsct_bin, tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	try:
		subprocess.run(cmd, check=True)
	except KeyboardInterrupt:
		logger.info("jtag-monitor stopped by user")
