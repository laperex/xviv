#!/usr/bin/env python3
"""
xviv  -  FPGA project controller for Vivado / Vitis
Reads project.toml and drives Vivado, xsct, or standalone Xilinx tools.

Usage:
xviv [--config project.toml] <command> [options]

Vivado-backed commands:
create-ip    --ip   <n>
edit-ip      --ip   <n>
ip-config    --ip   <n>
create-bd    --bd   <n>
edit-bd      --bd   <n>
generate-bd  --bd   <n>
export-bd    --bd   <n>
bd-config    --bd   <n>
synthesis    --top  <module>
synth-config --top  <module>
simulate     --top  <sim_top>  [--so libdpi]  [--dpi-lib ./build/libs]
open-dcp     --top  <module>   [--dcp post_synth]

xsct-backed commands (MicroBlaze / Vitis):
create-platform  --platform <n>
platform-build   --platform <n>
create-app       --app <n>  [--platform <n>]  [--template <t>]
app-build        --app <n>  [--info]
program          (--bitstream <path> | --platform <n>)  [--elf <path> | --app <n>]
processor        (--reset | --status)
jtag-monitor     --uart

Standalone commands:
open-wdb        --top <sim_top>
reload-wdb      --top <sim_top>
open-snapshot   --top <sim_top>
reload-snapshot --top <sim_top>
"""

import argparse
import glob as _glob
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import argcomplete
from typing import Optional
import stat
import importlib.resources

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("xviv")


def _setup_logging(log_file: str) -> None:
	logger.setLevel(logging.DEBUG)
	fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")

	ch = logging.StreamHandler(sys.stdout)
	ch.setLevel(logging.INFO)
	ch.setFormatter(fmt)
	logger.addHandler(ch)

	if log_file:
		os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
		fh = logging.FileHandler(log_file, mode="a")
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(fmt)
		logger.addHandler(fh)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_sha_tag() -> tuple[str, bool, str]:
	"""Return (sha, dirty, tag) for the current git HEAD.

	sha   - 7-char short SHA, e.g. "abc1234"
	dirty - True if there are uncommitted changes in the working tree
	tag   - ready-to-use filename suffix: "abc1234" or "abc1234_dirty"

	Never raises; falls back to ("unknown", False, "unknown") if git is
	unavailable or the directory is not a git repository.
	"""
	try:
		sha = subprocess.check_output(
			["git", "rev-parse", "--short=7", "HEAD"],
			stderr=subprocess.DEVNULL,
		).decode().strip()
	except Exception:
		return "unknown", False, "unknown"

	try:
		status = subprocess.check_output(
			["git", "status", "--porcelain"],
			stderr=subprocess.DEVNULL,
		).decode().strip()
		dirty = len(status) > 0
	except Exception:
		dirty = False

	tag = f"{sha}_dirty" if dirty else sha
	return sha, dirty, tag


# ---------------------------------------------------------------------------
# TOML loading & validation
# ---------------------------------------------------------------------------

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


def _resolve_fpga(cfg: dict, name: Optional[str]) -> dict:
	"""Return the fpga config dict for the given named target (or the default).

	The [fpga] section supports two layouts that can coexist:

	# Flat default (backward-compatible)
	[fpga]
	part       = "xc7z020clg400-1"
	board_part = "..."          # optional
	board_repo = "..."          # optional

	# Named targets
	[fpga.pynq_z2]
	part       = "xc7z020clg400-1"
	board_part = "tul.com.tw:pynq-z2:part0:1.0"

	[fpga.custom_fpga]
	part = "xc7k325tffg900-2"

	When name is None (no fpga = key in the [[bd]] / [[synthesis]] / [[ip]]
	entry) the flat default is used.  Sub-table dicts are excluded from the
	default so they don't pollute the returned dict with nested tables.
	"""
	fpga_section = cfg.get("fpga", {})

	if not name:
		# Default: scalar fields only (strip any [fpga.<name>] sub-tables)
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
		hits = sorted(_glob.glob(full_pat, recursive=True))
		files.extend(os.path.abspath(h) for h in hits if os.path.isfile(h))
	return files


def _tcl_list(items: list[str]) -> str:
	if not items:
		return "[list]"
	return "[list " + " ".join(f'"{i}"' for i in items) + "]"


# ---------------------------------------------------------------------------
# Symlink helper
# ---------------------------------------------------------------------------

def _atomic_symlink(target: str, link_path: str) -> None:
	"""Create or replace link_path -> target atomically using a temp name.

	target is stored as a relative path so the symlink is portable when
	the repo is checked out at a different absolute location.
	"""
	link_dir   = os.path.dirname(link_path)
	tmp_link   = os.path.join(link_dir, f".tmp_{os.path.basename(link_path)}")
	rel_target = os.path.relpath(target, link_dir)
	if os.path.lexists(tmp_link):
		os.unlink(tmp_link)
	os.symlink(rel_target, tmp_link)
	os.replace(tmp_link, link_path)


# ---------------------------------------------------------------------------
# Config TCL generation
# ---------------------------------------------------------------------------

def generate_config_tcl(
	cfg: dict,
	base_dir: str,
	*,
	ip_name: Optional[str] = None,
	bd_name: Optional[str] = None,
	top_name: Optional[str] = None,
	# When set, overrides the default export_tcl path derived from TOML.
	# Used by export-bd to inject the SHA-versioned path before calling Vivado.
	bd_export_path: Optional[str] = None,
) -> str:
	lines = ["# Generated by xviv - do not edit manually", ""]

	# Threading
	max_threads = cfg.get("vivado", {}).get("max_threads", 8)
	lines.append(f"set_param general.maxThreads {max_threads}")

	# FPGA / board
	# Determine which named FPGA target (if any) the active entry requests,
	# then resolve it to a concrete {part, board_part, board_repo} dict.
	fpga_ref: Optional[str] = None
	if ip_name:
		_e       = next((i for i in cfg.get("ip",        []) if i["name"] == ip_name),  {})
		fpga_ref = _e.get("fpga")
	elif bd_name:
		_e       = next((b for b in cfg.get("bd",        []) if b["name"] == bd_name),  {})
		fpga_ref = _e.get("fpga")
	elif top_name:
		_e       = next((s for s in cfg.get("synthesis", []) if s["top"]  == top_name), {})
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

	# Build dirs
	build_cfg   = cfg.get("build", {})
	build_dir   = os.path.abspath(os.path.join(base_dir, build_cfg.get("dir",         "build")))
	ip_repo     = os.path.abspath(os.path.join(base_dir, build_cfg.get("ip_repo",     "build/ip")))
	bd_dir      = os.path.abspath(os.path.join(base_dir, build_cfg.get("bd_dir",      "build/bd")))
	wrapper_dir = os.path.abspath(os.path.join(base_dir, build_cfg.get("wrapper_dir", "srcs/rtl")))

	lines.append(f'set xviv_build_dir   "{build_dir}"')
	lines.append(f'set xviv_ip_repo     "{ip_repo}"')
	lines.append(f'set xviv_bd_dir      "{bd_dir}"')
	lines.append(f'set xviv_wrapper_dir "{wrapper_dir}"')

	# Sources
	sources_cfg   = cfg.get("sources", {})
	rtl_files     = _resolve_globs(sources_cfg.get("rtl",     []), base_dir)
	wrapper_files = _resolve_globs(sources_cfg.get("wrapper", []), base_dir)

	lines.append(f"set xviv_rtl_files     {_tcl_list(rtl_files)}")
	lines.append(f"set xviv_wrapper_files {_tcl_list(wrapper_files)}")

	# IP config
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

	# BD config
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

	# Synth config
	if top_name:
		synth_list  = cfg.get("synthesis", {})
		synth_cfg   = next((b for b in synth_list if b["top"] == top_name), None)
		synth_hooks = synth_cfg.get("hooks", "")

		if synth_hooks:
			synth_hooks = os.path.abspath(os.path.join(base_dir, synth_hooks))

		lines.append(f'set xviv_synth_hooks "{synth_hooks}"')

		constr_files = _resolve_globs(synth_cfg.get("constrs", []), base_dir)
		lines.append(f"set xviv_constr_files  {_tcl_list(constr_files)}")

	return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Vivado runner
# ---------------------------------------------------------------------------

def run_vivado(
	cfg: dict,
	tcl_script: str,
	command: str,
	extra_args: list[str],
	config_tcl_content: str,
) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	vivado_bin  = os.path.join(vivado_path, "bin", "vivado")
	mode        = cfg.get("vivado", {}).get("mode", "batch")

	with tempfile.NamedTemporaryFile(
		mode="w", suffix="_config.tcl", delete=False, prefix="xviv_"
	) as tmp:
		tmp.write(config_tcl_content)
		config_tcl_path = tmp.name

	try:
		cmd = [
			vivado_bin,
			"-mode",    mode,
			"-nolog", "-nojournal", "-notrace", "-quiet",
			"-source",  tcl_script,
			"-tclargs", command, config_tcl_path,
			*extra_args,
		]
		logger.info("Running: %s", " ".join(cmd))
		subprocess.run(cmd, check=True)
	finally:
		os.unlink(config_tcl_path)


def run_vivado_xvlog(
	cfg: dict,
	target_dir: str,
	fileset: list[str],
	xsim_lib: str = "xv_work",
) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	xvlog_bin   = os.path.join(vivado_path, "bin", "xvlog")

	fileset.append(os.path.join(vivado_path, "data/verilog/src/glbl.v"))

	cmd = [xvlog_bin, "-sv", "-incr", "-work", xsim_lib, *fileset]
	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)
	subprocess.run(cmd, check=True, cwd=target_dir)


def run_vivado_xelab(
	cfg: dict,
	target_dir: str,
	top: str,
	timescale: str = "1ns/1ps",
	xsim_lib: str = "xv_work",
) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	xelab_bin   = os.path.join(vivado_path, "bin", "xelab")

	cmd = [
		xelab_bin,
		f"{xsim_lib}.{top}",
		f"{xsim_lib}.glbl",
		"-L", "unifast_ver",
		"-L", "unisims_ver",
		"-L", "unimacro_ver",
		"-L", "secureip",
		"-debug", "typical",
		"-mt", "20",
		"-s", top,
		"-timescale", timescale,
	]
	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)
	subprocess.run(cmd, check=True, cwd=target_dir)


def run_vivado_xsim(
	cfg: dict,
	target_dir: str,
	top: str,
	config_tcl_content: str,
) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	xsim_bin    = os.path.join(vivado_path, "bin", "xsim")

	try:
		with tempfile.NamedTemporaryFile(
			mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_"
		) as tmp:
			tmp.write(config_tcl_content)
			config_tcl_path = tmp.name

		cmd = [
			xsim_bin,
			"--stats", top,
			"--wdb", os.path.join(target_dir, "waveform.wdb"),
			"-t", config_tcl_path,
		]
		logger.info("Running: %s", " ".join(cmd))
		os.makedirs(target_dir, exist_ok=True)
		subprocess.run(cmd, check=True, cwd=target_dir)
	finally:
		os.unlink(config_tcl_path)


# ===========================================================================
# xsct helpers  (MicroBlaze / Vitis workflow)
# ===========================================================================

def _vitis_env(settings_sh: str) -> dict[str, str]:
    if not os.path.isfile(settings_sh):
        sys.exit(f"ERROR: Vitis settings not found: {settings_sh}")

    result = subprocess.run(
        ["bash", "-c", f'source "{settings_sh}" && env -0'],
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

_vitis_env_cache: Optional[dict[str, str]] = None

def _get_vitis_env(cfg: dict) -> dict[str, str]:
	global _vitis_env_cache
	if _vitis_env_cache is None:
		vitis_path  = cfg.get("vitis", {}).get("path", "/opt/Xilinx/Vitis/2024.1")
		settings_sh  = os.path.join(vitis_path, "settings64.sh")
		_vitis_env_cache = _vitis_env(settings_sh)
		_vitis_env_cache['PATH'] += f":{vitis_path}/gnu/microblaze/lin/bin"
		logger.debug("Vivado environment sourced from %s", settings_sh)
	return _vitis_env_cache

def _xsct_bin(cfg: dict) -> str:
	"""Resolve the xsct binary.  xsct ships alongside Vivado in the same
	installation tree, so we derive its path from [vivado] path in the TOML."""
	vitis_path = cfg.get("vitis", {}).get("path", "/opt/Xilinx/Vitis/2024.1")
	return os.path.join(vitis_path, "bin", "xsct")

def _find_xsct_script() -> str:
	"""Locate the packaged xviv_xsct.tcl dispatcher."""
	ref = importlib.resources.files("xviv") / "scripts" / "xviv_xsct.tcl"
	with importlib.resources.as_file(ref) as path:
		return str(path)


def run_xsct(cfg: dict, tcl_script: str, args: list[str]) -> None:
	"""Run xsct <tcl_script> [args...] and block until it exits."""
	xsct_bin = _xsct_bin(cfg)
	cmd = [xsct_bin, tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	subprocess.run(cmd, check=True)


def run_xsct_live(cfg: dict, tcl_script: str, args: list[str]) -> None:
	"""Run xsct without capturing output - used for interactive/streaming
	commands like jtag-monitor where stdout must flow directly to the terminal
	in real time.  Ctrl-C cleanly terminates xsct."""
	xsct_bin = _xsct_bin(cfg)
	cmd = [xsct_bin, tcl_script, *args]
	logger.info("Running: %s", " ".join(cmd))
	try:
		subprocess.run(cmd, check=True)
	except KeyboardInterrupt:
		logger.info("jtag-monitor stopped by user")


# ---------------------------------------------------------------------------
# Platform / app TOML resolution helpers
# ---------------------------------------------------------------------------

def _resolve_platform_cfg(cfg: dict, plat_name: str) -> dict:
	"""Return the [[platform]] entry matching plat_name or exit with an error."""
	plat_list = cfg.get("platform", [])
	plat_cfg  = next((p for p in plat_list if p["name"] == plat_name), None)
	if plat_cfg is None:
		sys.exit(
			f"ERROR: Platform '{plat_name}' not found in [[platform]] entries.\n"
			f"  Available: {[p['name'] for p in plat_list]}"
		)
	return plat_cfg


def _resolve_app_cfg(cfg: dict, app_name: str) -> dict:
	"""Return the [[app]] entry matching app_name or exit with an error."""
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
	"""Return (xsa_path, bitstream_path) for the given platform config dict.

	Priority:
	1. Explicit  xsa  key  -> xsa is that path; bitstream = same stem + .bit
		(falls back to any *.bit in the same directory when the stem match
		does not exist, e.g. when the bitstream carries a SHA tag).
	2. synth_top key       -> both paths are the symlinks written by 'synthesis'.
	"""
	name = plat_cfg["name"]

	if "xsa" in plat_cfg:
		xsa = os.path.abspath(os.path.join(project_dir, plat_cfg["xsa"]))
		stem = os.path.splitext(xsa)[0]
		bit  = stem + ".bit"
		if not os.path.exists(bit):
			candidates = sorted(_glob.glob(os.path.join(os.path.dirname(xsa), "*.bit")))
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


def _find_elf(app_out_dir: str, app_name: str) -> Optional[str]:
	"""Locate the compiled ELF within the app build directory.

	Checks the conventional Debug/ subdirectory first, then falls back to a
	recursive glob.  Returns None when no ELF is found.
	"""
	candidates = [
		os.path.join(app_out_dir, "Debug", f"{app_name}.elf"),
		os.path.join(app_out_dir, f"{app_name}.elf"),
	]
	for c in candidates:
		if os.path.exists(c):
			return c
	hits = sorted(_glob.glob(os.path.join(app_out_dir, "**", "*.elf"), recursive=True))
	return hits[0] if hits else None


def _mb_tool(cfg: dict, tool: str) -> str:
	"""Resolve a MicroBlaze GNU toolchain binary shipped with Vivado."""
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	return os.path.join(
		vivado_path, "gnu", "microblaze", "lin", "bin",
		f"microblaze-xilinx-elf-{tool}",
	)


def _hw_server(cfg: dict) -> str:
	"""Return the hw_server URL from config, defaulting to localhost."""
	return cfg.get("vivado", {}).get("hw_server", "localhost:3121")


# ===========================================================================
# Hooks file generators
# ===========================================================================

def generate_ip_hooks(
	cfg: dict,
	project_dir: str,
	ip_name: str,
	*,
	exist_ok: bool = False,
) -> Optional[str]:
	"""Generate a starter hooks file for the named IP."""
	ip_list = cfg.get("ip", [])
	ip_cfg  = next((i for i in ip_list if i["name"] == ip_name), None)
	if ip_cfg is None:
		sys.exit(f"ERROR: IP '{ip_name}' not found in project.toml [[ip]] entries")

	version    = ip_cfg.get("version", "1.0")
	hooks_path = ip_cfg.get("hooks", f"scripts/ip/{ip_name}_{version}.tcl")
	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		if exist_ok:
			logger.debug("IP hooks already exist, skipping - %s", hooks_path)
			return None
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# =============================================================================
# {os.path.basename(hooks_path)}
# Hook procs called by xviv create-ip for {ip_name}
# Leave a proc body empty if you don't need it.
# =============================================================================

# Called after the IP edit project is opened.
# Add your RTL source files to the edit project here.
proc ipx_add_files {{}} {{
	add_files [glob -nocomplain ./srcs/rtl/*.sv]
	add_files [glob -nocomplain ./srcs/rtl/*.v]
}}

# Called after ipx::merge_project_changes.
# Use for any custom post-merge fixups.
proc ipx_merge_changes {{}} {{

}}

# Called after the default axis/aximm inference.
# Add inferences for any other bus standards your IP uses.
proc ipx_infer_bus_interfaces {{}} {{
	# example:
	# ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]
}}

# Called after HDL parameters are added to the IP GUI.
# Use to reorder, group, or add display conditions.
proc ipx_add_params {{}} {{
	# example:
	# ipgui::move_param -component [ipx::current_core] \\
	#     -order 0 [ipgui::get_guiparamspec -name "DATA_WIDTH" \\
	#     -component [ipx::current_core]] \\
	#     -parent [ipgui::get_pagespec -name "Page 0" -component [ipx::current_core]]
}}

# Called after bus interfaces are set up.
# Use to add custom memory maps beyond what xviv auto-generates.
proc ipx_add_memory_map {{}} {{

}}
""")
	logger.info("IP hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_bd_hooks(
	cfg: dict,
	project_dir: str,
	bd_name: str,
	*,
	exist_ok: bool = False,
) -> Optional[str]:
	bd_list = cfg.get("bd", [])
	bd_cfg  = next((b for b in bd_list if b["name"] == bd_name), None)
	if bd_cfg is None:
		sys.exit(f"ERROR: BD '{bd_name}' not found in project.toml [[bd]] entries")

	hooks_path = bd_cfg.get("hooks", f"scripts/bd/{bd_name}_hooks.tcl")
	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		if exist_ok:
			logger.debug("BD hooks already exist, skipping - %s", hooks_path)
			return None
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	export_tcl_abs = os.path.abspath(
		os.path.join(project_dir, bd_cfg.get("export_tcl", f"scripts/bd/{bd_name}.tcl"))
	)
	export_tcl_rel = os.path.relpath(export_tcl_abs, os.path.dirname(hooks_path))

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# =============================================================================
# {os.path.basename(hooks_path)}
# Hook procs called by xviv create-bd / edit-bd for {bd_name}
# =============================================================================
set ::_bd_design_tcl [file join [file dirname [info script]] "{export_tcl_rel}"]

proc bd_design_config {{ parentCell }} {{
	global _bd_design_tcl

	if {{[file exists $_bd_design_tcl]}} {{
		puts "INFO: Sourcing exported BD TCL - $_bd_design_tcl"
		source $_bd_design_tcl

		xviv_refresh_bd_addresses
		validate_bd_design
		save_bd_design
		exit 0

	}} else {{
		puts "INFO: No exported BD TCL found at $_bd_design_tcl"
		puts "INFO: Opening GUI for interactive design."
		puts "INFO: When done, run:  xviv export-bd --bd {bd_name}"
		start_gui
	}}
}}
""")
	logger.info("BD hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")
	return hooks_path


def generate_synth_hooks(cfg: dict, project_dir: str, top: str) -> None:
	synth_list = cfg.get("synthesis", {})
	synth_cfg  = next((b for b in synth_list if b["top"] == top), None)
	hooks_path = synth_cfg.get("hooks", f"scripts/synth/{top}.tcl")
	hooks_path = os.path.join(project_dir, hooks_path)

	if os.path.exists(hooks_path):
		sys.exit(
			f"ERROR: Hooks file already exists - {hooks_path}\n"
			"Delete it first if you want to regenerate."
		)

	os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
	with open(hooks_path, "w") as fh:
		fh.write(f"""\
# =============================================================================
# {os.path.basename(hooks_path)}
# Hook procs called by xviv synthesis for {top}
# Leave a proc body empty if you don't need it.
# =============================================================================

proc report_synth    {{}} {{ return 1 }}
proc report_place    {{}} {{ return 1 }}
proc report_route    {{}} {{ return 1 }}
proc report_netlists {{}} {{ return 1 }}

proc synth_pre {{}} {{}}
proc synth_post {{}} {{}}
proc place_post {{}} {{}}
proc route_post {{}} {{}}
proc bitstream_post {{}} {{}}
""")
	logger.info("Synthesis hooks file created -> %s", hooks_path)
	print(f"Edit: {hooks_path}")


# ===========================================================================
# Waveform helpers
# ===========================================================================

_XSIM_WDB_TCL = """
set xsi_sim_wdb_file  {wdb}
set xsi_sim_wcfg_file {wcfg}
set xviv_fifo_path    {fifo_path}
set xviv_ready        0

if {{[file exists $xsi_sim_wcfg_file]}} {{
	catch {{open_wave_config $xsi_sim_wcfg_file}}
}} else {{
	add_wave {top}
	save_wave_config $xsi_sim_wcfg_file
}}

set xviv_ready 1

set xviv_fifo_fh [open $xviv_fifo_path r+]
fconfigure $xviv_fifo_fh -blocking 0 -buffering line

proc _fifo_reopen {{}} {{
	global xviv_fifo_fh xviv_fifo_path
	catch {{close $xviv_fifo_fh}}
	set xviv_fifo_fh [open $xviv_fifo_path r+]
	fconfigure $xviv_fifo_fh -blocking 0 -buffering line
	fileevent  $xviv_fifo_fh readable _fifo_handle
}}

proc _fifo_handle {{}} {{
	global xviv_fifo_fh xviv_ready
	if {{!$xviv_ready}} {{ return }}

	if {{[eof $xviv_fifo_fh]}} {{
		fileevent $xviv_fifo_fh readable {{}}
		_fifo_reopen
		return
	}}

	set len [gets $xviv_fifo_fh cmd]
	if {{$len <= 0}} {{ return }}

	puts "xviv: $cmd"
	catch {{uplevel #0 $cmd}} result
	puts "xviv: -> $result"
}}

fileevent $xviv_fifo_fh readable _fifo_handle
puts "xviv: FIFO ready at $xviv_fifo_path"
"""


def _fifo_path(build_dir: str, top: str) -> str:
	return os.path.join(build_dir, "xviv", top, "control.fifo")


def _ensure_fifo(path: str) -> None:
	if os.path.exists(path):
		if not stat.S_ISFIFO(os.stat(path).st_mode):
			os.unlink(path)
			os.mkfifo(path)
	else:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		os.mkfifo(path)


def _fifo_send(path: str, command: str) -> None:
	try:
		fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
		with os.fdopen(fd, "w") as fh:
			fh.write(command + "\n")
	except OSError as e:
		logger.warning("FIFO send failed (%s) - is xsim running?", e)


def reload_wdb(build_dir: str, top: str) -> None:
	path = _fifo_path(build_dir, top)
	cmd = (
		"after 300 {"
		"set _wcfg [get_property FILE_PATH [current_wave_config]]; "
		"save_wave_config [current_wave_config];"
		"close_wave_config [current_wave_config];"
		"open_wave_database $xsi_sim_wdb_file; "
		"catch {open_wave_config $_wcfg}"
		"}"
	)
	logger.info("Reloading waveform: %s", path)
	_fifo_send(path, cmd)


def reload_snapshot(build_dir: str, top: str) -> None:
	path = _fifo_path(build_dir, top)
	cmd = (
		"set _wcfg [get_property FILE_PATH [current_wave_config]]; "
		"save_wave_config $_wcfg; "
		f"xsim {top};"
		"log_wave -recursive *; "
		"run all; "
		"open_wave_config $_wcfg"
	)
	logger.info("Reloading snapshot: %s", path)
	_fifo_send(path, cmd)


def open_wdb(cfg: dict, top: str, build_dir: str) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	xsim_bin    = os.path.join(vivado_path, "bin", "xsim")
	work_dir    = os.path.join(build_dir, "xviv", top)
	wdb_file    = "waveform.wdb"
	wcfg_file   = "waveform.wcfg"
	tcl_file    = os.path.join(work_dir, "waveform_config.tcl")

	os.makedirs(work_dir, exist_ok=True)
	fifo = _fifo_path(build_dir, top)
	_ensure_fifo(fifo)

	with open(tcl_file, "w") as fh:
		fh.write(_XSIM_WDB_TCL.format(
			wdb=wdb_file, wcfg=wcfg_file, top=top, fifo_path=fifo
		))

	proc = subprocess.Popen(
		[xsim_bin, wdb_file, "-t", tcl_file, "-g"],
		cwd=work_dir,
	)
	logger.info("xsim waveform PID: %d", proc.pid)


def open_snapshot(cfg: dict, top: str, build_dir: str) -> None:
	vivado_path = cfg.get("vivado", {}).get("path", "/opt/Xilinx/Vivado/2024.1")
	xsim_bin    = os.path.join(vivado_path, "bin", "xsim")
	work_dir    = os.path.join(build_dir, "xviv", top)
	wdb_file    = os.path.join(work_dir, "waveform.wdb")
	wcfg_file   = os.path.join(work_dir, "waveform.wcfg")
	tcl_file    = os.path.join(work_dir, "waveform_config.tcl")

	os.makedirs(work_dir, exist_ok=True)
	fifo = _fifo_path(build_dir, top)
	_ensure_fifo(fifo)

	with open(tcl_file, "w") as fh:
		fh.write(_XSIM_WDB_TCL.format(
			wdb=wdb_file, wcfg=wcfg_file, top=top, fifo_path=fifo
		))

	proc = subprocess.Popen(
		[xsim_bin, top, "-t", tcl_file, "-g"],
		cwd=work_dir,
	)
	logger.info("xsim waveform PID: %d", proc.pid)


# ===========================================================================
# CLI
# ===========================================================================

def _find_tcl_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "xviv.tcl"
	with importlib.resources.as_file(ref) as path:
		return str(path)

def _strip_bd_tcl(path: str) -> None:
	with open(path, "r") as f:
		data = f.read()
	start = data.find("set bCheckIPsPassed")
	end   = data.find("save_bd_design")
	if start == -1 or end == -1:
		raise RuntimeError(
			f"Could not find expected markers in exported BD TCL: {path}\n"
			f"  'set bCheckIPsPassed' found: {start != -1}\n"
			f"  'save_bd_design'     found: {end != -1}"
		)
	with open(path, "w") as f:
		f.write(data[start:end])

def _find_config(prefix, parsed_args, **kwargs) -> str:
	return getattr(parsed_args, "config", None) or "project.toml"

def _ip_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [ip["name"] for ip in cfg.get("ip", [])]
	except Exception:
		return []

def _bd_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [bd["name"] for bd in cfg.get("bd", [])]
	except Exception:
		return []

def _top_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s["top"] for s in cfg.get("synthesis", [])]
	except Exception:
		return []

def _dcp_stems_completer(prefix, parsed_args, **kwargs):
	try:
		cfg      = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		top      = getattr(parsed_args, "top", None)
		build_dir = cfg.get("build", {}).get("dir", "build")
		if not top:
			return ["post_synth", "post_place", "post_route"]
		stems = [
			os.path.splitext(os.path.basename(f))[0]
			for f in _glob.glob(os.path.join(build_dir, top, "*.dcp"))
		]
		return stems or ["post_synth", "post_place", "post_route"]
	except Exception:
		return ["post_synth", "post_place", "post_route"]

def _platform_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [p["name"] for p in cfg.get("platform", [])]
	except Exception:
		return []

def _app_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [a["name"] for a in cfg.get("app", [])]
	except Exception:
		return []


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)
	p.add_argument(
		"--config", "-c",
		default="project.toml",
		metavar="TOML",
		help="Project configuration file (default: project.toml)",
	)
	p.add_argument(
		"--log-file",
		default="",
		metavar="FILE",
		help="Append debug log to FILE",
	)

	sub = p.add_subparsers(dest="command", required=True)

	def _cmd(name: str, help_str: str):
		return sub.add_parser(name, help=help_str)

	# -- IP ------------------------------------------------------------------
	for name in ("create-ip", "edit-ip"):
		c = _cmd(name, f"{name} for the specified IP")
		c.add_argument(
			"--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
		).completer = _ip_names_completer

	c = _cmd("ip-config", "Generate a starter hooks file for an IP")
	c.add_argument(
		"--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
	).completer = _ip_names_completer

	# -- Block Design --------------------------------------------------------
	for name in ("create-bd", "edit-bd", "generate-bd"):
		c = _cmd(name, f"{name} for the specified Block Design")
		c.add_argument(
			"--bd", required=True, help="BD name as defined in [[bd]] TOML entry"
		).completer = _bd_names_completer

	c = _cmd("export-bd", "Export the current BD as a versioned re-runnable TCL script")
	c.add_argument("--bd", required=True, help="BD name as defined in [[bd]] TOML entry"
		).completer = _bd_names_completer

	c = _cmd("bd-config", "Generate a starter hooks file for a BD")
	c.add_argument("--bd", required=True, help="BD name as defined in [[bd]] TOML entry"
		).completer = _bd_names_completer

	# -- Implementation ------------------------------------------------------
	c = _cmd("synthesis", "Synthesise, place, route, and write bitstream")
	c.add_argument("--top", required=True, help="Top module name"
		).completer = _top_names_completer

	c = _cmd("synth-config", "Generate a starter hooks file for synthesis")
	c.add_argument("--top", required=True, help="Top module name"
		).completer = _top_names_completer

	# -- Simulation ----------------------------------------------------------
	c = _cmd("elaborate", "Compile and optionally run simulation")
	c.add_argument("--top", required=True, help="Simulation top module"
		).completer = _top_names_completer
	c.add_argument("--so",      default="", help="DPI shared library name (no path/extension)")
	c.add_argument("--dpi-lib", default="", help="Directory containing the DPI .so")
	c.add_argument("--run",     default="", help="Simulation run time, e.g. 1000ns")

	# -- Checkpoint ----------------------------------------------------------
	c = _cmd("open-dcp", "Open a checkpoint in Vivado GUI")
	c.add_argument("--top", required=True, help="Top module name (locates build/<top>/)"
		).completer = _top_names_completer
	c.add_argument("--dcp", default="post_synth", help="Checkpoint stem (default: post_synth)"
		).completer = _dcp_stems_completer

	c = _cmd("open-snapshot", "Open the simulation snapshot in xsim GUI")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("reload-snapshot", "Restart simulation snapshot")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("open-wdb", "Open the waveform database in xsim GUI")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	c = _cmd("reload-wdb", "Reload waveform window")
	c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

	# -----------------------------------------------------------------------
	# Vitis / MicroBlaze commands
	# -----------------------------------------------------------------------

	# -- Platform (BSP) ------------------------------------------------------
	c = _cmd(
		"create-platform",
		"Generate BSP from XSA using hsi (xsct). "
		"BSP is placed in build/bsp/<platform>.",
	)
	c.add_argument(
		"--platform", required=True,
		help="Platform name as defined in [[platform]] TOML entry",
	).completer = _platform_names_completer

	c = _cmd(
		"platform-build",
		"Compile the BSP with make -j<ncpu>.",
	)
	c.add_argument(
		"--platform", required=True,
		help="Platform name as defined in [[platform]] TOML entry",
	).completer = _platform_names_completer

	# -- Application ---------------------------------------------------------
	c = _cmd(
		"create-app",
		"Scaffold an application from a Vitis template using hsi (xsct). "
		"App is placed in build/app/<app>. "
		"If the BSP does not yet exist it is created automatically.",
	)
	c.add_argument(
		"--app", required=True,
		help="App name as defined in [[app]] TOML entry",
	).completer = _app_names_completer
	c.add_argument(
		"--platform", default="",
		help="Override the platform name specified in the [[app]] TOML entry",
	).completer = _platform_names_completer
	c.add_argument(
		"--template", default="",
		help="Override the app template (e.g. 'empty_application', 'hello_world')",
	)

	c = _cmd(
		"app-build",
		"Compile the application with make -j<ncpu>.",
	)
	c.add_argument(
		"--app", required=True,
		help="App name as defined in [[app]] TOML entry",
	).completer = _app_names_completer
	c.add_argument(
		"--info", action="store_true",
		help="Print ELF section sizes and headers after a successful build "
			"(uses microblaze-xilinx-elf-size and microblaze-xilinx-elf-objdump)",
	)

	# -- Program -------------------------------------------------------------
	c = _cmd(
		"program",
		"Download bitstream to FPGA, and optionally load an ELF. "
		"Requires hw_server running (Vivado Hardware Manager or standalone).",
	)
	bit_src = c.add_mutually_exclusive_group(required=True)
	bit_src.add_argument(
		"--bitstream", metavar="PATH",
		help="Explicit path to the .bit file to program",
	)
	bit_src.add_argument(
		"--platform", metavar="NAME",
		help="Derive bitstream path from [[platform]] TOML entry",
	).completer = _platform_names_completer

	elf_src = c.add_mutually_exclusive_group()
	elf_src.add_argument(
		"--elf", metavar="PATH",
		help="Explicit path to the .elf file to load",
	)
	elf_src.add_argument(
		"--app", metavar="NAME",
		help="Derive ELF path from [[app]] build directory",
	).completer = _app_names_completer

	# -- Processor -----------------------------------------------------------
	c = _cmd(
		"processor",
		"Control the embedded MicroBlaze processor via JTAG.",
	)
	proc_action = c.add_mutually_exclusive_group(required=True)
	proc_action.add_argument(
		"--reset", action="store_true",
		help="Soft-reset the processor (rst -processor then continue)",
	)
	proc_action.add_argument(
		"--status", action="store_true",
		help="Print target list, processor state, and key registers",
	)

	# -- JTAG monitor --------------------------------------------------------
	c = _cmd(
		"jtag-monitor",
		"Stream debug output from the embedded processor over JTAG. "
		"Requires the MDM IP in the Vivado design with JTAG UART enabled. "
		"Press Ctrl-C to stop.",
	)
	c.add_argument(
		"--uart", action="store_true", default=True,
		help="Stream JTAG UART output to stdout (default mode)",
	)

	return p


def main() -> None:
	parser = build_parser()
	# echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.zshrc
	argcomplete.autocomplete(parser)
	args   = parser.parse_args()

	cfg_path    = os.path.abspath(args.config)
	project_dir = os.path.dirname(cfg_path)
	os.chdir(project_dir)

	cfg = load_config(cfg_path)

	build_dir   = os.path.join(project_dir, cfg.get("build", {}).get("dir", "build"))
	default_log = os.path.join(build_dir, "xviv", "xviv.log")
	_setup_logging(args.log_file or default_log)

	tcl_script = _find_tcl_script()
	xsct_script = _find_xsct_script()
	cmd        = args.command

	# -- IP ------------------------------------------------------------------
	if cmd == "create-ip":
		config_tcl = generate_config_tcl(cfg, project_dir, ip_name=args.ip)
		run_vivado(cfg, tcl_script, "create_ip", [], config_tcl)

	elif cmd == "edit-ip":
		config_tcl = generate_config_tcl(cfg, project_dir, ip_name=args.ip)
		run_vivado(cfg, tcl_script, "edit_ip", [], config_tcl)

	elif cmd == "ip-config":
		generate_ip_hooks(cfg, project_dir, args.ip)

	# -- Block Design --------------------------------------------------------
	elif cmd == "create-bd":
		generate_bd_hooks(cfg, project_dir, args.bd, exist_ok=True)
		config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
		run_vivado(cfg, tcl_script, "create_bd", [], config_tcl)

	elif cmd == "edit-bd":
		config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
		run_vivado(cfg, tcl_script, "edit_bd", [], config_tcl)

	elif cmd == "generate-bd":
		config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
		run_vivado(cfg, tcl_script, "generate_bd", [], config_tcl)

	elif cmd == "export-bd":
		sha, dirty, tag = _git_sha_tag()

		bd_list = cfg.get("bd", [])
		bd_cfg  = next((b for b in bd_list if b["name"] == args.bd), None)
		if bd_cfg is None:
			sys.exit(f"ERROR: BD '{args.bd}' not found in project.toml [[bd]] entries")

		export_base = bd_cfg.get("export_tcl", f"scripts/bd/{args.bd}.tcl")
		export_base = os.path.abspath(os.path.join(project_dir, export_base))
		stem        = os.path.splitext(export_base)[0]
		versioned   = f"{stem}_{tag}.tcl"
		symlink     = export_base

		logger.info("BD export: sha=%s dirty=%s", sha, dirty)
		logger.info("BD export versioned: %s", versioned)
		logger.info("BD export symlink  : %s", symlink)

		if dirty:
			logger.warning(
				"Working tree is dirty - export tagged _dirty. "
				"Commit changes before a production export."
			)

		config_tcl = generate_config_tcl(
			cfg, project_dir,
			bd_name=args.bd,
			bd_export_path=versioned,
		)

		run_vivado(cfg, tcl_script, "export_bd", [], config_tcl)
		_strip_bd_tcl(versioned)

		_atomic_symlink(versioned, symlink)
		logger.info(
			"Symlink updated: %s -> %s",
			os.path.basename(symlink),
			os.path.basename(versioned),
		)
		print(f"Exported : {versioned}")
		print(f"Symlink  : {symlink} -> {os.path.basename(versioned)}")

	elif cmd == "bd-config":
		generate_bd_hooks(cfg, project_dir, args.bd)

	# -- Implementation ------------------------------------------------------
	elif cmd == "synthesis":
		_, _, tag  = _git_sha_tag()
		config_tcl = generate_config_tcl(cfg, project_dir, top_name=args.top)
		run_vivado(cfg, tcl_script, "synthesis", [args.top, tag], config_tcl)

	elif cmd == "synth-config":
		generate_synth_hooks(cfg, project_dir, args.top)

	elif cmd == "open-dcp":
		dcp_path = os.path.abspath(
			os.path.join(build_dir, args.top, f"{args.dcp}.dcp")
		)
		config_tcl = generate_config_tcl(cfg, project_dir)
		run_vivado(cfg, tcl_script, "open_dcp", [dcp_path], config_tcl)

	# -- Simulation ----------------------------------------------------------
	elif cmd == "elaborate":
		sim_build_dir = os.path.join(build_dir, "xviv", args.top)
		sources_cfg   = cfg.get("sources", {})
		sim_files     = _resolve_globs(sources_cfg.get("sim", []), project_dir)

		run_vivado_xvlog(cfg, sim_build_dir, sim_files)
		run_vivado_xelab(cfg, sim_build_dir, args.top)

		if args.run:
			x_simulate_tcl = f"""
				log_wave -recursive *
				run {args.run}
				exit
			"""
			run_vivado_xsim(cfg, sim_build_dir, args.top, x_simulate_tcl)

	elif cmd == "open-snapshot":
		open_snapshot(cfg, args.top, build_dir)

	elif cmd == "reload-snapshot":
		reload_snapshot(build_dir, args.top)

	elif cmd == "open-wdb":
		open_wdb(cfg, args.top, build_dir)

	elif cmd == "reload-wdb":
		reload_wdb(build_dir, args.top)

	# -----------------------------------------------------------------------
	# Vitis / MicroBlaze commands
	# -----------------------------------------------------------------------

	elif cmd == "create-platform":
		plat_cfg = _resolve_platform_cfg(cfg, args.platform)
		xsa, _   = _platform_paths(cfg, project_dir, build_dir, plat_cfg)
		bsp      = _bsp_dir(build_dir, args.platform)
		cpu      = plat_cfg["cpu"]
		os_name  = plat_cfg.get("os", "standalone")

		if not os.path.exists(xsa):
			sys.exit(
				f"ERROR: XSA not found: {xsa}\n"
				f"  Run 'xviv synthesis --top {plat_cfg.get('synth_top', '<top>')}' first."
			)

		logger.info("Creating BSP platform '%s'", args.platform)
		logger.info("  XSA    : %s", xsa)
		logger.info("  CPU    : %s", cpu)
		logger.info("  OS     : %s", os_name)
		logger.info("  BSP dir: %s", bsp)

		run_xsct(cfg, xsct_script, ["create_platform", xsa, cpu, os_name, bsp])

	elif cmd == "platform-build":
		plat_cfg = _resolve_platform_cfg(cfg, args.platform)
		bsp = _bsp_dir(build_dir, args.platform)

		env = _get_vitis_env(cfg)

		if not os.path.isdir(bsp):
			sys.exit(
				f"ERROR: BSP directory not found: {bsp}\n"
				f"  Run: xviv create-platform --platform {args.platform}"
			)

		logger.info("Building BSP: %s", bsp)
		subprocess.run(
			["make", f"-j{os.cpu_count() or 4}"],
			check=True,
			cwd=bsp,
			env=env
		)
		logger.info("BSP build complete")

	elif cmd == "create-app":
		app_cfg      = _resolve_app_cfg(cfg, args.app)
		plat_name    = args.platform or app_cfg["platform"]
		plat_cfg     = _resolve_platform_cfg(cfg, plat_name)
		xsa, _       = _platform_paths(cfg, project_dir, build_dir, plat_cfg)
		bsp          = _bsp_dir(build_dir, plat_name)
		app_out_dir  = _app_dir(build_dir, args.app)
		cpu          = plat_cfg["cpu"]
		os_name      = plat_cfg.get("os", "standalone")
		template     = args.template or app_cfg.get("template", "empty_application")
		src_dir      = app_cfg.get("src_dir", "")

		if not os.path.exists(xsa):
			sys.exit(
				f"ERROR: XSA not found: {xsa}\n"
				f"  Run synthesis for platform '{plat_name}' first."
			)

		# Auto-create BSP if absent
		if not os.path.isdir(bsp):
			logger.info("BSP not found - creating platform '%s' first", plat_name)
			run_xsct(cfg, xsct_script, ["create_platform", xsa, cpu, os_name, bsp])

		logger.info("Creating app '%s' from template '%s'", args.app, template)
		logger.info("  App dir : %s", app_out_dir)

		run_xsct(cfg, xsct_script, ["create_app", xsa, cpu, os_name, template, app_out_dir])

		# Overlay user source files into the generated app's src/ directory.
		if src_dir:
			abs_src = os.path.abspath(os.path.join(project_dir, src_dir))
			dst_src = os.path.join(app_out_dir, "src")
			if os.path.isdir(abs_src):
				os.makedirs(dst_src, exist_ok=True)
				for f in _glob.glob(os.path.join(abs_src, "**", "*"), recursive=True):
					if os.path.isfile(f):
						rel    = os.path.relpath(f, abs_src)
						dst    = os.path.join(dst_src, rel)
						os.makedirs(os.path.dirname(dst), exist_ok=True)
						shutil.copy2(f, dst)
						logger.info("  Copied: %s", rel)
			else:
				logger.warning("src_dir not found, skipping source overlay: %s", abs_src)

	elif cmd == "app-build":
		app_cfg     = _resolve_app_cfg(cfg, args.app)
		plat_name   = app_cfg["platform"]
		plat_cfg    = _resolve_platform_cfg(cfg, plat_name)
		bsp         = _bsp_dir(build_dir, plat_name)
		cpu         = plat_cfg["cpu"]
		app_out_dir = _app_dir(build_dir, args.app)

		if not os.path.isdir(app_out_dir):
			sys.exit(
				f"ERROR: App directory not found: {app_out_dir}\n"
				f"  Run: xviv create-app --app {args.app}"
			)

		bsp_include = os.path.join(bsp, cpu, "include")
		bsp_lib     = os.path.join(bsp, cpu, "lib")

		logger.info("Building app '%s'", args.app)
		subprocess.run(
			[
				"make", f"-j{os.cpu_count() or 4}",
				f"INCLUDEPATH=-I{bsp_include}",
				f"LIBPATH=-L{bsp_lib}",
			],
			check=True,
			cwd=app_out_dir,
		)
		logger.info("App build complete")

		if args.info:
			elf = _find_elf(app_out_dir, args.app)
			if elf:
				logger.info("ELF: %s", elf)
				print(f"\n=== ELF size: {os.path.basename(elf)} ===")
				subprocess.run([_mb_tool(cfg, "size"), elf])
				print(f"\n=== ELF sections: {os.path.basename(elf)} ===")
				subprocess.run([_mb_tool(cfg, "objdump"), "-h", elf])
			else:
				logger.warning("No ELF found in %s", app_out_dir)

	elif cmd == "program":
		server = _hw_server(cfg)

		# ---- Resolve bitstream ----
		if args.bitstream:
			bit = os.path.abspath(args.bitstream)
		else:
			plat_cfg = _resolve_platform_cfg(cfg, args.platform)
			_, bit   = _platform_paths(cfg, project_dir, build_dir, plat_cfg)

		if not os.path.exists(bit):
			sys.exit(f"ERROR: Bitstream not found: {bit}")

		# ---- Resolve ELF (optional) ----
		elf = ""
		if args.elf:
			elf = os.path.abspath(args.elf)
			if not os.path.exists(elf):
				sys.exit(f"ERROR: ELF not found: {elf}")
		elif args.app:
			app_cfg     = _resolve_app_cfg(cfg, args.app)
			app_out_dir = _app_dir(build_dir, args.app)
			elf         = _find_elf(app_out_dir, args.app) or ""
			if not elf:
				sys.exit(
					f"ERROR: No ELF found in {app_out_dir}\n"
					f"  Run: xviv app-build --app {args.app}"
				)

		logger.info("Programming FPGA")
		logger.info("  Bitstream : %s", bit)
		if elf:
			logger.info("  ELF       : %s", elf)
		logger.info("  hw_server : %s", server)

		run_xsct(cfg, xsct_script, ["program", bit, elf, server])

	elif cmd == "processor":
		server = _hw_server(cfg)
		if args.reset:
			logger.info("Resetting embedded processor via JTAG (%s)", server)
			run_xsct(cfg, xsct_script, ["processor_reset", server])
		elif args.status:
			run_xsct(cfg, xsct_script, ["processor_status", server])

	elif cmd == "jtag-monitor":
		server = _hw_server(cfg)
		logger.info("Starting JTAG UART monitor (Ctrl-C to stop)")
		logger.info("  hw_server : %s", server)
		# run_xsct_live keeps stdout unbuffered and forwards Ctrl-C cleanly
		run_xsct_live(cfg, xsct_script, ["jtag_uart", server])

	else:
		parser.print_help()
		sys.exit(1)


if __name__ == "__main__":
	main()