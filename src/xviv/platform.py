import logging
import os
import re
import glob
import sys
import typing

from xviv import config
from xviv.vivado import _get_vivado_path

logger = logging.getLogger(__name__)

def _resolve_platform_cfg(cfg: dict, plat_name: str) -> dict:
	plat_list = cfg.get("platform", [])
	plat_cfg  = next((p for p in plat_list if p["name"] == plat_name), None)
	if plat_cfg is None:
		sys.exit(
			f"ERROR: Platform '{plat_name}' not found in [[platform]] entries.\n"
			f"  Available: {[p['name'] for p in plat_list]}"
		)
	return plat_cfg


def _resolve_app_cfg(cfg: dict, app_name: str) -> dict:
	app_list = cfg.get("app", [])
	app_cfg  = next((a for a in app_list if a["name"] == app_name), None)
	if app_cfg is None:
		sys.exit(
			f"ERROR: App '{app_name}' not found in [[app]] entries.\n"
			f"  Available: {[a['name'] for a in app_list]}"
		)
	return app_cfg


def _platform_paths(
	cfg: dict,
	project_dir: str,
	build_dir: str,
	plat_cfg: dict,
) -> tuple[str, str]:
	name = plat_cfg["name"]

	if "xsa" in plat_cfg:
		xsa = os.path.abspath(os.path.join(project_dir, plat_cfg["xsa"]))
		stem = os.path.splitext(xsa)[0]
		bit  = stem + ".bit"
		if not os.path.exists(bit):
			candidates = sorted(glob.glob(os.path.join(os.path.dirname(xsa), "*.bit")))
			if candidates:
				bit = candidates[0]
				logger.debug("Bitstream resolved via glob: %s", bit)
		return xsa, bit

	if "synth_top" in plat_cfg:
		top      = plat_cfg["synth_top"]
		synth_dir = os.path.join(build_dir, "synth", top)
		xsa = os.path.join(synth_dir, f"{top}.xsa")
		bit = os.path.join(synth_dir, f"{top}.bit")
		return xsa, bit

	sys.exit(
		f"ERROR: Platform '{name}' must specify either 'xsa' or 'synth_top' in project.toml"
	)


def _bsp_dir(build_dir: str, plat_name: str) -> str:
	return os.path.join(build_dir, "bsp", plat_name)


def _app_dir(build_dir: str, app_name: str) -> str:
	return os.path.join(build_dir, "app", app_name)


def _find_elf(app_out_dir: str, app_name: str) -> typing.Optional[str]:
	candidates = [
		os.path.join(app_out_dir, "Debug", f"{app_name}.elf"),
		os.path.join(app_out_dir, f"{app_name}.elf"),
	]
	for c in candidates:
		if os.path.exists(c):
			return c
	hits = sorted(glob.glob(os.path.join(app_out_dir, "**", "*.elf"), recursive=True))
	return hits[0] if hits else None


def _mb_tool(cfg: dict, tool: str) -> str:
	vivado_path = _get_vivado_path(cfg)
	return os.path.join(
		vivado_path, "gnu", "microblaze", "lin", "bin",
		f"microblaze-xilinx-elf-{tool}",
	)


def _hw_server(cfg: dict) -> str:
	return cfg.get("vivado", {}).get("hw_server", "localhost:3121")

def _transform_app_makefile(path: str):
	content = open(path, "rt").read()

	content = re.sub(
		r'(patsubst\s+%\.\w+,\s*)(?!build/)%.o',
		r'\1build/%.o',
		content
	)

	content = re.sub(
		r'(?<!build/)%.o(:%\.[cSs])',
		r'build/%.o\1',
		content
	)

	content = re.sub(
		r'(build/%.o:%\.[cSs]\n)(?!\t@mkdir)',
		r'\1\t@mkdir -p $(dir $@)\n',
		content
	)

	open(path, 'wt').write(content)