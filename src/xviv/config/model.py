import dataclasses
import os
import shutil
import typing

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _sources_to_lock(sources: list["SourceFile"], base_dir: str) -> list[dict]:
	return [s.to_lock(base_dir) for s in sources]


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


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

	def to_lock(self, base_dir: str) -> dict:
		return {"files": [f"./{os.path.relpath(self.file, base_dir)}"], "used_in": sorted(self.used_in)}


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
	fpga: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["sources"] = _sources_to_lock(self.sources, base_dir=base_dir)
		return d


@dataclasses.dataclass
class IpWrapperConfig:
	wrapper_top: str

	ip: str
	top: str
	sources: list[SourceFile]

	wrapper_file: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["sources"] = _sources_to_lock(self.sources, base_dir=base_dir)
		d['wrapper_file'] = os.path.relpath(self.wrapper_file, base_dir)
		return d


@dataclasses.dataclass
class FpgaConfig:
	name: str
	fpga_part: str | None
	board_part: str | None

	def to_lock(self) -> dict:
		return dataclasses.asdict(self)


@dataclasses.dataclass
class DesignConfig:
	name: str
	top: str
	sources: list[SourceFile]
	fpga: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["sources"] = _sources_to_lock(self.sources, base_dir=base_dir)
		return d


@dataclasses.dataclass
class CoreConfig:
	name: str
	vlnv: str
	fpga: str

	xci_file: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d['xci_file'] = os.path.relpath(self.xci_file, base_dir)
		return d


@dataclasses.dataclass
class SubCoreConfig:
	inst_hier_path: str
	bd: str | None
	design: str | None
	core: str | None

	def to_lock(self) -> dict:
		return dataclasses.asdict(self)


@dataclasses.dataclass
class BdConfig:
	name: str
	fpga: str

	save_file: str
	bd_file: str
	bd_wrapper_file: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d['save_file'] = os.path.relpath(self.save_file, base_dir)
		d['bd_file'] = os.path.relpath(self.bd_file, base_dir)
		d['bd_wrapper_file'] = os.path.relpath(self.bd_wrapper_file, base_dir)
		return d


@dataclasses.dataclass
class SynthConfig:
	design: str | None
	core: str | None
	bd: str | None

	top: str
	fpga: str
	constraints: list[SourceFile]

	synth_incremental: bool
	run_synth: bool
	run_opt: bool

	impl_incremental: bool
	run_place: bool
	run_phys_opt: bool
	run_route: bool

	bitstream: str | None
	hw_platform: str | None

	# checkpoints

	synth_dcp: str | None
	place_dcp: str | None
	route_dcp: str | None

	# reports

	synth_report_timing_summary: str | None
	synth_report_utilization: str | None
	synth_report_incremental_reuse: str | None

	route_report_drc: str | None
	route_report_methodology: str | None
	route_report_power: str | None
	route_report_route_status: str | None
	route_report_timing_summary: str | None

	impl_report_incremental_reuse: str | None

	# netlists

	synth_functional_netlist: str | None
	synth_timing_netlist: str | None
	impl_functional_netlist: str | None
	impl_timing_netlist: str | None

	impl_timing_sdf: str | None

	# stubs

	synth_stub: str | None

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

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["constraints"] = _sources_to_lock(self.constraints, base_dir=base_dir)

		if self.bitstream:
			d["bitstream"] = os.path.relpath(self.bitstream, base_dir)
		if self.hw_platform:
			d["hw_platform"] = os.path.relpath(self.hw_platform, base_dir)
		if self.synth_dcp:
			d["synth_dcp"] = os.path.relpath(self.synth_dcp, base_dir)
		if self.place_dcp:
			d["place_dcp"] = os.path.relpath(self.place_dcp, base_dir)
		if self.route_dcp:
			d["route_dcp"] = os.path.relpath(self.route_dcp, base_dir)
		if self.synth_report_timing_summary:
			d["synth_report_timing_summary"] = os.path.relpath(self.synth_report_timing_summary, base_dir)
		if self.synth_report_utilization:
			d["synth_report_utilization"] = os.path.relpath(self.synth_report_utilization, base_dir)
		if self.synth_report_incremental_reuse:
			d["synth_report_incremental_reuse"] = os.path.relpath(self.synth_report_incremental_reuse, base_dir)
		if self.route_report_drc:
			d["route_report_drc"] = os.path.relpath(self.route_report_drc, base_dir)
		if self.route_report_methodology:
			d["route_report_methodology"] = os.path.relpath(self.route_report_methodology, base_dir)
		if self.route_report_power:
			d["route_report_power"] = os.path.relpath(self.route_report_power, base_dir)
		if self.route_report_route_status:
			d["route_report_route_status"] = os.path.relpath(self.route_report_route_status, base_dir)
		if self.route_report_timing_summary:
			d["route_report_timing_summary"] = os.path.relpath(self.route_report_timing_summary, base_dir)
		if self.impl_report_incremental_reuse:
			d["impl_report_incremental_reuse"] = os.path.relpath(self.impl_report_incremental_reuse, base_dir)
		if self.synth_functional_netlist:
			d["synth_functional_netlist"] = os.path.relpath(self.synth_functional_netlist, base_dir)
		if self.synth_timing_netlist:
			d["synth_timing_netlist"] = os.path.relpath(self.synth_timing_netlist, base_dir)
		if self.impl_functional_netlist:
			d["impl_functional_netlist"] = os.path.relpath(self.impl_functional_netlist, base_dir)
		if self.impl_timing_netlist:
			d["impl_timing_netlist"] = os.path.relpath(self.impl_timing_netlist, base_dir)
		if self.impl_timing_sdf:
			d["impl_timing_sdf"] = os.path.relpath(self.impl_timing_sdf, base_dir)
		if self.synth_stub:
			d["synth_stub"] = os.path.relpath(self.synth_stub, base_dir)

		return d


@dataclasses.dataclass
class UvmConfig:
	test: str
	simulation: str
	top: str
	timescale: str
	verbosity: str
	version: str
	max_quit_count: int | None

	def to_lock(self) -> dict:
		return dataclasses.asdict(self)


@dataclasses.dataclass
class SimulationConfig:
	name: str
	top: str
	sources: list[SourceFile]
	backend: str

	sdfmax: list[str]
	sdfmin: list[str]

	timescale: str

	bd: str | None
	design: str | None

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

	uvm_pkg_dir: str | None
	# UVM with verilator: user must supply UVM source files in `sources`
	# and point uvm_pkg_dir at a verilator-compatible UVM package root.
	work_dir: str | None

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["sources"] = _sources_to_lock(self.sources, base_dir=base_dir)

		if self.work_dir:
			d["work_dir"] = os.path.relpath(self.work_dir, base_dir)

		if self.uvm_pkg_dir:
			d["uvm_pkg_dir"] = os.path.relpath(self.uvm_pkg_dir, base_dir)

		d['include_dirs'] = [os.path.relpath(i, base_dir) for i in self.include_dirs]

		return d


@dataclasses.dataclass
class PlatformConfig:
	name: str
	cpu: str
	os: str
	properties: list[tuple[str, str]]

	work_dir: str
	xsa: str
	bitstream: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)
		d["properties"] = {p: c for p, c in self.properties}
		d["xsa"] = os.path.relpath(self.xsa, base_dir)
		d["bitstream"] = os.path.relpath(self.bitstream, base_dir)
		d["work_dir"] = os.path.relpath(self.work_dir, base_dir)
		return d


@dataclasses.dataclass
class AppConfig:
	name: str
	platform: str
	template: str
	sources: list[SourceFile]

	work_dir: str
	elf: str

	def to_lock(self, base_dir: str) -> dict:
		d = dataclasses.asdict(self)

		d["sources"] = _sources_to_lock(self.sources, base_dir=base_dir)

		d["work_dir"] = os.path.relpath(self.work_dir, base_dir)
		d["elf"] = os.path.relpath(self.elf, base_dir)

		return d


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
	sources: list[SourceFile]

	engine: str
	depth: int
	append: int
	defines: list[str]
	multiclock: bool
	async2sync: bool
	sv: bool

	extra_script: list[str]
	extra_opts: list[str]

	work_dir: str
	include_dirs: list[str]

	def __post_init__(self) -> None:
		if self.mode not in ("bmc", "prove", "cover"):
			raise ValueError(f"FormalConfig '{self.name}': invalid mode '{self.mode}'")

	def to_lock(self, base_dir: str) -> dict:
		# sources is list[str] and all other fields are scalars/plain lists
		d = dataclasses.asdict(self)
		d['sources'] = _sources_to_lock(self.sources, base_dir=base_dir)
		d['work_dir'] = os.path.relpath(self.work_dir, base_dir)
		d['include_dirs'] = [os.path.relpath(i, base_dir) for i in self.include_dirs]
		return d
