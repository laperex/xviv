import os
import shutil
import subprocess
import sys

# def find_vivado_script() -> str:
# 	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "vivado.tcl"

# 	with importlib.resources.as_file(ref) as path:
# 		return str(path)

# def find_xsct_script() -> str:
# 	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "xsct.tcl"
# 	with importlib.resources.as_file(ref) as path:
# 		return str(path)

_HINT = """\
ERROR: '{tool}' not found on PATH.
Source the Vivado settings script to add it to PATH, e.g.:
	source <install dir>/settings64.sh
	(typically /tools/Xilinx/<Vivado>/<version>/settings64.sh)
Or let xviv source it automatically:
	export XVIV_VIVADO_SOURCE_SCRIPT=<Vivado install dir>/settings64.sh
"""

_settings_sourced: set[str] = set()
_sourced_env: dict[str, str] = {}

def _source_settings(settings_path: str) -> None:
	if settings_path in _settings_sourced:
		return
	if not os.path.isfile(settings_path):
		sys.exit(f"ERROR: settings file not found: {settings_path!r}")

	result = subprocess.run(
		["bash", "-c", f'source "{settings_path}" && env -0'],
		capture_output=True,
		text=True,
	)
	if result.returncode != 0 or not result.stdout:
		sys.exit(f"ERROR: failed to source {settings_path!r}:\n{result.stderr}")

	sourced_env = dict(
		entry.partition("=")[::2]
		for entry in result.stdout.split("\0")
		if "=" in entry
	)

	for k, v in sourced_env.items():
		if os.environ.get(k) != v:
			os.environ[k] = v

	_settings_sourced.add(settings_path)

def _load_dotenv(path: str = ".env") -> None:
	"""Load KEY=VALUE pairs from a .env file into os.environ (no-op if absent)."""
	try:
		with open(path) as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				key, _, val = line.partition("=")
				key = key.strip()
				if key and key not in os.environ:
					os.environ[key] = val
	except FileNotFoundError:
		pass

def _source_settings_from_env(tool: str) -> None:
	if not shutil.which("bash"):
		sys.exit("ERROR: bash is required but not found on PATH")

	if shutil.which(tool):
		return

	_load_dotenv()

	script_env_var = "XVIV_VIVADO_SOURCE_SCRIPT"
	settings_path = os.environ.get(script_env_var, "")
	if not settings_path:
		sys.exit(
			f"ERROR: '{tool}' not found on PATH and {script_env_var} is not set.\n"
			"Set it to the path of your settings script, e.g.:\n"
			f"  export {script_env_var}=/tools/Xilinx/<version>/settings64.sh"
		)
	_source_settings(settings_path)


def _find_tool_dir(tool: str) -> str:
	_source_settings_from_env(tool)
	tool_bin = shutil.which(tool)
	if not tool_bin:
		sys.exit(_HINT.format(tool=tool))
	return os.path.dirname(os.path.dirname(os.path.realpath(tool_bin)))


def find_vivado_dir_path() -> str:
	return _find_tool_dir("vivado")


def find_vitis_dir_path() -> str:
	return _find_tool_dir("xsct")

def get_vitis_env() -> dict:
    env = os.environ.copy()
    extra_paths = [
        f"{find_vitis_dir_path()}/gnu/microblaze/lin/bin",      # mb-gcc lives here
        f"{find_vitis_dir_path()}/bin",
        f"{find_vitis_dir_path()}/lib/lnx64.o",
    ]
    env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")

    return env


def mb_tool(tool: str) -> str:
    return os.path.join(
        find_vitis_dir_path(), "gnu", "microblaze", "lin", "bin",
        f"microblaze-xilinx-elf-{tool}",
    )