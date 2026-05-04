import dataclasses
import logging
import os
import re
import shutil

from xviv.utils.tools import find_vitis_dir_path, find_vivado_dir_path

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DEFAULT_VIVADO_PATH    = "/opt/Xilinx/Vivado/2024.1"
DEFAULT_VITIS_PATH     = "/opt/Xilinx/Vitis/2024.1"
DEFAULT_BUILD_DIR      = "build"
DEFAULT_BUILD_IP_REPO  = "build/ip"
DEFAULT_BUILD_BD_DIR   = "build/bd"
DEFAULT_BUILD_CORE_DIR = "build/core"
DEFAULT_BUILD_WRAPPER_DIR = "build/wrapper"

# =============================================================================
# Schema  -  one dataclass per TOML section
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
	max_threads: int = 10
	hw_server:   str = "localhost:3121"


@dataclasses.dataclass
class VitisConfig:
	path: str = DEFAULT_VITIS_PATH


@dataclasses.dataclass
class BuildConfig:
	dir:         str = DEFAULT_BUILD_DIR
	bd_dir:      str = DEFAULT_BUILD_BD_DIR
	wrapper_dir: str = DEFAULT_BUILD_WRAPPER_DIR
	core_dir:    str = DEFAULT_BUILD_CORE_DIR
	max_parallel_jobs: int = 4


@dataclasses.dataclass
class IpConfig:
	name:           str
	vendor:         str       = "user.org"
	library:        str       = "user"
	version:        str       = "1.0"
	repo:           str       = DEFAULT_BUILD_IP_REPO
	top:            str       = ""
	rtl:            list[str] = dataclasses.field(default_factory=list)
	hooks:          str       = ""
	create_wrapper: bool      = False
	vlnv:			str       = ""

	def __post_init__(self) -> None:
		self.repo = os.path.abspath(self.repo)

		if not self.top:
			self.top = self.name
		if not self.hooks:
			self.hooks = f"scripts/ip/{self.name}_{self.version}.tcl"
		if not self.vlnv:
			self.vlnv = f"{self.vendor}:{self.library}:{self.name}:{self.version}"


@dataclasses.dataclass
class BdConfig:
	name:       str
	hooks:      str       = ""
	state_tcl:  str       = ""
	fpga_ref:       str       = ""
	vlnv_list:  list[str] = dataclasses.field(default_factory=list)

	def __post_init__(self) -> None:
		if not self.hooks:
			self.hooks = f"scripts/bd/{self.name}_hooks.tcl"
		if not self.state_tcl:
			self.state_tcl = f"scripts/bd/state/{self.name}.tcl"

		self.state_tcl = os.path.abspath(self.state_tcl)

		if os.path.exists(self.state_tcl):
			with open(self.state_tcl, 'rt') as f:
				self.vlnv_list = self._resolve_vlnv_list(f.read())

				logger.info(f"Retrieved VLNV's of Reuired IP's for BD {self.name} from {self.state_tcl}\n\t{self.vlnv_list}")

	def _resolve_vlnv_list(self, text) -> list[str]:
		match = re.search(r'set\s+list_check_ips\s+"(.*?)"', text, re.DOTALL)

		if match:
			raw = match.group(1)

			return [
				ip for ip in [
					line.strip().rstrip("\\").strip() for line in raw.splitlines()
				] if ip
			]

		return []


@dataclasses.dataclass
class SynthConfig:
	top:              str
	ip:               str
	bd:               str
	hooks:            str       = ""
	rtl:              list[str] = dataclasses.field(default_factory=list)
	xdc:              list[str] = dataclasses.field(default_factory=list)
	xdc_ooc:          list[str] = dataclasses.field(default_factory=list)
	fpga_ref:             str       = ""
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
			self.hooks = f"scripts/synth/{self.ip or self.bd or self.top}.tcl"

@dataclasses.dataclass
class SimulationConfig:
	top:       str
	rtl:       list[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class CoreConfig:
	name:       str
	vlnv:       str
	state_tcl:  str
	
	def __post_init__(self) -> None:
		if not self.state_tcl:
			self.state_tcl = f"scripts/core/state/{self.name}.tcl"

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


@dataclasses.dataclass(frozen=True)
class CoreEntry:
	vlnv:                 str
	vendor:               str
	library:              str
	name:                 str
	version:              str
	display_name:         str
	description:          str
	hidden:               bool
	board_dependent:      bool
	ipi_only:             bool
	unsupported_families: frozenset[str]
	upgrades_from:        tuple[str, ...]

	@property
	def short_desc(self) -> str:
		desc_max = shutil.get_terminal_size().columns // 2
		text = " ".join(self.description.split())
		if len(text) > desc_max:
			text = text[:desc_max - 1] + "..."
		return text

	@property
	def completion_description(self) -> str:
		parts = [self.display_name, f"[{self.vendor}/{self.library}]"]
		flags: list[str] = []
		if self.hidden:
			flags.append("⚠ internal subcore")
		if self.board_dependent:
			flags.append("⚠ board-dependent")
		if self.ipi_only:
			flags.append("⚠ IPI-only")
		if flags:
			parts.append("  ".join(flags))
		elif self.short_desc:
			parts.append(self.short_desc)
		return "  ".join(parts)



def _parse_fpga(raw: dict) -> tuple[str, dict[str, FpgaConfig]]:
	section = raw.get("fpga", {})

	# Default target: flat scalars directly under [fpga]
	default_part_ref = section.get("default", "")

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

	return default_part_ref, fpga_named


def _parse_vivado(raw: dict) -> VivadoConfig:
	v = raw.get("vivado", {})
	return VivadoConfig(
		path=find_vivado_dir_path(),
		mode=v.get("mode", "batch"),
		max_threads=int(v.get("max_threads", 20)),
		hw_server=v.get("hw_server", "localhost:3121"),
	)


def _parse_vitis(raw: dict) -> VitisConfig:
	return VitisConfig(
		path=find_vitis_dir_path()
	)

def _parse_parallel(raw: dict) -> int:
	return raw.get('max_parallel_jobs', 4)

def _parse_build(raw: dict) -> BuildConfig:
	b = raw.get("build", {})
	return BuildConfig(
		max_parallel_jobs=b.get("max_parallel_jobs", 10),
		dir=b.get("dir", DEFAULT_BUILD_DIR),
		bd_dir=b.get("bd_dir", DEFAULT_BUILD_BD_DIR),
		core_dir=b.get("core_dir", DEFAULT_BUILD_CORE_DIR),
		wrapper_dir=b.get("wrapper_dir", DEFAULT_BUILD_WRAPPER_DIR),
	)


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
			repo=i.get("repo", DEFAULT_BUILD_IP_REPO),
			# xdc=i.get("xdc", []),
			# xdc_ooc=i.get("xdc_ooc", []),
			# fpga=i.get("fpga", ""),
			create_wrapper=i.get("create_wrapper", False),
		)
		for i in raw.get("ip", [])
	]


def _parse_bds(raw: dict) -> list[BdConfig]:
	return [
		BdConfig(
			name=b["name"],
			hooks=b.get("hooks", ""),
			state_tcl=b.get("state_tcl", ""),
			# xdc=b.get("xdc", []),
			# xdc_ooc=b.get("xdc_ooc", []),
			fpga_ref=b.get("fpga", ""),
		)
		for b in raw.get("bd", [])
	]

def _parse_cores(raw: dict) -> list[CoreConfig]:
	return [
		CoreConfig(
			name=b["name"],
			vlnv=b["vlnv"],
			state_tcl=b.get('state_tcl', '')
		)
		for b in raw.get("core", [])
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
			fpga_ref=s.get("fpga", ""),
			report_synth=s.get("report_synth", False),
			report_place=s.get("report_place", False),
			report_route=s.get("report_route", False),
			generate_netlist=s.get("generate_netlist", False),
			out_of_context=s.get("out_of_context", False),
		)
		for s in raw.get("synthesis", [])
	]

def _parse_simulations(raw: dict) -> list[SimulationConfig]:
	return [
		SimulationConfig(
			top=p["top"],
			rtl=p.get("rtl", []),
		)
		for p in raw.get("simulate", [])
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

