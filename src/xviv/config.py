"""
config.py  -  Project configuration for xviv
=============================================

Architecture
------------
The TOML file is parsed ONCE in load_config() into a ProjectConfig dataclass
tree.  Every raw dict key access (i.e., every reference to the TOML schema)
is confined to the _parse_* functions below.  If a TOML key is renamed or
restructured, only those functions need to change.

Callers receive a ProjectConfig and work with typed attributes:
	cfg.vivado.path
	cfg.get_ip("my_ip").vendor
	cfg.build_dir          # resolved absolute path property
	...

generate_config_tcl() is the only place that maps Python config -> TCL globals.
If a new TCL variable is needed, add it there (and nowhere else).
"""

from __future__ import annotations

import dataclasses
import glob
import logging
import os
import sys
import tomllib
import typing

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DEFAULT_VIVADO_PATH    = "/opt/Xilinx/Vivado/2024.1"
DEFAULT_VITIS_PATH     = "/opt/Xilinx/Vitis/2024.1"
DEFAULT_BUILD_DIR      = "build"
DEFAULT_BUILD_IP_REPO  = "build/ip"
DEFAULT_BUILD_BD_DIR   = "build/bd"
DEFAULT_BUILD_WRAPPER_DIR = "build/wrapper"


# =============================================================================
# Schema  -  one dataclass per TOML section
#            THIS IS THE SINGLE SOURCE OF TRUTH for TOML structure.
# =============================================================================

@dataclasses.dataclass
class FpgaConfig:
	part:       str
	board_part: str = ""
	board_repo: str = ""


@dataclasses.dataclass
class VivadoConfig:
	path:        str = DEFAULT_VIVADO_PATH
	mode:        str = "batch"
	max_threads: int = 8
	hw_server:   str = "localhost:3121"


@dataclasses.dataclass
class VitisConfig:
	path: str = DEFAULT_VITIS_PATH


@dataclasses.dataclass
class BuildConfig:
	dir:         str = DEFAULT_BUILD_DIR
	ip_repo:     str = DEFAULT_BUILD_IP_REPO
	bd_dir:      str = DEFAULT_BUILD_BD_DIR
	wrapper_dir: str = DEFAULT_BUILD_WRAPPER_DIR


# @dataclasses.dataclass
# class SourcesConfig:
# 	rtl: list[str] = dataclasses.field(default_factory=list)
# 	sim: list[str] = dataclasses.field(default_factory=list)
# 	xdc: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class IpConfig:
	name:           str
	vendor:         str       = "user.org"
	library:        str       = "user"
	version:        str       = "1.0"
	top:            str       = ""
	rtl:            list[str] = dataclasses.field(default_factory=list)
	hooks:          str       = ""
	# xdc:            list[str] = dataclasses.field(default_factory=list)
	# xdc_ooc:        list[str] = dataclasses.field(default_factory=list)
	# fpga:           str       = ""
	create_wrapper: bool      = False

	def __post_init__(self) -> None:
		if not self.top:
			self.top = self.name
		if not self.hooks:
			self.hooks = f"scripts/ip/{self.name}_{self.version}.tcl"


@dataclasses.dataclass
class BdConfig:
	name:       str
	hooks:      str       = ""
	export_tcl: str       = ""
	# xdc:        list[str] = dataclasses.field(default_factory=list)
	# xdc_ooc:    list[str] = dataclasses.field(default_factory=list)
	fpga:       str       = ""

	def __post_init__(self) -> None:
		if not self.hooks:
			self.hooks = f"scripts/bd/{self.name}_hooks.tcl"
		if not self.export_tcl:
			self.export_tcl = f"scripts/bd/{self.name}.tcl"


@dataclasses.dataclass
class SynthConfig:
	top:              str
	ip:               str
	bd:               str
	hooks:            str       = ""
	rtl:              list[str] = dataclasses.field(default_factory=list)
	xdc:              list[str] = dataclasses.field(default_factory=list)
	xdc_ooc:          list[str] = dataclasses.field(default_factory=list)
	fpga:             str       = ""
	report_synth:     bool      = False
	report_place:     bool      = False
	report_route:     bool      = False
	generate_netlist: bool      = False
	out_of_context:   bool      = False

	# =========================================================================
	# GLOBAL SETTINGS
	# =========================================================================
	# Caps the number of CPU threads Vivado will use (1-32)
	max_threads: int = 8 

	# autoIncr.Synth.RejectBehavior when incremental synthesis criteria isn't met
	# values: continue (switch to default full synthesis) | terminate (stop build)
	incr_synth_fallback: str = "continue"

	# =========================================================================
	# SYNTHESIS (synth_design)
	# =========================================================================
	# values: default | RuntimeOptimized | AreaOptimized_high | AreaOptimized_medium
	#         PerformanceOptimized | AlternateRoutability | AreaMapLargeShiftRegToBRAM
	synth_directive: str = "default"

	# values: rebuilt | full | none
	flatten_hierarchy: str = "rebuilt"
	
	# values: auto | one_hot | sequential | johnson | gray | off
	fsm_extraction: str = "auto"

	# =========================================================================
	# LOGIC OPTIMIZATION (opt_design)
	# Note: Must be True if using an incremental implementation reference!
	# =========================================================================
	run_opt_design: bool = True
	
	# values: default | Explore | ExploreArea | ExploreSequentialArea
	#         AddRemap | ExploreWithRemap | RuntimeOptimized | NoBramPowerOpt
	opt_directive: str = "default"

	# =========================================================================
	# PLACEMENT (place_design)
	# =========================================================================
	# values: default | Explore | WLDrivenBlockPlacement | Quick | RuntimeOptimized
	#         ExtraNetDelay_high | ExtraNetDelay_medium | ExtraNetDelay_low
	#         SpreadLogic_high | SpreadLogic_medium | SpreadLogic_low
	#         AltSpreadLogic_high | AltSpreadLogic_medium | AltSpreadLogic_low
	place_directive: str = "default"

	# =========================================================================
	# PHYSICAL OPTIMIZATION (phys_opt_design)
	# Runs after placement to fix timing violations using physical data
	# =========================================================================
	run_phys_opt: bool = False
	
	# values: default | Explore | AggressiveExplore | AlternateReplication
	#         AggressiveFanoutOpt | AlternateFlowWithRetiming | AddRetime
	phys_opt_directive: str = "default"

	# =========================================================================
	# ROUTING (route_design)
	# =========================================================================
	# values: default | Explore | MoreGlobalIterations | HigherDelayCost 
	#         AdvancedSkewModeling | NoTimingRelaxation | RuntimeOptimized | Quick
	route_directive: str = "default"

	# =========================================================================
	# BITSTREAM GENERATION
	# =========================================================================
	# 32-bit hex string to embed via JTAG (e.g., "DEADBEEF"). 
	# If left empty, xviv automatically injects the git SHA.
	usr_access: str = ""

	def __post_init__(self) -> None:
		if not self.hooks:
			self.hooks = f"scripts/synth/{self.top}.tcl"


@dataclasses.dataclass
class PlatformConfig:
	name:      str
	cpu:       str
	os:        str = "standalone"
	xsa:       str = ""
	synth_top: str = ""


@dataclasses.dataclass
class AppConfig:
	name:     str
	platform: str
	template: str = "empty_application"
	src_dir:  str = ""

	def __post_init__(self) -> None:
		if not self.src_dir:
			self.src_dir = f"srcs/sw/{self.name}"


# =============================================================================
# ProjectConfig  -  root object; all callers work with this
# =============================================================================

@dataclasses.dataclass
class ProjectConfig:
	base_dir: str          # resolved absolute path to the project root

	fpga_default: typing.Optional[FpgaConfig]
	fpga_named:   dict[str, FpgaConfig]

	vivado:  VivadoConfig
	vitis:   VitisConfig
	build:   BuildConfig
	# sources: SourcesConfig

	ips:       list[IpConfig]
	bds:       list[BdConfig]
	synths:    list[SynthConfig]
	platforms: list[PlatformConfig]
	apps:      list[AppConfig]

	# ---- resolved absolute path properties ----------------------------------------------------------------

	@property
	def build_dir(self) -> str:
		return os.path.join(self.base_dir, self.build.dir)

	@property
	def ip_repo(self) -> str:
		return os.path.join(self.base_dir, self.build.ip_repo)

	@property
	def bd_dir(self) -> str:
		return os.path.join(self.base_dir, self.build.bd_dir)

	@property
	def wrapper_dir(self) -> str:
		return os.path.join(self.base_dir, self.build.wrapper_dir)

	# ---- lookup helpers --------------------------------------------------------------------------------------------------------

	def get_ip(self, name: str) -> IpConfig:
		ip = next((i for i in self.ips if i.name == name), None)
		if ip is None:
			sys.exit(
				f"ERROR: IP '{name}' not found in [[ip]] entries.\n"
				f"  Available: {[i.name for i in self.ips]}"
			)
		return ip

	def get_bd(self, name: str) -> BdConfig:
		bd = next((b for b in self.bds if b.name == name), None)
		if bd is None:
			sys.exit(
				f"ERROR: BD '{name}' not found in [[bd]] entries.\n"
				f"  Available: {[b.name for b in self.bds]}"
			)
		return bd

	def get_synth(self, *, top_name: typing.Optional[str] = None, bd_name: typing.Optional[str] = None, ip_name: typing.Optional[str] = None) -> SynthConfig:
		s = next(
			(
				s for s in self.synths 
				if (top_name is not None and s.top == top_name) or 
				(ip_name is not None and s.ip == ip_name) or 
				(bd_name is not None and s.bd == bd_name)
			), 
			None
		)
		
		# Handle the failure cases
		if s is None:
			# If 'top_name' was provided and we failed to find it, throw the error
			if top_name is not None:
				avail_tops = [s.top for s in self.synths if s.top is not None]
				sys.exit(
					f"ERROR: Synthesis top '{top_name}' not found in [[synthesis]] entries.\n"
					f"  Available tops: {avail_tops}"
				)

			# If it was a 'bd_name' or 'ip_name' search that failed, return an empty config
			return SynthConfig(top="", ip="", bd="")
	
		return s

	def get_platform(self, name: str) -> PlatformConfig:
		p = next((p for p in self.platforms if p.name == name), None)
		if p is None:
			sys.exit(
				f"ERROR: Platform '{name}' not found in [[platform]] entries.\n"
				f"  Available: {[p.name for p in self.platforms]}"
			)
		return p

	def get_app(self, name: str) -> AppConfig:
		a = next((a for a in self.apps if a.name == name), None)
		if a is None:
			sys.exit(
				f"ERROR: App '{name}' not found in [[app]] entries.\n"
				f"  Available: {[a.name for a in self.apps]}"
			)
		return a

	def resolve_fpga(self, ref: typing.Optional[str] = None) -> FpgaConfig:
		"""Return the FpgaConfig for the named target, or the default."""
		if ref:
			fpga = self.fpga_named.get(ref)
			if fpga is None:
				sys.exit(
					f"ERROR: FPGA target '{ref}' not found in [fpga.*] tables.\n"
					f"  Available: {list(self.fpga_named.keys())}"
				)
			return fpga
		if self.fpga_default is None:
			sys.exit(
				"ERROR: No default [fpga] part found and no named fpga = '<name>' specified.\n"
				"  Add  [fpga] part = '...'  or reference a named  [fpga.<name>]  target."
			)
		return self.fpga_default

	# ---- path helpers ------------------------------------------------------------------------------------------------------------

	def abs_path(self, rel: str) -> str:
		return os.path.abspath(os.path.join(self.base_dir, rel))

	def resolve_globs(self, patterns: list[str]) -> list[str]:
		return _resolve_globs(patterns, self.base_dir)

	def get_dcp_path(self, top: str, dcp_name: str) -> str:
		return os.path.abspath(os.path.join(self.build_dir, top, f"{dcp_name}.dcp"))

	def get_control_fifo_path(self, top: str) -> str:
		return os.path.join(self.build_dir, "xviv", top, "control.fifo")

	def get_xlib_work_dir(self, top: str) -> str:
		return os.path.join(self.build_dir, "elab", top)

	def get_platform_dir(self, name: str) -> str:
		return os.path.join(self.build_dir, "bsp", name)

	def get_app_dir(self, name: str) -> str:
		app_dir = os.path.join(self.build_dir, "app", name)
		if not os.path.isdir(app_dir):
			sys.exit(
				f"ERROR: App directory not found: {app_dir}\n"
				f"  Run: xviv create --app {name}"
			)
		return app_dir

	def get_platform_paths(self, name: str) -> tuple[str, str]:
		"""Return (xsa_path, bitstream_path) for a platform."""
		plat = self.get_platform(name)

		if plat.xsa:
			xsa = self.abs_path(plat.xsa)
			stem = os.path.splitext(xsa)[0]
			bit = stem + ".bit"
			if not os.path.exists(bit):
				candidates = sorted(glob.glob(os.path.join(os.path.dirname(xsa), "*.bit")))
				if candidates:
					bit = candidates[0]
					logger.debug("Bitstream resolved via glob: %s", bit)
			return xsa, bit

		if plat.synth_top:
			synth_dir = os.path.join(self.build_dir, "synth", plat.synth_top)
			return (
				os.path.join(synth_dir, f"{plat.synth_top}.xsa"),
				os.path.join(synth_dir, f"{plat.synth_top}.bit"),
			)

		sys.exit(
			f"ERROR: Platform '{name}' must specify either 'xsa' or 'synth_top' in project.toml."
		)


# =============================================================================
# TOML -> ProjectConfig
# ALL raw dict key access is confined to the _parse_* functions below.
# To rename a TOML key, change only the relevant function here.
# =============================================================================

def _parse_fpga(raw: dict) -> tuple[typing.Optional[FpgaConfig], dict[str, FpgaConfig]]:
	section = raw.get("fpga", {})

	# Default target: flat scalars directly under [fpga]
	default_part = section.get("part", "")
	fpga_default: typing.Optional[FpgaConfig] = (
		FpgaConfig(
			part=default_part,
			board_part=section.get("board_part", ""),
			board_repo=section.get("board_repo", ""),
		)
		if default_part
		else None
	)

	# Named targets: [fpga.<name>] sub-tables
	fpga_named: dict[str, FpgaConfig] = {
		key: FpgaConfig(
			part=val["part"],
			board_part=val.get("board_part", ""),
			board_repo=val.get("board_repo", ""),
		)
		for key, val in section.items()
		if isinstance(val, dict) and val.get("part")
	}

	return fpga_default, fpga_named


def _parse_vivado(raw: dict) -> VivadoConfig:
	v = raw.get("vivado", {})
	return VivadoConfig(
		path=v.get("path", DEFAULT_VIVADO_PATH),
		mode=v.get("mode", "batch"),
		max_threads=int(v.get("max_threads", 8)),
		hw_server=v.get("hw_server", "localhost:3121"),
	)


def _parse_vitis(raw: dict) -> VitisConfig:
	v = raw.get("vitis", {})
	return VitisConfig(path=v.get("path", DEFAULT_VITIS_PATH))


def _parse_build(raw: dict) -> BuildConfig:
	b = raw.get("build", {})
	return BuildConfig(
		dir=b.get("dir", DEFAULT_BUILD_DIR),
		ip_repo=b.get("ip_repo", DEFAULT_BUILD_IP_REPO),
		bd_dir=b.get("bd_dir", DEFAULT_BUILD_BD_DIR),
		wrapper_dir=b.get("wrapper_dir", DEFAULT_BUILD_WRAPPER_DIR),
	)


# def _parse_sources(raw: dict) -> SourcesConfig:
# 	s = raw.get("sources", {})
# 	return SourcesConfig(
# 		rtl=s.get("rtl", []),
# 		sim=s.get("sim", []),
# 		xdc=s.get("xdc", []),
# 	)


def _parse_ips(raw: dict) -> list[IpConfig]:
	return [
		IpConfig(
			name=i["name"],
			vendor=i.get("vendor", "user.org"),
			library=i.get("library", "user"),
			version=i.get("version", "1.0"),
			top=i.get("top", ""),
			rtl=i.get("rtl", []),
			hooks=i.get("hooks", ""),
			# xdc=i.get("xdc", []),
			# xdc_ooc=i.get("xdc_ooc", []),
			# fpga=i.get("fpga", ""),
			create_wrapper=i.get("create-wrapper", False),
		)
		for i in raw.get("ip", [])
	]


def _parse_bds(raw: dict) -> list[BdConfig]:
	return [
		BdConfig(
			name=b["name"],
			hooks=b.get("hooks", ""),
			export_tcl=b.get("export_tcl", ""),
			# xdc=b.get("xdc", []),
			# xdc_ooc=b.get("xdc_ooc", []),
			fpga=b.get("fpga", ""),
		)
		for b in raw.get("bd", [])
	]


def _parse_synths(raw: dict) -> list[SynthConfig]:
	return [
		SynthConfig(
			top=s.get("top", ""),
			ip=s.get("ip", ""),
			bd=s.get("bd", ""),
			hooks=s.get("hooks", ""),
			rtl=s.get("rtl", []),
			xdc=s.get("xdc", []),
			xdc_ooc=s.get("xdc_ooc", []),
			fpga=s.get("fpga", ""),
			report_synth=s.get("report_synth", False),
			report_place=s.get("report_place", False),
			report_route=s.get("report_route", False),
			generate_netlist=s.get("generate_netlist", False),
			out_of_context=s.get("out_of_context", False),
		)
		for s in raw.get("synthesis", [])
	]


def _parse_platforms(raw: dict) -> list[PlatformConfig]:
	return [
		PlatformConfig(
			name=p["name"],
			cpu=p["cpu"],
			os=p.get("os", "standalone"),
			xsa=p.get("xsa", ""),
			synth_top=p.get("synth_top", ""),
		)
		for p in raw.get("platform", [])
	]


def _parse_apps(raw: dict) -> list[AppConfig]:
	return [
		AppConfig(
			name=a["name"],
			platform=a["platform"],
			template=a.get("template", "empty_application"),
			src_dir=a.get("src_dir", ""),
		)
		for a in raw.get("app", [])
	]


# =============================================================================
# Public entry-point
# =============================================================================

def load_config(path: str) -> ProjectConfig:
	"""
	Parse project.toml and return a fully validated ProjectConfig.
	This is the only function that reads the raw TOML dict.
	"""
	path = os.path.abspath(path)
	if not os.path.isfile(path):
		sys.exit(f"ERROR: Config file not found - {path}")

	with open(path, "rb") as fh:
		raw = tomllib.load(fh)

	base_dir = os.path.dirname(path)

	fpga_default, fpga_named = _parse_fpga(raw)

	if fpga_default is None and not fpga_named:
		sys.exit(
			"ERROR: project.toml must define at least one FPGA target:\n"
			"  [fpga] part = '...'        (default target)\n"
			"  [fpga.<name>] part = '...' (named target, select with  fpga = '<name>')"
		)

	return ProjectConfig(
		base_dir     = base_dir,
		fpga_default = fpga_default,
		fpga_named   = fpga_named,
		vivado       = _parse_vivado(raw),
		vitis        = _parse_vitis(raw),
		build        = _parse_build(raw),
		# sources      = _parse_sources(raw),
		ips          = _parse_ips(raw),
		bds          = _parse_bds(raw),
		synths       = _parse_synths(raw),
		platforms    = _parse_platforms(raw),
		apps         = _parse_apps(raw),
	)


# =============================================================================
# TCL config generator
#
# Produces a self-contained TCL snippet that sets every global variable used
# by scripts/xviv.tcl and its sub-scripts.  All variables are always emitted
# (set to empty / zero by default) so TCL scripts never encounter unset vars.
#
# ip_name / bd_name / top_name select which context-specific block is active.
# =============================================================================

def generate_config_tcl(
	cfg: ProjectConfig,
	*,
	ip_name:  typing.Optional[str] = None,
	bd_name:  typing.Optional[str] = None,
	top_name: typing.Optional[str] = None,
) -> str:
	if sum(arg is not None for arg in (top_name, bd_name, ip_name)) != 1:
		sys.exit("ERROR: get_synth requires exactly one of 'top_name', 'bd_name', or 'ip_name' to be specified.")

	lines: list[str] = []

	# ---- resolve FPGA target (entry-level fpga = '<name>' override) ------------------
	fpga_ref: str = ""
	if bd_name:
		fpga_ref = cfg.get_bd(bd_name).fpga
	elif top_name:
		fpga_ref = cfg.get_synth(top_name=top_name).fpga

	fpga = cfg.resolve_fpga(fpga_ref or None)
	logger.debug("FPGA target: %s  part=%s", fpga_ref or "<default>", fpga.part)

	# ---- Vivado tuning ----------------------------------------------------------------------------------------------------------------
	lines.append(f"set_param general.maxThreads {cfg.vivado.max_threads}")

	# ---- FPGA ----------------------------------------------------------------------------------------------------------------------------------
	if fpga.board_repo:
		lines.append(f'set_param board.repoPaths [list "{fpga.board_repo}"]')

	lines += [
		f'set xviv_fpga_part  "{fpga.part}"',
		f'set xviv_board_part "{fpga.board_part}"',
		f'set xviv_board_repo "{fpga.board_repo}"',
	]

	# ---- Build paths ----------------------------------------------------------------------------------------------------------------------
	lines += [
		f'set xviv_build_dir   "{cfg.build_dir}"',
		f'set xviv_ip_repo     "{cfg.ip_repo}"',
		f'set xviv_bd_dir      "{cfg.bd_dir}"',
		f'set xviv_wrapper_dir "{cfg.wrapper_dir}"',
	]

	# ---- Synthesis report / netlist flags (defaults off) --------------------------------------------
	lines += [
		"set xviv_synth_report_synth    0",
		"set xviv_synth_report_place    0",
		"set xviv_synth_report_route    0",
		"set xviv_synth_generate_netlist 0",
		'set xviv_synth_hooks           ""',
	]

	# ---- IP variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_ip_name    ""',
		'set xviv_ip_vendor  ""',
		'set xviv_ip_library ""',
		'set xviv_ip_version ""',
		'set xviv_ip_top     ""',
		'set xviv_ip_hooks   ""',
	]

	# ---- BD variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_bd_name       ""',
		'set xviv_bd_hooks      ""',
	]

	# =========================================================================
	# Context-specific overrides
	# =========================================================================

	synth	= cfg.get_synth(top_name=top_name, bd_name=bd_name, ip_name=ip_name)

	synth_hooks	= cfg.abs_path(synth.hooks) if synth.hooks else ""

	xdc		= cfg.resolve_globs(synth.xdc) if synth.xdc else []
	rtl		= cfg.resolve_globs(synth.rtl) if synth.rtl else []

	if ip_name:
		ip    = cfg.get_ip(ip_name)
		ip_hooks = cfg.abs_path(ip.hooks) if ip.hooks else ""
		# IP-specific RTL overrides the global source glob; fall back if empty
		rtl = cfg.resolve_globs(ip.rtl)

		if not os.path.exists(ip_hooks):
			ip_hooks = ""

		lines += [
			f'set xviv_ip_name    "{ip.name}"',
			f'set xviv_ip_vendor  "{ip.vendor}"',
			f'set xviv_ip_library "{ip.library}"',
			f'set xviv_ip_version "{ip.version}"',
			f'set xviv_ip_top     "{ip.top}"',
			f'set xviv_ip_hooks   "{ip_hooks}"',
		]

	elif bd_name:
		bd     	= cfg.get_bd(bd_name)
		bd_hooks	= cfg.abs_path(bd.hooks) if bd.hooks else ""
		
		if not os.path.exists(bd_hooks):
			bd_hooks = ""

		# For BD commands the "RTL" source is the .bd file itself;
		# the synthesised wrapper is the companion .v file.
		bd_file   = os.path.join(cfg.bd_dir, bd_name, f"{bd_name}.bd")
		wrap_file = os.path.join(cfg.wrapper_dir, f"{bd_name}_wrapper.v")

		rtl = [wrap_file, bd_file]

		lines += [
			f'set xviv_bd_name       "{bd.name}"',
			f'set xviv_bd_hooks      "{bd_hooks}"',
		]

	if not os.path.exists(synth_hooks):
		synth_hooks = ""

	lines += [
		f'set xviv_synth_hooks            "{synth_hooks}"',
		f"set xviv_xdc_files              {_tcl_list(xdc)}",
		f"set xviv_rtl_files              {_tcl_list(rtl)}",
		f"set xviv_synth_report_synth     {int(synth.report_synth)}",
		f"set xviv_synth_report_place     {int(synth.report_place)}",
		f"set xviv_synth_report_route     {int(synth.report_route)}",
		f"set xviv_synth_generate_netlist {int(synth.generate_netlist)}",
	]

	return "\n".join(lines) + "\n"


# =============================================================================
# Internal helpers
# =============================================================================

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

