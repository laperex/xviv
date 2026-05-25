import dataclasses
import shutil
import typing


@dataclasses.dataclass
class VivadoConfig:
	path: str | None
	mode: str
	max_threads: int
	hw_server: str

	xsim_bin: str = "xsim"
	xvlog_bin: str = "xvlog"
	xelab_bin: str = "xelab"
	vivado_bin: str = "vivado"

	glbl_file: str | None = None


@dataclasses.dataclass
class VitisConfig:
	path: str | None

	xsct_bin: str = "xsct"


@dataclasses.dataclass
class SourceFile:
	file: str
	used_in: frozenset[str]

	@property
	def used_in_synth(self) -> bool:
		return "synth" in self.used_in

	@property
	def used_in_impl(self) -> bool:
		return "impl" in self.used_in

	@property
	def used_in_ooc(self) -> bool:
		return "ooc" in self.used_in

	@property
	def used_in_sim(self) -> bool:
		return "sim" in self.used_in

	@classmethod
	def from_stages(cls, file: str, stages: typing.Iterable[str]) -> "SourceFile":
		return cls(file=file, used_in=frozenset(stages))


@dataclasses.dataclass
class IpConfig:
	vendor: str
	library: str
	version: str
	vlnv: str
	repo: str

	name: str
	top: str
	sources: list[SourceFile]
	fpga_ref: str


@dataclasses.dataclass
class IpWrapperConfig:
	wrapper_top: str
	wrapper_file: str

	ip_name: str
	ip_top: str
	sources: list[SourceFile]


@dataclasses.dataclass
class FpgaConfig:
	name: str
	fpga_part: str | None
	board_part: str | None


@dataclasses.dataclass
class DesignConfig:
	name: str
	top: str
	sources: list[SourceFile]
	fpga_ref: str


@dataclasses.dataclass
class CoreConfig:
	name: str
	vlnv: str
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
	name: str
	fpga_ref: str

	save_file: str
	bd_file: str
	bd_wrapper_file: str


@dataclasses.dataclass
class SynthConfig:
	design_name: str | None
	core_name: str | None
	bd_name: str | None

	out_of_context_subcores: bool

	top: str
	fpga_ref: str
	constraints: list[SourceFile]

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
class UvmConfig:
	top: str
	timescale: str
	simulation: str
	test: str
	verbosity: str
	version: str
	max_quit_count: int | None


@dataclasses.dataclass
class SimulationConfig:
	name: str
	top: str
	sources: list[SourceFile]
	backend: str
	timescale: str

	work_dir: str | None

	sdfmax: list[str]
	sdfmin: list[str]

	design: str | None
	bd: str | None

	# -- UVM -------------------------------------------------------------- #
	# Vivado ships UVM 1.1d and 1.2 pre-compiled.  Set uvm=True and xelab
	# links -L uvm automatically; xsim receives the plusargs below.

	uvm_version: str
	uvm_verbosity: str
	uvm_max_quit_count: int | None

	# -- Generic plusargs (passed verbatim to xsim / verilated binary) -- #
	plusargs: list[str]

	# -- Preprocessor / include (xsim xvlog + verilator) --------------- #
	defines: list[str]
	include_dirs: list[str]

	# -- Verilator-specific ---------------------------------------------  #
	threads: int
	trace: bool
	trace_fst: bool
	trace_depth: int | None
	verilator_args: list[str]

	# UVM with verilator: user must supply UVM source files in `sources`
	# and point uvm_pkg_dir at a verilator-compatible UVM package root.
	uvm_pkg_dir: str | None


@dataclasses.dataclass
class PlatformConfig:
	name: str
	cpu: str
	os: str
	xsa_file: str
	bitstream_file: str
	properties: list[tuple[str, str]]
	dir: str


@dataclasses.dataclass
class AppConfig:
	name: str
	platform: str
	template: str
	sources: list[SourceFile]
	dir: str
	elf_file: str


@dataclasses.dataclass(frozen=True)
class CatalogCoreEntry:
	vlnv: str
	vendor: str
	library: str
	name: str
	version: str
	display_name: str
	description: str
	hidden: bool
	board_dependent: bool
	ipi_only: bool
	unsupported_families: frozenset[str]
	upgrades_from: tuple[str, ...]

	@property
	def short_desc(self) -> str:
		desc_max = shutil.get_terminal_size().columns // 2
		text = " ".join(self.description.split())

		if len(text) > desc_max:
			text = text[: desc_max - 1] + "..."

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


@dataclasses.dataclass
class FormalConfig:
	name: str
	top: str
	mode: str  # bmc | prove | cover
	sources: list[str]
	work_dir: str

	engine: str
	depth: int
	append: int
	defines: list[str]
	include_dirs: list[str]
	multiclock: bool
	async2sync: bool
	sv: bool
	extra_script: list[str]
	extra_opts: list[str]

	def __post_init__(self) -> None:
		if self.mode not in ("bmc", "prove", "cover"):
			from xviv.utils import error

			raise error.FormalInvalidModeError(self.name, self.mode)
