import logging
import typing
import os
import sys
import tomllib
import glob

logger = logging.getLogger(__name__)

DEFAULT_VIVADO_PATH = "/opt/Xilinx/Vivado/2024.1"
DEFAULT_VITIS_PATH = "/opt/Xilinx/Vitis/2024.1"

DEFAULT_BUILD_DIR = "build"
DEFAULT_BUILD_IP_REPO = "build/ip"
DEFAULT_BUILD_BD_DIR = "build/bd"
DEFAULT_BUILD_WRAPPER_DIR = "build/wrapper"

def load_config(path: str) -> dict:
	path = os.path.abspath(path)
	if not os.path.isfile(path):
		sys.exit(f"ERROR: Config file not found - {path}")
	with open(path, "rb") as fh:
		cfg = tomllib.load(fh)
	fpga = cfg.get("fpga", {})
	has_default = isinstance(fpga.get("part"), str) and bool(fpga["part"])
	has_named   = any(isinstance(v, dict) and v.get("part") for v in fpga.values())
	if not has_default and not has_named:
		sys.exit(
			"ERROR: project.toml must define at least one FPGA target:\n"
			"  [fpga] part = '...'              (default, used when no fpga = key present)\n"
			"  [fpga.<name>] part = '...'       (named target, referenced via fpga = '<name>')"
		)
	return cfg


def _resolve_fpga(cfg: dict, name: typing.Optional[str]) -> dict:
	fpga_section = cfg.get("fpga", {})

	if not name:
		result = {k: v for k, v in fpga_section.items() if not isinstance(v, dict)}
		if not result.get("part"):
			sys.exit(
				"ERROR: No fpga = '<name>' specified and no default [fpga] part found.\n"
				"  Either add  [fpga] part = '...'  or set  fpga = '<name>'  in the entry."
			)
		return result

	named = fpga_section.get(name)
	if not isinstance(named, dict):
		available = [k for k, v in fpga_section.items() if isinstance(v, dict)]
		sys.exit(
			f"ERROR: FPGA target '{name}' not found in project.toml.\n"
			f"  Available named targets : {available}\n"
			f"  Define it as            : [fpga.{name}]  part = '...'"
		)
	if not named.get("part"):
		sys.exit(f"ERROR: [fpga.{name}] must define  part = '...'")
	return named


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

def generate_config_tcl(
	cfg: dict,
	base_dir: str,
	*,
	ip_name: typing.Optional[str] = None,
	bd_name: typing.Optional[str] = None,
	top_name: typing.Optional[str] = None,
	bd_export_path: typing.Optional[str] = None,
) -> str:
	lines = []

	max_threads = cfg.get("vivado", {}).get("max_threads", 8)
	lines.append(f"set_param general.maxThreads {max_threads}")

	fpga_ref: typing.Optional[str] = None
	if ip_name:
		_e: dict[str, typing.Any] = next((i for i in cfg.get("ip",        []) if i["name"] == ip_name),  {})
		fpga_ref = _e.get("fpga")
	elif bd_name:
		_e = next((b for b in cfg.get("bd",        []) if b["name"] == bd_name),  {})
		fpga_ref = _e.get("fpga")
	elif top_name:
		_e = next((s for s in cfg.get("synthesis", []) if s["top"]  == top_name), {})
		fpga_ref = _e.get("fpga")

	fpga       = _resolve_fpga(cfg, fpga_ref)
	part       = fpga["part"]
	board_part = fpga.get("board_part", "")
	board_repo = fpga.get("board_repo", "")

	logger.debug("FPGA target: %s  part=%s", fpga_ref or "<default>", part)

	if board_repo:
		lines.append(f'set_param board.repoPaths [list "{board_repo}"]')

	lines.append(f'set xviv_fpga_part  "{part}"')
	lines.append(f'set xviv_board_part "{board_part}"')
	lines.append(f'set xviv_board_repo "{board_repo}"')

	build_cfg   = cfg.get("build", {})
	build_dir   = os.path.abspath(os.path.join(base_dir, build_cfg.get("dir",         DEFAULT_BUILD_DIR)))
	ip_repo     = os.path.abspath(os.path.join(base_dir, build_cfg.get("ip_repo",     DEFAULT_BUILD_IP_REPO)))
	bd_dir      = os.path.abspath(os.path.join(base_dir, build_cfg.get("bd_dir",      DEFAULT_BUILD_BD_DIR)))
	wrapper_dir = os.path.abspath(os.path.join(base_dir, build_cfg.get("wrapper_dir", DEFAULT_BUILD_WRAPPER_DIR)))

	lines.append(f'set xviv_build_dir   "{build_dir}"')
	lines.append(f'set xviv_ip_repo     "{ip_repo}"')
	lines.append(f'set xviv_bd_dir      "{bd_dir}"')
	lines.append(f'set xviv_wrapper_dir "{wrapper_dir}"')

	sources_cfg   = cfg.get("sources", {})
	rtl_files     = _resolve_globs(sources_cfg.get("rtl",     []), base_dir)
	wrapper_files = _resolve_globs(sources_cfg.get("wrapper", []), base_dir)

	lines.append(f"set xviv_rtl_files     {_tcl_list(rtl_files)}")
	lines.append(f"set xviv_wrapper_files {_tcl_list(wrapper_files)}")

	if ip_name:
		ip_list = cfg.get("ip", [])
		ip_cfg  = next((i for i in ip_list if i["name"] == ip_name), None)
		if ip_cfg is None:
			sys.exit(f"ERROR: IP '{ip_name}' not found in project.toml [[ip]] entries")
		hooks = ip_cfg.get("hooks", "")
		if hooks:
			hooks = os.path.abspath(os.path.join(base_dir, hooks))

		ip_rtl_files = _resolve_globs(ip_cfg.get("rtl", []), base_dir)

		lines += [
			f'set xviv_ip_name    "{ip_cfg["name"]}"',
			f'set xviv_ip_vendor  "{ip_cfg.get("vendor",  "user.org")}"',
			f'set xviv_ip_library "{ip_cfg.get("library", "user")}"',
			f'set xviv_ip_version "{ip_cfg.get("version", "1.0")}"',
			f'set xviv_ip_top     "{ip_cfg.get("top", f"{ip_cfg["name"]}_wrapper")}"',
			f'set xviv_ip_rtl     "{_tcl_list(ip_rtl_files) if ip_rtl_files else _tcl_list(rtl_files)}"',
			f'set xviv_ip_hooks   "{hooks}"',
		]

	if bd_name:
		bd_list = cfg.get("bd", [])
		bd_cfg  = next((b for b in bd_list if b["name"] == bd_name), None)
		if bd_cfg is None:
			sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

		hooks = bd_cfg.get("hooks", "")
		if hooks:
			hooks = os.path.abspath(os.path.join(base_dir, hooks))

		if bd_export_path:
			export_tcl = bd_export_path
		else:
			raw = bd_cfg.get("export_tcl", f"scripts/bd/{bd_name}.tcl")
			export_tcl = os.path.abspath(os.path.join(base_dir, raw))

		lines += [
			f'set xviv_bd_name       "{bd_cfg["name"]}"',
			f'set xviv_bd_hooks      "{hooks}"',
			f'set xviv_bd_export_tcl "{export_tcl}"',
		]

	if top_name:
		synth_list  = cfg.get("synthesis", {})
		synth_cfg   = next((b for b in synth_list if b["top"] == top_name), None)

		if synth_cfg is None:
			sys.exit(f"ERROR: Synthesis Top '{top_name}' not found in project.toml [[bd]] entries")

		synth_hooks = synth_cfg.get("hooks", "")

		if synth_hooks:
			synth_hooks = os.path.abspath(os.path.join(base_dir, synth_hooks))

		lines.append(f'set xviv_synth_hooks "{synth_hooks}"')

		constr_files = _resolve_globs(synth_cfg.get("constrs", []), base_dir)
		lines.append(f"set xviv_constr_files  {_tcl_list(constr_files)}")

	return "\n".join(lines) + "\n"
