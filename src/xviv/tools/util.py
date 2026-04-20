import importlib.resources
import os
import shutil
import sys

_HINT = """
ERROR: '{tool}' not found on PATH.
Source the Vivado settings script to add it to PATH, e.g.:
	source <Vivado install dir>/settings64.sh
	(typically /tools/Xilinx/Vivado/<version>/settings64.sh)
"""

def find_vivado_dir_path() -> str:
    vivado_bin = shutil.which("vivado")
    if not vivado_bin:
        sys.exit(_HINT.format(tool='vivado'))
    return os.path.dirname(os.path.dirname(os.path.realpath(vivado_bin)))

def find_vitis_dir_path() -> str:
    xsct_bin = shutil.which("xsct")
    if not xsct_bin:
        sys.exit(_HINT.format(tool='xsct'))
    return os.path.dirname(os.path.dirname(os.path.realpath(xsct_bin)))

def find_vivado_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "vivado.tcl"

	with importlib.resources.as_file(ref) as path:
		return str(path)

def find_xsct_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "xsct.tcl"
	with importlib.resources.as_file(ref) as path:
		return str(path)