import dataclasses
import shutil


@dataclasses.dataclass
class VivadoConfig:
	path:        str
	dry_run:     bool
	mode:        str
	max_threads: int
	hw_server:   str

	# vivado_bin: str | None
	# xvlog_bin: str | None
	# xelab_bin: str | None
	# xsim_bin: str | None

@dataclasses.dataclass
class VitisConfig:
	path: str

	# xsct_bin: str | None

@dataclasses.dataclass
class IpConfig:
	vendor:  str
	library: str
	name:    str
	version: str
	vlnv:    str
	repo:    str
	top:     str
	sources: list[str]
	fpga_ref: str


@dataclasses.dataclass
class WrapperConfig:
	ip_name:      str
	ip_top:       str
	wrapper_file: str
	sources:      list[str]


@dataclasses.dataclass
class FpgaConfig:
	name: str
	fpga_part:  str | None
	board_part: str | None



@dataclasses.dataclass
class DesignConfig:
	name:    str
	top:     str
	sources: list[str]
	fpga_ref: str


@dataclasses.dataclass
class CoreConfig:
	name:     str
	vlnv:     str
	xci_file: str
	fpga_ref: str


@dataclasses.dataclass
class BdCoreConfig(CoreConfig):
	inst_hier_path: str


@dataclasses.dataclass
class BdConfig:
	name:            str
	vlnv_list:       list[str]
	fpga_ref:        str

	save_file:       str
	bd_file:         str
	bd_wrapper_file: str
	bd_wrapper_top:  str

	core_list: list[BdCoreConfig]


@dataclasses.dataclass
class SynthConfig:
	design_name: str | None
	core_name:   str | None
	bd_name:     str | None

	fpga_ref:    str
	constraints: list[str]


@dataclasses.dataclass
class SimulationConfig:
	top:     str
	sources: list[str]
	backend: str


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

