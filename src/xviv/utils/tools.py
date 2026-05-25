import logging
import os
import shutil
import subprocess
import sys

from xviv.utils import error

logger = logging.getLogger(__name__)

# Environment variable that points to the Vivado/Vitis settings64.sh script.
# When set, xviv will source it automatically if the tools are not on PATH.
SETTINGS_ENV_VAR = "XVIV_VIVADO_SOURCE_SCRIPT"

_TOOL_NOT_FOUND_HINT = """\
ERROR: '{tool}' not found on PATH.
Source the Vivado settings script to add it to PATH, e.g.:
\tsource <install_dir>/settings64.sh
\t(typically /tools/Xilinx/Vivado/<version>/settings64.sh)
Or let xviv source it automatically by setting:
\texport {env_var}=/tools/Xilinx/Vivado/<version>/settings64.sh
"""

# Track which settings scripts have already been sourced so we don't re-run them.
_settings_sourced: set[str] = set()

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_dotenv(path: str = ".env") -> None:
	try:
		with open(path) as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#"):
					continue
				# Strip optional "export " prefix
				if line.startswith("export "):
					line = line[len("export ") :]
				if "=" not in line:
					continue
				key, _, val = line.partition("=")
				key = key.strip()
				val = val.strip()
				if key and key not in os.environ:
					os.environ[key] = val
	except FileNotFoundError:
		pass


def _source_settings(settings_path: str) -> None:
	if settings_path in _settings_sourced:
		return

	if not os.path.isfile(settings_path):
		raise error.SettingsFileNotFoundError(settings_path)

	logger.debug("Sourcing settings script: %s", settings_path)

	result = subprocess.run(
		["bash", "-c", f'source "{settings_path}" && env -0'],
		capture_output=True,
		text=True,
	)

	if result.returncode != 0 or not result.stdout:
		raise error.SettingsSourceError(settings_path, result.stderr)

	# env -0 produces NUL-delimited KEY=VALUE entries; split on NUL and parse.
	new_vars = 0
	for entry in result.stdout.split("\0"):
		if "=" not in entry:
			continue
		key, _, value = entry.partition("=")
		if os.environ.get(key) != value:
			os.environ[key] = value
			new_vars += 1

	logger.debug("Sourced %s - %d environment variable(s) updated", settings_path, new_vars)
	_settings_sourced.add(settings_path)


def _ensure_tool_on_path(tool: str) -> None:
	if shutil.which(tool):
		return

	if not shutil.which("bash"):
		raise error.BashNotFoundError()

	_load_dotenv()

	settings_path = os.environ.get(SETTINGS_ENV_VAR, "").strip()
	if not settings_path:
		raise error.SettingsEnvUnsetError(tool, SETTINGS_ENV_VAR)

	_source_settings(settings_path)


def _find_tool_dir(tool: str) -> str:
	_ensure_tool_on_path(tool)

	tool_bin = shutil.which(tool)
	if not tool_bin:
		raise error.ToolBinaryNotFoundError(tool, _TOOL_NOT_FOUND_HINT, SETTINGS_ENV_VAR)

	# Follow symlinks then walk up two levels: bin/<tool> -> bin -> <install_root>
	return os.path.dirname(os.path.dirname(os.path.realpath(tool_bin)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_vivado_dir_path(exit_on_fail: bool = True) -> str | None:
	try:
		return _find_tool_dir("vivado")

	except error.SettingsEnvUnsetError as e:
		if exit_on_fail:
			logger.error(e)
			sys.exit(1)

	return None


def find_vitis_dir_path(exit_on_fail: bool = True) -> str | None:
	try:
		return _find_tool_dir("xsct")

	except error.SettingsEnvUnsetError as e:
		if exit_on_fail:
			logger.error(e)
			sys.exit(1)

	return None
