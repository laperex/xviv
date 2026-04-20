import importlib.resources
import logging
import os
import subprocess
import sys
import typing

from xviv.config.model import ProjectConfig

logger = logging.getLogger(__name__)


def find_xsct_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "xsct.tcl"
	with importlib.resources.as_file(ref) as path:
		return str(path)


def run_xsct(cfg: ProjectConfig, tcl_script: str, args: list[str]) -> None:
	cmd = [_xsct_bin(cfg), tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	subprocess.run(cmd, check=True)


def run_xsct_live(cfg: ProjectConfig, tcl_script: str, args: list[str]) -> None:
	cmd = [_xsct_bin(cfg), tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))

	try:
		subprocess.run(cmd, check=True)
	except KeyboardInterrupt:
		logger.info("jtag-monitor stopped by user")


_vitis_env_cache: typing.Optional[dict[str, str]] = None

def get_vitis_env(cfg: ProjectConfig) -> dict[str, str]:
	global _vitis_env_cache
	if _vitis_env_cache is None:
		settings_sh = os.path.join(cfg.vitis.path, "settings64.sh")
		_vitis_env_cache = _shell_env(settings_sh)
		_vitis_env_cache['PATH'] += f":{cfg.vitis.path}/gnu/microblaze/lin/bin"
		logger.debug("Vitis environment sourced from %s", settings_sh)
	return _vitis_env_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xsct_bin(cfg: ProjectConfig) -> str:
	return os.path.join(cfg.vitis.path, "bin", "xsct")


def _shell_env(source_file: str) -> dict[str, str]:
	if not os.path.isfile(source_file):
		sys.exit(f"ERROR: Vitis settings not found: {source_file}")

	result = subprocess.run(
		["bash", "-c", f'source "{source_file}" && env -0'],
		capture_output=True,
		text=True,
		check=True,
	)

	env = {}
	for entry in result.stdout.split("\0"):
		if "=" in entry:
			k, _, v = entry.partition("=")
			env[k] = v
	return env