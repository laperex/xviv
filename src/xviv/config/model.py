import dataclasses
import os
import typing

from xviv.utils.hash import sha512_file

# ---------------------------------------------------------------------------
# Field factories
# ---------------------------------------------------------------------------


def relpath_field(**kw) -> typing.Any:
	return dataclasses.field(metadata={"lock": "relpath"}, **kw)


def integer_hex_field(**kw) -> typing.Any:
	return dataclasses.field(metadata={"lock": "hex"}, **kw)


def sources_field(**kw) -> typing.Any:
	return dataclasses.field(metadata={"lock": "sources"}, **kw)


def relpath_list_field(**kw) -> typing.Any:
	return dataclasses.field(metadata={"lock": "relpath_list"}, **kw)


# ---------------------------------------------------------------------------
# Generic serialiser + Lockable mixin
# ---------------------------------------------------------------------------


def _relpath(path: str, relpath: str) -> str:
	return ("./" if relpath != "/" else "/") + os.path.relpath(path, relpath)


def lock_serialize(obj: object, base_dir: str) -> dict:
	d: dict = {}
	for f in dataclasses.fields(obj):  # type: ignore[arg-type]
		val = getattr(obj, f.name)
		match f.metadata.get("lock"):
			case "relpath":
				d[f.name] = _relpath(val, base_dir) if val else val
			case "hex":
				d[f.name] = hex(val) if val else val
			case "sources":
				d[f.name] = [{"file": _relpath(s.file, base_dir), "hash": s.hash, "used_in": sorted(s.used_in)} for s in val]
			case "relpath_list":
				d[f.name] = [_relpath(p, base_dir) for p in val]
			case _:
				d[f.name] = val
	return d


class Lockable:
	def to_lock(self, base_dir: str = ".") -> dict:
		return lock_serialize(self, base_dir)


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ProjectConfig(Lockable):
	work_dir: str = relpath_field()
	log_file: str = relpath_field()
	board_repo: list[str] = relpath_list_field()
	ip_repo: list[str] = relpath_list_field()

	def __post_init__(self) -> None:
		self.work_dir = os.path.abspath(self.work_dir)
		self.log_file = os.path.abspath(self.log_file)
		self.board_repo = [os.path.abspath(p) for p in self.board_repo]
		self.ip_repo = [os.path.abspath(p) for p in self.ip_repo]


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
	vv_index_file: str | None = None


@dataclasses.dataclass
class VitisConfig:
	path: str | None

	xsct_bin: str = "xsct"


@dataclasses.dataclass
class SourceFile:
	file: str
	used_in: frozenset[str]
	hash: str = ""

	def uses(self, stage: str) -> bool:
		return stage in self.used_in

	@property
	def used_in_synth(self) -> bool:
		return self.uses("synth")

	@property
	def used_in_impl(self) -> bool:
		return self.uses("impl")

	@property
	def used_in_ooc(self) -> bool:
		return self.uses("ooc")

	@property
	def used_in_sim(self) -> bool:
		return self.uses("sim")

	@classmethod
	def from_stages(cls, file: str, stages: typing.Iterable[str]) -> typing.Self:
		return cls(file=file, used_in=frozenset(stages))

	def __post_init__(self) -> None:
		self.file = os.path.abspath(self.file)
		self.hash = sha512_file(self.file)


@dataclasses.dataclass
class IpConfig(Lockable):
	vendor: str
	library: str
	version: str
	vlnv: str
	repo: str
	name: str
	top: str
	fpga: str

	sources: list[SourceFile] = sources_field()

	@property
	def vid(self) -> str:
		return f"{self.name}_{self.version}".replace(".", "_")

	@property
	def component_xml_file(self) -> str:
		return os.path.abspath(os.path.join(self.repo, self.vid, "component.xml"))

	def __post_init__(self) -> None:
		for s in self.sources:
			s.file = os.path.abspath(s.file)

		self.repo = os.path.abspath(self.repo)


@dataclasses.dataclass
class IpWrapperConfig(Lockable):
	wrapper_top: str
	ip: str
	top: str
	wrapper_file: str = relpath_field()
	sources: list[SourceFile] = sources_field()

	def __post_init__(self) -> None:
		self.wrapper_file = os.path.abspath(self.wrapper_file)

		for s in self.sources:
			s.file = os.path.abspath(s.file)


@dataclasses.dataclass
class FpgaConfig(Lockable):
	name: str
	fpga_part: str | None
	board_part: str | None


@dataclasses.dataclass
class DesignConfig(Lockable):
	name: str
	top: str
	fpga: str
	sources: list[SourceFile] = sources_field()

	def __post_init__(self) -> None:
		for s in self.sources:
			s.file = os.path.abspath(s.file)


@dataclasses.dataclass
class CoreConfig(Lockable):
	name: str
	vlnv: str
	fpga: str
	xci_file: str = relpath_field()

	@property
	def parent_dir(self) -> str:
		return os.path.dirname(os.path.dirname(self.xci_file))

	@property
	def is_bd_core(self) -> bool:
		return os.path.exists(os.path.join(os.path.dirname(self.parent_dir), f"{os.path.basename(os.path.dirname(self.parent_dir))}.bd"))

	def __post_init__(self) -> None:
		self.xci_file = os.path.abspath(self.xci_file)


@dataclasses.dataclass
class SubCoreConfig(Lockable):
	bd: str | None
	design: str | None

	core: str | None
	inst_hier_path: str


@dataclasses.dataclass
class BdConfig(Lockable):
	name: str
	fpga: str
	save_file: str = relpath_field()
	bd_file: str = relpath_field()
	bd_wrapper_file: str = relpath_field()

	def __post_init__(self) -> None:
		self.save_file = os.path.abspath(self.save_file)
		self.bd_file = os.path.abspath(self.bd_file)
		self.bd_wrapper_file = os.path.abspath(self.bd_wrapper_file)


@dataclasses.dataclass
class SynthConfig(Lockable):
	design: str | None
	core: str | None
	bd: str | None

	top: str
	fpga: str

	synth_incremental: bool
	run_synth: bool
	run_opt: bool

	impl_incremental: bool
	run_place: bool
	run_phys_opt: bool
	run_route: bool

	# settings

	synth_directive: str
	synth_mode: str
	synth_flatten_hierarchy: str
	synth_fsm_extraction: str

	opt_directive: str
	place_directive: str
	phys_opt_directive: str
	route_directive: str

	# sources

	constraints: list[SourceFile] = sources_field()

	lock_file: str = relpath_field()

	usr_access_value: int | None = integer_hex_field(default=None)

	# checkpoints

	synth_dcp: str | None = relpath_field(default=None)
	place_dcp: str | None = relpath_field(default=None)
	route_dcp: str | None = relpath_field(default=None)

	# output artifacts

	bitstream: str | None = relpath_field(default=None)
	hw_platform: str | None = relpath_field(default=None)

	# reports

	synth_report_timing_summary: str | None = relpath_field(default=None)
	synth_report_utilization: str | None = relpath_field(default=None)
	synth_report_incremental_reuse: str | None = relpath_field(default=None)

	route_report_drc: str | None = relpath_field(default=None)
	route_report_methodology: str | None = relpath_field(default=None)
	route_report_power: str | None = relpath_field(default=None)
	route_report_route_status: str | None = relpath_field(default=None)
	route_report_timing_summary: str | None = relpath_field(default=None)

	impl_report_incremental_reuse: str | None = relpath_field(default=None)

	# netlists

	synth_functional_netlist: str | None = relpath_field(default=None)
	synth_timing_netlist: str | None = relpath_field(default=None)
	impl_functional_netlist: str | None = relpath_field(default=None)
	impl_timing_netlist: str | None = relpath_field(default=None)
	impl_timing_sdf: str | None = relpath_field(default=None)

	# stubs

	synth_stub: str | None = relpath_field(default=None)

	def __post_init__(self) -> None:
		for s in self.constraints:
			s.file = os.path.abspath(s.file)
		self.lock_file = os.path.abspath(self.lock_file)

		_optional_paths = (
			"synth_dcp",
			"place_dcp",
			"route_dcp",
			"bitstream",
			"hw_platform",
			"synth_report_timing_summary",
			"synth_report_utilization",
			"synth_report_incremental_reuse",
			"route_report_drc",
			"route_report_methodology",
			"route_report_power",
			"route_report_route_status",
			"route_report_timing_summary",
			"impl_report_incremental_reuse",
			"synth_functional_netlist",
			"synth_timing_netlist",
			"impl_functional_netlist",
			"impl_timing_netlist",
			"impl_timing_sdf",
			"synth_stub",
		)
		for attr in _optional_paths:
			val = getattr(self, attr)
			if val is not None:
				setattr(self, attr, os.path.abspath(val))


@dataclasses.dataclass
class UvmConfig(Lockable):
	test: str
	simulation: str
	top: str
	timescale: str
	verbosity: str
	version: str
	max_quit_count: int | None


@dataclasses.dataclass
class SimulationConfig(Lockable):
	name: str
	top: str
	backend: str

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

	# -- Verilator-specific --------------------------------------------- #
	threads: int
	trace: bool
	trace_fst: bool
	trace_depth: int | None
	verilator_args: list[str]

	sdfmax: list[str]
	sdfmin: list[str]

	# Declared with field factories so lock_serialize handles them automatically.
	sources: list[SourceFile] = sources_field()
	include_dirs: list[str] = relpath_list_field(default_factory=list)
	uvm_pkg_dir: str | None = relpath_field(default=None)
	# UVM with verilator: user must supply UVM source files in `sources`
	# and point uvm_pkg_dir at a verilator-compatible UVM package root.
	work_dir: str | None = relpath_field(default=None)

	def __post_init__(self) -> None:  # was __post__init__ (dead code)
		self.include_dirs = [os.path.abspath(p) for p in self.include_dirs]  # was abspath(list) - bug
		if self.uvm_pkg_dir is not None:
			self.uvm_pkg_dir = os.path.abspath(self.uvm_pkg_dir)
		if self.work_dir is not None:
			self.work_dir = os.path.abspath(self.work_dir)
		for s in self.sources:
			s.file = os.path.abspath(s.file)


@dataclasses.dataclass
class PlatformConfig(Lockable):
	name: str
	cpu: str
	os: str
	# dict[str, str] reflects the actual key -> value nature of platform properties;
	# the original list[tuple[str, str]] was immediately converted to dict in to_lock.
	xsa: str = relpath_field()
	bitstream: str = relpath_field()
	work_dir: str = relpath_field()

	properties: dict[str, str] | None = None

	def __post_init__(self) -> None:  # was __post__init__ (dead code)
		self.xsa = os.path.abspath(self.xsa)
		self.bitstream = os.path.abspath(self.bitstream)
		self.work_dir = os.path.abspath(self.work_dir)


@dataclasses.dataclass
class AppConfig(Lockable):
	name: str
	platform: str
	template: str
	sources: list[SourceFile] = sources_field()
	work_dir: str = relpath_field()
	elf: str = relpath_field()

	def __post_init__(self) -> None:
		self.work_dir = os.path.abspath(self.work_dir)
		self.elf = os.path.abspath(self.elf)
		for s in self.sources:
			s.file = os.path.abspath(s.file)


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

	# @property
	# def short_desc(self) -> str:
	# 	desc_max = shutil.get_terminal_size().columns // 2
	# 	text = " ".join(self.description.split())
	# 	if len(text) > desc_max:
	# 		text = text[: desc_max - 1] + "..."
	# 	return text

	# @property
	# def completion_description(self) -> str:
	# 	parts = [self.display_name, f"[{self.vendor}/{self.library}]"]
	# 	flags: list[str] = []

	# 	if self.hidden:
	# 		flags.append(theme_cfg.warning("internal subcore"))
	# 	if self.board_dependent:
	# 		flags.append(theme_cfg.warning("board-dependent"))
	# 	if self.ipi_only:
	# 		flags.append(theme_cfg.warning("IPI-only"))

	# 	parts.append("  ".join(flags) if flags else self.short_desc)
	# 	return "  ".join(parts)


@dataclasses.dataclass
class FormalConfig(Lockable):
	name: str
	top: str
	mode: str  # bmc | prove | cover

	engine: str
	depth: int
	append: int
	defines: list[str]
	multiclock: bool
	async2sync: bool
	sv: bool

	extra_script: list[str]
	extra_opts: list[str]

	sources: list[SourceFile] = sources_field()
	work_dir: str = relpath_field()
	include_dirs: list[str] = relpath_list_field(default_factory=list)

	def __post_init__(self) -> None:
		self.work_dir = os.path.abspath(self.work_dir)
		self.include_dirs = [os.path.abspath(p) for p in self.include_dirs]
		for s in self.sources:
			s.file = os.path.abspath(s.file)
