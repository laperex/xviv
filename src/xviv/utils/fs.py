import glob
import os
import subprocess
import sys


def shell_env(source_file: str) -> dict[str, str]:
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


def _resolve_globs(patterns: list[str], base: str) -> list[str]:
	files: list[str] = []
	for pat in patterns:
		full_pat = os.path.join(base, pat)
		hits = sorted(glob.glob(full_pat, recursive=True))
		files.extend(os.path.abspath(h) for h in hits if os.path.isfile(h))
	return files


def _tcl_list(items: list[str]) -> str:
	if not items:
		return "[list]"
	return "[list " + " ".join(f'"{i}"' for i in items) + "]"

