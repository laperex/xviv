import dataclasses
import logging
import os
import re
import shutil

from xviv.utils.tools import find_vitis_dir_path, find_vivado_dir_path

logger = logging.getLogger(__name__)


DEFAULT_BUILD_IP_REPO  = "build/ip"

@dataclasses.dataclass
class FpgaConfig:
	part:       str
	board_part: str = ""
	board_repo: str = ""


@dataclasses.dataclass
class VivadoConfig:
	path:        str
	mode:        str = "batch"
	max_threads: int = 10
	hw_server:   str = "localhost:3121"


@dataclasses.dataclass
class VitisConfig:
	path: str

@dataclasses.dataclass
class IpConfig:
	name:    str
	repo:    str
	top:     str
	vendor:  str
	library: str
	version: str
	sources: list[str]

@dataclasses.dataclass
class WrapperConfig:
	ip_name:      str
	wrapper_file: str
	sources:      list[str]


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
	fpga_ref:         str       = ""

	srcs:             list[str] = dataclasses.field(default_factory=list)
	constrs:          list[str] = dataclasses.field(default_factory=list)

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
	xci_file:   str
	dcp_file:   str
	stub_file:  str

	def __post_init__(self) -> None:
		pass


@dataclasses.dataclass
class BdCoreConfig(CoreConfig):
	inst_hier_path: str


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
class CatalogCoreEntry:
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

