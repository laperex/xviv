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

# sources
def _get_sim_files(cfg: dict, project_dir: str):
	return _resolve_globs(cfg.get("sources", {}).get("sim", []), project_dir)

# build artifacts paths

def _get_build_dir(cfg: dict, project_dir: str) -> str:
	return os.path.join(project_dir, cfg.get("build", {}).get("dir", DEFAULT_BUILD_DIR))

def _get_dcp_path(cfg: dict, project_dir: str, top_name: str, dcp_name: str) -> str:
	return os.path.abspath(os.path.join(_get_build_dir(cfg, project_dir), top_name, f"{dcp_name}.dcp"))

def _get_wrapper_dir(cfg: dict, project_dir: str) -> str:
	return os.path.abspath(os.path.join(project_dir, cfg.get("build", {}).get("wrapper_dir", DEFAULT_BUILD_WRAPPER_DIR)))

# control fifo - waveforms

def _get_control_fifo_path(cfg: dict, project_dir: str, top_name: str) -> str:
	return os.path.join(_get_build_dir(cfg, project_dir), "xviv", top_name, "control.fifo")

def _get_xlib_work_dir(cfg: dict, project_dir: str, top_name: str) -> str:
	return os.path.join(_get_build_dir(cfg, project_dir), "elab", top_name)

# platform

## platform

def _get_platform_cfg(cfg: dict, plat_name: str) -> dict:
	plat_list = cfg.get("platform", [])
	plat_cfg = next((p for p in plat_list if p["name"] == plat_name), None)

	if plat_cfg is None:
		sys.exit(
			f"ERROR: Platform '{plat_name}' not found in [[platform]] entries.\n"
			f"  Available: {[p['name'] for p in plat_list]}"
		)

	return plat_cfg

def _get_platform_dir(cfg, project_dir, plat_name: str) -> str:
	return os.path.join(_get_build_dir(cfg, project_dir), "bsp", plat_name)

def _get_platform_paths(cfg: dict, project_dir: str, plat_name: str) -> tuple[str, str]:
	plat_cfg = _get_platform_cfg(cfg, project_dir)

	if "xsa" in plat_cfg:
		xsa = os.path.abspath(os.path.join(project_dir, plat_cfg["xsa"]))
		stem = os.path.splitext(xsa)[0]
		bit = stem + ".bit"

		if not os.path.exists(bit):
			candidates = sorted(glob.glob(os.path.join(os.path.dirname(xsa), "*.bit")))

			if candidates:
				bit = candidates[0]
				logger.debug("Bitstream resolved via glob: %s", bit)

		return xsa, bit

	if "synth_top" in plat_cfg:
		top = plat_cfg["synth_top"]
		synth_dir = os.path.join(_get_build_dir(cfg, project_dir), "synth", top)

		xsa = os.path.join(synth_dir, f"{top}.xsa")
		bit = os.path.join(synth_dir, f"{top}.bit")

		return xsa, bit

	sys.exit(f"ERROR: Platform '{plat_name}' must specify either 'xsa' or 'synth_top' in project.toml")

def _get_platform_hw_server(cfg: dict) -> str:
	return cfg.get("vivado", {}).get("hw_server", "localhost:3121")

## app

def _get_app_cfg(cfg: dict, app_name: str) -> dict:
	app_list = cfg.get("app", [])
	app_cfg = next((a for a in app_list if a["name"] == app_name), None)

	if app_cfg is None:
		sys.exit(
			f"ERROR: App '{app_name}' not found in [[app]] entries.\n"
			f"  Available: {[a['name'] for a in app_list]}"
		)

	return app_cfg

def _get_app_src_dir(cfg: dict, app_name: str) -> str:
	return os.path.abspath(_get_app_cfg(cfg, app_name).get("src_dir", f"srcs/sw/{app_name}"))

def _get_app_dir(cfg: dict, project_dir: str, app_name: str) -> str:
	app_dir = os.path.join(_get_build_dir(cfg, project_dir), "app", app_name)
	
	if not os.path.isdir(app_dir):
		sys.exit(
			f"ERROR: App directory not found: {app_dir}\n"
			f"  Run: xviv create-app --app {app_name}"
		)

	return app_dir

# hooks

## ip

def _get_ip_cfg(cfg: dict, ip_name: str) -> dict:
	ip_cfg = next((b for b in cfg.get("ip", {}) if b["name"] == ip_name), None)

	if ip_cfg is None:
		sys.exit(f"ERROR: IP '{ip_name}' not found in project.toml [[ip]] entries")

	return ip_cfg

def _get_ip_version(ip_cfg: dict) -> str:
	return ip_cfg.get("version", "1.0")

def _get_ip_rtl_files(ip_cfg: dict, project_dir: str) -> tuple[str, list[str]]:
	return ip_cfg.get("top", ip_cfg["name"]), _resolve_globs(ip_cfg.get("rtl", []), project_dir)

def _get_ip_hooks(ip_cfg: dict) -> str:
	return ip_cfg.get("hooks", f"scripts/ip/{ip_cfg['name']}_{_get_ip_version(ip_cfg)}.tcl")

## bd

def _get_bd_cfg(cfg: dict, bd_name: str) -> dict:
	bd_cfg = next((b for b in cfg.get("bd", {}) if b["name"] == bd_name), None)

	if bd_cfg is None:
		sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

	return bd_cfg

def _get_bd_hooks(bd_cfg: dict) -> str:
	return bd_cfg.get("hooks", f"scripts/bd/{bd_cfg['name']}_hooks.tcl")

def _get_bd_export_tcl(bd_cfg: dict) -> str:
	return bd_cfg.get("export_tcl", f"scripts/bd/{bd_cfg['name']}.tcl")

## synth

def _get_synth_cfg(cfg: dict, top_name: str) -> dict:
	synth_cfg = next((b for b in cfg.get("synthesis", {}) if b["top"] == top_name), None)
	
	if synth_cfg is None:
		sys.exit(f"ERROR: Synthesis Top '{top_name}' not found in project.toml [[bd]] entries")

	return synth_cfg

def _get_synth_hooks(synth_cfg: dict) -> str:
	return synth_cfg.get("hooks", f"scripts/synth/{synth_cfg['top']}.tcl")



# vivado

def _get_vivado_path(cfg: dict) -> str:
	return cfg.get("vivado", {}).get("path", DEFAULT_VIVADO_PATH)

def _get_vivado_mode(cfg: dict) -> str:
	return cfg.get("vivado", {}).get("mode", "batch")

# vitis

def _get_vitis_path(cfg: dict) -> str:
	return cfg.get("vitis", {}).get("path", DEFAULT_VITIS_PATH)

# config

def load_config(path: str) -> dict:
	path = os.path.abspath(path)
	if not os.path.isfile(path):
		sys.exit(f"ERROR: Config file not found - {path}")
	with open(path, "rb") as fh:
		cfg = tomllib.load(fh)
	fpga = cfg.get("fpga", {})
	has_default = isinstance(fpga.get("part"), str) and bool(fpga["part"])
	has_named = any(isinstance(v, dict) and v.get("part") for v in fpga.values())
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
	
	# if ip_name:
		

	# fpga_ref: typing.Optional[str] = None
	# # if ip_name:
	# # 	_e: dict[str, typing.Any] = next((i for i in cfg.get("ip",        []) if i["name"] == ip_name),  {})
	# # 	fpga_ref = _e.get("fpga")

	# # elif bd_name:
	# # 	_e = next((b for b in cfg.get("bd",        []) if b["name"] == bd_name),  {})
	# # 	fpga_ref = _e.get("fpga")

	# # elif top_name:
	# # 	_e = next((s for s in cfg.get("synthesis", []) if s["top"] == top_name), {})
	# # 	fpga_ref = _e.get("fpga")

	# fpga = _resolve_fpga(cfg, fpga_ref)
	# part = fpga["part"]
	# board_part = fpga.get("board_part", "")
	# board_repo = fpga.get("board_repo", "")

	# logger.debug("FPGA target: %s  part=%s", fpga_ref or "<default>", part)

	# if board_repo:
	# 	lines.append(f'set_param board.repoPaths [list "{board_repo}"]')

	# lines.append(f'set xviv_fpga_part  "{part}"')
	# lines.append(f'set xviv_board_part "{board_part}"')
	# lines.append(f'set xviv_board_repo "{board_repo}"')

	# build_cfg = cfg.get("build", {})
	# build_dir = os.path.abspath(os.path.join(base_dir, build_cfg.get("dir",         DEFAULT_BUILD_DIR)))
	# ip_repo = os.path.abspath(os.path.join(base_dir, build_cfg.get("ip_repo",     DEFAULT_BUILD_IP_REPO)))
	# bd_dir = os.path.abspath(os.path.join(base_dir, build_cfg.get("bd_dir",      DEFAULT_BUILD_BD_DIR)))
	# wrapper_dir = os.path.abspath(os.path.join(base_dir, build_cfg.get("wrapper_dir", DEFAULT_BUILD_WRAPPER_DIR)))

	# lines.append(f'set xviv_build_dir   "{build_dir}"')
	# lines.append(f'set xviv_ip_repo     "{ip_repo}"')
	# lines.append(f'set xviv_bd_dir      "{bd_dir}"')
	# lines.append(f'set xviv_wrapper_dir "{wrapper_dir}"')

	# sources_cfg = cfg.get("sources", {})
	# rtl_files = _resolve_globs(sources_cfg.get("rtl",     []), base_dir)
	# wrapper_files = _resolve_globs([f"{wrapper_dir}/**/*"], base_dir)

	# lines.append(f"set xviv_rtl_files     {_tcl_list(rtl_files)}")
	# lines.append(f"set xviv_wrapper_files {_tcl_list(wrapper_files)}")

	# if synth_report_all:
	# 	synth_report_synth = True
	# 	synth_report_post = True
	# 	synth_report_place = True
	# 	synth_report_rout = True

	# # lines.append(f"set xviv_synth_out_of_context {int(synth_out_of_context_synth or False)}")
	# lines.append(f"set xviv_synth_report_synth {int(synth_report_synth or False)}")
	# lines.append(f"set xviv_synth_report_post {int(synth_report_post or False)}")
	# lines.append(f"set xviv_synth_report_place {int(synth_report_place or False)}")
	# lines.append(f"set xviv_synth_report_route {int(synth_report_rout or False)}")
	# lines.append(f"set xviv_synth_generate_netlist {int(synth_generate_netlist or False)}")

	# if ip_name:
	# 	ip_list = cfg.get("ip", [])
	# 	ip_cfg = next((i for i in ip_list if i["name"] == ip_name), None)
	# 	if ip_cfg is None:
	# 		sys.exit(f"ERROR: IP '{ip_name}' not found in project.toml [[ip]] entries")
	# 	hooks = ip_cfg.get("hooks", "")
	# 	if hooks:
	# 		hooks = os.path.abspath(os.path.join(base_dir, hooks))

	# 	ip_rtl_files = _resolve_globs(ip_cfg.get("rtl", []), base_dir)

	# 	lines += [
	# 		f'set xviv_ip_name    "{ip_cfg["name"]}"',
	# 		f'set xviv_ip_vendor  "{ip_cfg.get("vendor",  "user.org")}"',
	# 		f'set xviv_ip_library "{ip_cfg.get("library", "user")}"',
	# 		f'set xviv_ip_version "{ip_cfg.get("version", "1.0")}"',
	# 		f'set xviv_ip_top     "{ip_cfg.get("top", f"{ip_cfg["name"]}_wrapper")}"',
	# 		f'set xviv_ip_rtl     "{_tcl_list(ip_rtl_files) if ip_rtl_files else _tcl_list(rtl_files)}"',
	# 		f'set xviv_ip_hooks   "{hooks}"',
	# 	]

	# 	xdc_files = _resolve_globs(ip_cfg.get("xdc", []), base_dir)
	# 	xdc_ooc_files = _resolve_globs(ip_cfg.get("xdc_ooc", []), base_dir)
	# 	# lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_ooc_files if synth_out_of_context_synth else xdc_files)}")
	# 	lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_files)}")

	# if bd_name:
	# 	bd_list = cfg.get("bd", [])
	# 	bd_cfg = next((b for b in bd_list if b["name"] == bd_name), None)
	# 	if bd_cfg is None:
	# 		sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

	# 	hooks = bd_cfg.get("hooks", f"scripts/bd/{bd_name}_hooks.tcl")
	# 	if hooks:
	# 		hooks = os.path.abspath(os.path.join(base_dir, hooks))

	# 	if bd_export_path:
	# 		export_tcl = bd_export_path
	# 	else:
	# 		raw = bd_cfg.get("export_tcl", f"scripts/bd/{bd_name}.tcl")
	# 		export_tcl = os.path.abspath(os.path.join(base_dir, raw))

	# 	lines += [
	# 		f'set xviv_bd_name       "{bd_cfg["name"]}"',
	# 		f'set xviv_bd_hooks      "{hooks}"',
	# 		f'set xviv_bd_export_tcl "{export_tcl}"',
	# 	]

	# 	xdc_files = _resolve_globs(bd_cfg.get("xdc", []), base_dir)
	# 	xdc_ooc_files = _resolve_globs(bd_cfg.get("xdc_ooc", []), base_dir)

	# 	# lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_ooc_files if synth_out_of_context_synth else xdc_files)}")
	# 	lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_files)}")

	# 	lines.append(f"set xviv_rtl_files     {_tcl_list([os.path.join(build_dir, "bd", bd_name, f"{bd_name}.bd")])}")
	# 	lines.append(f"set xviv_wrapper_files {_tcl_list([os.path.join(build_dir, "wrapper", f"{bd_name}_wrapper.v")])}")

	# if top_name:
	# 	synth_list = cfg.get("synthesis", {})
	# 	synth_cfg = next((b for b in synth_list if b["top"] == top_name), None)

	# 	if synth_cfg is None:
	# 		sys.exit(f"ERROR: Synthesis Top '{top_name}' not found in project.toml [[bd]] entries")

	# 	synth_hooks = synth_cfg.get("hooks", "")

	# 	if synth_hooks:
	# 		synth_hooks = os.path.abspath(os.path.join(base_dir, synth_hooks))

	# 	lines.append(f'set xviv_synth_hooks "{synth_hooks}"')

	# 	xdc_files = _resolve_globs(synth_cfg.get("xdc", []), base_dir)
	# 	xdc_ooc_files = _resolve_globs(synth_cfg.get("xdc_ooc", []), base_dir)
	# 	# lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_ooc_files if synth_out_of_context_synth else xdc_files)}")
	# 	lines.append(f"set xviv_xdc_files  {_tcl_list(xdc_files)}")

	return "\n".join(lines) + "\n"
