import dataclasses
import shutil


@dataclasses.dataclass
class VivadoConfig:
	path:        str
	dry_run:     bool
	mode:        str
	max_threads: int
	hw_server:   str

@dataclasses.dataclass
class VitisConfig:
	path: str

	# xsct_bin: str | None

@dataclasses.dataclass
class IpConfig:
	vendor:   str
	library:  str
	version:  str
	vlnv:     str
	repo:     str

	name:     str
	top:      str
	sources:  list[str]
	fpga_ref: str


@dataclasses.dataclass
class IpWrapperConfig:
	wrapper_top: str
	wrapper_file: str

	ip_name:      str
	ip_top:       str
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
class SubCoreConfig:
	inst_hier_path: str
	bd: str | None
	design: str | None
	core: str | None

@dataclasses.dataclass
class BdConfig:
	name:            str
	fpga_ref:        str

	save_file:       str
	bd_file:         str
	bd_wrapper_file: str


@dataclasses.dataclass
class SynthConfig:
	design_name: str | None
	core_name:   str | None
	bd_name:     str | None
	
	out_of_context_subcores: bool

	top: str
	fpga_ref:    str
	constraints: list[str]

	synth_incremental: bool
	run_synth: bool
	run_opt: bool

	impl_incremental: bool
	run_place: bool
	run_phys_opt: bool
	run_route: bool
	
	bitstream_file: str | None
	hw_platform_xsa_file: str | None
	
	# checkpoints

	synth_dcp_file: str | None
	place_dcp_file: str | None
	route_dcp_file: str | None
	
	# reports
	
	synth_report_timing_summary_file: str | None
	synth_report_utilization_file: str | None
	synth_report_incremental_reuse_file: str | None
	
	route_report_drc_file: str | None
	route_report_methodology_file: str | None
	route_report_power_file: str | None
	route_report_route_status_file: str | None
	route_report_timing_summary_file: str | None

	impl_report_incremental_reuse_file: str | None
	
	# # netlists
	
	synth_functional_netlist_file: str | None
	synth_timing_netlist_file: str | None
	impl_functional_netlist_file: str | None
	impl_timing_netlist_file: str | None

	impl_timing_sdf_file: str | None
	
	# # stubs
	
	synth_stub_file: str | None
	
	# settings
	
	synth_directive: str
	synth_mode: str
	synth_flatten_hierarchy: str
	synth_fsm_extraction: str
	
	opt_directive: str
	
	place_directive: str
	
	phys_opt_directive: str
	
	route_directive: str

	# usr access val

	usr_access_value: int | None


@dataclasses.dataclass
class SimulationConfig:
	name:      str
	top:       str
	sources:   list[str]
	backend:   str
	design:    str | None
	timescale: str
	
	work_dir:  str | None
	
	sdfmax:    list[str]


@dataclasses.dataclass
class PlatformConfig:
	name:      str
	cpu:       str
	os:        str
	xsa_file:  str
	bitstream_file:  str
	dir:       str

@dataclasses.dataclass
class AppConfig:
	name:     str
	platform: str
	template: str
	sources:  list[str]
	dir:      str
	elf_file: str


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

