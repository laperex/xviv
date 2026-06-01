from __future__ import annotations

# --- Root --------------------------------------------------------------------


class XvivError(Exception): ...


class UninitializedError(XvivError): ...


class UninitializedVivadoError(UninitializedError):
	def __str__(self) -> str:
		return "VivadoConfig is not initialized - call add_vivado_cfg() first"


class UninitializedVitisError(UninitializedError):
	def __str__(self) -> str:
		return "VitisConfig is not initialized - call add_vitis_cfg() first"


class UninitializedCoreCatalogError(UninitializedError):
	def __str__(self) -> str:
		return "IP Catalog is not initialized - call add_vivado_cfg() first"


# --- Path --------------------------------------------------------------------


class InvalidPathError(XvivError):
	def __init__(self, path: str, context: str = "") -> None:
		self.path = path
		self.context = context
		super().__init__(path)

	def __str__(self) -> str:
		suffix = f" ({self.context})" if self.context else ""
		return f"Path does not exist: '{self.path}'{suffix}"


class FileNotFoundError(XvivError):
	def __init__(self, path: str) -> None:
		self.path = path
		super().__init__(path)

	def __str__(self) -> str:
		return f"File not found: '{self.path}'"


# --- Resolve -----------------------------------------------------------------


class ResolveError(XvivError): ...


class VlnvResolveError(ResolveError):
	def __init__(self, vlnv: str) -> None:
		self.vlnv = vlnv
		super().__init__(vlnv)

	def __str__(self) -> str:
		return f"Unable to resolve VLNV '{self.vlnv}' - check your IP repos and catalog entries"


class CoreVlnvResolveError(ResolveError):
	def __init__(self, name: str, vlnv: str) -> None:
		self.name = name
		self.vlnv = vlnv
		super().__init__(vlnv)

	def __str__(self) -> str:
		return f"Core '{self.name}' unable to resolve VLNV '{self.vlnv}' - check your IP repos and catalog entries"


class FpgaResolveError(ResolveError):
	def __init__(self, fpga: str) -> None:
		self.fpga = fpga
		super().__init__(fpga)

	def __str__(self) -> str:
		return f"Unable to resolve FPGA '{self.fpga}'"


# --- Config base -------------------------------------------------------------


class ConfigError(XvivError): ...


class AlreadyExistsError(ConfigError):
	def __init__(self, kind: str, name: str) -> None:
		self.kind = kind
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"{self.kind} entry already exists: '{self.name}'"


class DoesNotExistError(ConfigError):
	def __init__(self, kind: str, name: str) -> None:
		self.kind = kind
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"{self.kind} entry not found: '{self.name}'"


# --- AlreadyExists -----------------------------------------------------------


class CoreCatalogAlreadySpecifiedError(AlreadyExistsError):
	def __init__(self) -> None:
		super().__init__("CoreCatalog", "<singleton>")

	def __str__(self) -> str:
		return "CoreCatalog is already specified"


class VivadoAlreadySpecifiedError(AlreadyExistsError):
	def __init__(self) -> None:
		super().__init__("VivadoConfig", "<singleton>")

	def __str__(self) -> str:
		return "VivadoConfig is already specified"


class VitisAlreadySpecifiedError(AlreadyExistsError):
	def __init__(self) -> None:
		super().__init__("VitisConfig", "<singleton>")

	def __str__(self) -> str:
		return "VitisConfig is already specified"


class FpgaAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("FpgaConfig", name)


class IpAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("IpConfig", name)


class WrapperAlreadyExistsError(AlreadyExistsError):
	def __init__(self, ip_name: str) -> None:
		super().__init__("IpWrapperConfig", ip_name)


class BdAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("BdConfig", name)


class CoreAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("CoreConfig", name)


class DesignAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("DesignConfig", name)


class SynthAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("SynthConfig", name)


class SimAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("SimulationConfig", name)


class PlatformAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("PlatformConfig", name)


class AppAlreadyExistsError(AlreadyExistsError):
	def __init__(self, name: str) -> None:
		super().__init__("AppConfig", name)


# --- DoesNotExist ------------------------------------------------------------


class FpgaDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("FpgaConfig", name)


class IpDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("IpConfig", name)


class WrapperDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("IpWrapperConfig", name)


class BdDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("BdConfig", name)


class CoreDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("CoreConfig", name)


class DesignDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("DesignConfig", name)


class UvmDoesNotExistError(ConfigError):
	def __init__(self, test_name: str, sim_name: str) -> None:
		self.kind = "UvmConfig"
		self.test_name = test_name
		self.sim_name = sim_name
		super().__init__(test_name)

	def __str__(self) -> str:
		return f"{self.kind} entry not found for: '{self.test_name}' [SimulationConfig: '{self.sim_name}']"


class SynthDoesNotExistError(DoesNotExistError):
	def __init__(self, design: str | None, core: str | None, bd: str | None) -> None:
		self.design = design
		self.core = core
		self.bd = bd
		super().__init__("SynthConfig", design or core or bd or "<unknown>")

	def __str__(self) -> str:
		parts = []
		if self.design:
			parts.append(f"design='{self.design}'")
		if self.core:
			parts.append(f"core='{self.core}'")
		if self.bd:
			parts.append(f"bd='{self.bd}'")
		return f"SynthConfig not found for: {', '.join(parts)}"


class SimDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("SimulationConfig", name)


class PlatformDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("PlatformConfig", name)


class AppDoesNotExistError(DoesNotExistError):
	def __init__(self, name: str) -> None:
		super().__init__("AppConfig", name)


# --- FPGA --------------------------------------------------------------------


class FpgaPartUnspecifiedError(ConfigError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"FPGA entry '{self.name}' requires at least one of: fpga_part, board_part"


class NoFpgaError(ConfigError):
	def __str__(self) -> str:
		return "No FpgaConfig registered - call add_fpga_cfg() first"


class FpgaRefMismatchError(ConfigError):
	def __init__(self, entity_kind: str, entity_name: str, entity_fpga: str, given_fpga: str) -> None:
		self.entity_kind = entity_kind
		self.entity_name = entity_name
		self.entity_fpga = entity_fpga
		self.given_fpga = given_fpga
		super().__init__(entity_name)

	def __str__(self) -> str:
		return f"{self.entity_kind} '{self.entity_name}' is bound to FPGA '{self.entity_fpga}', but fpga='{self.given_fpga}' was explicitly specified"


# --- Wrapper -----------------------------------------------------------------


class WrapperIpMissing(ConfigError):
	def __init__(self, ip_name: str) -> None:
		self.ip_name = ip_name
		super().__init__(ip_name)

	def __str__(self) -> str:
		return f"IP '{self.ip_name}' is missing - call add_ip_cfg() before add_wrapper_cfg()"


# --- Sources -----------------------------------------------------------------


class SourceError(ConfigError): ...


class SourceEmptyError(SourceError):
	def __init__(self, prefix: str, name: str) -> None:
		self.name = name
		self.prefix = prefix
		super().__init__(name)

	def __str__(self) -> str:
		return f"{self.prefix} '{self.name}' requires at least one source file"


class SourceMissingError(SourceError):
	def __init__(self, prefix: str, name: str, path: str, file_type: str = "source") -> None:
		self.name = name
		self.prefix = prefix
		self.path = path
		self.file_type = file_type
		super().__init__(name)

	def __str__(self) -> str:
		return f"{self.prefix} '{self.name}' {self.file_type} file not found: '{self.path}'"


# Source spec errors raised by _resolve_sources


class SourceSpecError(SourceError): ...


class SourceSpecMissingKeyError(SourceSpecError):
	def __init__(self, key: str, entry: object, sources: object) -> None:
		self.key = key
		self.entry = entry
		self.sources = sources
		super().__init__(str(entry))

	def __str__(self) -> str:
		return f"Source spec missing required key '{self.key}'.\n  Entry   : {self.entry!r}\n  Sources : {self.sources!r}"


class SourceSpecUnknownStageError(SourceSpecError):
	VALID_STAGES: frozenset[str] = frozenset({"synth", "impl", "ooc", "sim"})

	def __init__(self, unknown: set[str], entry: object) -> None:
		self.unknown = unknown
		self.entry = entry
		super().__init__(str(entry))

	def __str__(self) -> str:
		listed = ", ".join(f"'{s}'" for s in sorted(self.unknown))
		valid = ", ".join(f"'{s}'" for s in sorted(self.VALID_STAGES))
		return f"Source spec unknown stage(s): {listed}.\n  Valid : {valid}\n  Entry : {self.entry!r}"


class WrapperSourcesEmptyError(SourceEmptyError):
	def __init__(self, name: str) -> None:
		super().__init__("Wrapper for IP", name)


class WrapperSourcesMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("Wrapper for IP", name, path)


class IpSourcesEmptyError(SourceEmptyError):
	def __init__(self, name: str) -> None:
		super().__init__("IP", name)


class IpSourcesMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("IP", name, path)


class DesignSourcesMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("Design", name, path)


class AppSourcesEmptyError(SourceEmptyError):
	def __init__(self, name: str) -> None:
		super().__init__("App", name)


class AppSourcesMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("App", name, path)


class AppElfMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("App", name, path, file_type="ELF")


class PlatformXsaMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("Platform", name, path, file_type="XSA")


class PlatformBitstreamMissingError(SourceMissingError):
	def __init__(self, name: str, path: str) -> None:
		super().__init__("Platform", name, path, file_type="bitstream")


class SynthConstraintsMissingError(SourceMissingError):
	def __init__(self, name: str, name_type: str, path: str) -> None:
		super().__init__(f"Synth for {name_type}", name, path, file_type="constraints")


# --- Properties --------------------------------------------------------------


class PropertiesError(ConfigError): ...


class PropertiesNotADictError(PropertiesError):
	def __init__(self, name: str, value: object) -> None:
		self.name = name
		self.value = value
		super().__init__(name)

	def __str__(self) -> str:
		return f"PlatformConfig '{self.name}': properties must be a dict, got {type(self.value).__name__!r}: {self.value!r}"


class PropertiesInvalidValueError(PropertiesError):
	def __init__(self, name: str, key: str, value: object) -> None:
		self.name = name
		self.key = key
		self.value = value
		super().__init__(name)

	def __str__(self) -> str:
		return f"PlatformConfig '{self.name}': property '{self.key}' has unsupported value type {type(self.value).__name__!r}: {self.value!r}"


# --- SubCore identifier ------------------------------------------------------


class SubCoreBdAlreadyExistsError(ConfigError):
	def __init__(self, inst_hier_path: str, core: str, bd: str) -> None:
		self.inst_hier_path = inst_hier_path
		self.core = core
		self.bd = bd
		super().__init__(core)

	def __str__(self) -> str:
		return f"SubCore '{self.core}' at '{self.inst_hier_path}' with bd='{self.bd}' is already specified"


class SubCoreDesignAlreadyExistsError(ConfigError):
	def __init__(self, inst_hier_path: str, core: str, design: str) -> None:
		self.inst_hier_path = inst_hier_path
		self.core = core
		self.design = design
		super().__init__(core)

	def __str__(self) -> str:
		return f"SubCore '{self.core}' at '{self.inst_hier_path}' with design='{self.design}' is already specified"


class SubCoreIdentifierError(ConfigError): ...


class SubCoreIdentifierUnspecifiedError(SubCoreIdentifierError):
	def __init__(self, inst_hier_path: str, core: str) -> None:
		self.inst_hier_path = inst_hier_path
		self.core = core
		super().__init__(core)

	def __str__(self) -> str:
		return f"SubCore '{self.core}' at '{self.inst_hier_path}' requires exactly one of: bd, design"


class SubCoreIdentifierMultipleError(SubCoreIdentifierError):
	def __init__(self, inst_hier_path: str, core: str, bd: str, design: str) -> None:
		self.inst_hier_path = inst_hier_path
		self.core = core
		self.bd = bd
		self.design = design
		super().__init__(core)

	def __str__(self) -> str:
		return f"SubCore '{self.core}' at '{self.inst_hier_path}' specifies both bd='{self.bd}' and design='{self.design}' - pick one"


class SubCoreListIdentifierUnspecifiedError(SubCoreIdentifierError):
	def __str__(self) -> str:
		return "requires exactly one of: bd, design"


class SubCoreListIdentifierMultipleError(SubCoreIdentifierError):
	def __init__(self, bd: str, design: str) -> None:
		self.bd = bd
		self.design = design
		super().__init__()

	def __str__(self) -> str:
		return f"specifies both bd='{self.bd}' and design='{self.design}' - pick one"


# --- Synth identifier --------------------------------------------------------


class SynthIdentifierError(ConfigError): ...


class SynthIdentifierUnspecifiedError(SynthIdentifierError):
	def __str__(self) -> str:
		return "SynthConfig requires exactly one of: bd, core, design"


class SynthIdentifierMultipleError(SynthIdentifierError):
	def __init__(self, design: str | None, core: str | None, bd: str | None) -> None:
		self.design = design
		self.core = core
		self.bd = bd
		super().__init__()

	def __str__(self) -> str:
		parts = []
		if self.design:
			parts.append(f"design='{self.design}'")
		if self.core:
			parts.append(f"core='{self.core}'")
		if self.bd:
			parts.append(f"bd='{self.bd}'")
		return f"SynthConfig received multiple identifiers: {', '.join(parts)} - specify exactly one"


# --- Platform identifier -----------------------------------------------------


class PlatformIdentifierError(ConfigError): ...


class PlatformIdentifierUnspecifiedError(PlatformIdentifierError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__()

	def __str__(self) -> str:
		return f"PlatformConfig '{self.name}' requires exactly one of: bd, design, xsa"


class PlatformIdentifierMultipleError(PlatformIdentifierError):
	def __init__(self, name: str, design: str | None, bd: str | None, xsa: str | None) -> None:
		self.name = name
		self.design = design
		self.bd = bd
		self.xsa = xsa
		super().__init__()

	def __str__(self) -> str:
		parts = []
		if self.design:
			parts.append(f"design='{self.design}'")
		if self.bd:
			parts.append(f"bd='{self.bd}'")
		if self.xsa:
			parts.append(f"xsa='{self.xsa}'")
		return f"PlatformConfig '{self.name}' received multiple identifiers: {', '.join(parts)} - specify exactly one"


# --- App ---------------------------------------------------------------------


class AppPlatformUnspecifiedError(ConfigError):
	def __init__(self, app_name: str) -> None:
		self.app_name = app_name
		super().__init__(app_name)

	def __str__(self) -> str:
		return f"AppConfig '{self.app_name}' requires a platform - pass platform=<name>"


# --- Ambiguous ---------------------------------------------------------------


class AmbiguousIdentifierError(ConfigError):
	def __init__(self, kind: str, id: str, candidates: list[str]) -> None:
		self.kind = kind
		self.id = id
		self.candidates = candidates
		super().__init__(id)

	def __str__(self) -> str:
		listed = ", ".join(f"'{c}'" for c in self.candidates)
		return f"{self.kind} identifier {self.id!r} is ambiguous - matches: {listed}"


class AmbiguousCoreError(AmbiguousIdentifierError):
	def __init__(self, id: str, candidates: list[str]) -> None:
		super().__init__("CoreConfig", id, candidates)


# --- Core identifier ---------------------------------------------------------


class CoreIdentifierError(ConfigError): ...


class CoreIdentifierMultipleError(CoreIdentifierError):
	def __init__(self, name: str, ip: str, vlnv: str) -> None:
		self.ip = ip
		self.vlnv = vlnv
		self.name = name
		super().__init__()

	def __str__(self) -> str:
		return f"Core '{self.name}' received multiple identifiers: ip={self.ip}, vlnv={self.vlnv} - specify exactly one"


class CoreIdentifierUnspecifiedError(CoreIdentifierError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"CoreConfig '{self.name}' requires at least one of: ip, vlnv"


class CoreVlnvUnspecifiedError(ConfigError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"CoreConfig '{self.name}' requires: vlnv"


# --- Mode / backend ----------------------------------------------------------


class ModeError(BaseException): ...


class BackendError(BaseException): ...


class InvalidSimulationMode(ModeError):
	def __init__(self, mode: str) -> None:
		self.mode = mode
		super().__init__()

	def __str__(self) -> str:
		return f"Invalid simulation mode '{self.mode}'"


class InvalidSimulationBackend(BackendError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__()

	def __str__(self) -> str:
		return f"Invalid simulation backend '{self.name}'"


# --- Formal ------------------------------------------------------------------


class FormalError(XvivError): ...


class FormalAlreadyExistsError(FormalError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"Formal target '{self.name}' is already defined"


class FormalDoesNotExistError(FormalError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"Formal target '{self.name}' is not defined in project.toml"


class FormalNoTargetsError(FormalError):
	def __str__(self) -> str:
		return "No [[formal]] targets defined in project.toml"


class FormalSbyNotFoundError(FormalError):
	def __str__(self) -> str:
		return "SymbiYosys (sby) not found on PATH.\nInstall it with:  pip install symbiyosys\nor:               sudo apt install symbiyosys"


class FormalSourceMissingError(FormalError):
	def __init__(self, name: str, path: str) -> None:
		self.name = name
		self.path = path
		super().__init__(path)

	def __str__(self) -> str:
		return f"Formal target '{self.name}': source file not found: '{self.path}'"


class FormalInvalidModeError(FormalError):
	def __init__(self, name: str, mode: str) -> None:
		self.name = name
		self.mode = mode
		super().__init__(mode)

	def __str__(self) -> str:
		return f"Formal target '{self.name}': invalid mode '{self.mode}' - must be one of: bmc, prove, cover"


# --- Verilator ---------------------------------------------------------------


class VerilatorNotFoundError(XvivError):
	def __init__(self) -> None:
		super().__init__("verilator not found on PATH - install verilator or add it to PATH")


class VerilatorCompileError(XvivError):
	def __init__(self, top: str, returncode: int) -> None:
		self.top = top
		self.returncode = returncode
		super().__init__(f"verilator compilation of '{top}' failed (exit {returncode})")


class VerilatorBinaryMissingError(XvivError):
	def __init__(self, path: str) -> None:
		self.path = path
		super().__init__(f"verilated binary not found: {path} - run compile step first")


# --- UVM ---------------------------------------------------------------------


class UvmPkgDirRequiredError(XvivError):
	def __init__(self, sim_name: str) -> None:
		self.sim_name = sim_name
		super().__init__(
			f"sim '{sim_name}': uvm=True with backend='verilator' requires uvm_pkg_dir to be set (verilator does not ship a pre-compiled UVM library)"
		)


class UvmNotSupportedError(XvivError):
	def __init__(self, backend: str) -> None:
		self.backend = backend
		super().__init__(f"UVM is not supported by backend '{backend}'")


# --- TCL project -------------------------------------------------------------


class InMemoryProjectAlreadyExistsError(XvivError):
	def __init__(self, name: str) -> None:
		self.name = name
		super().__init__(name)

	def __str__(self) -> str:
		return f"In-memory project '{self.name}' already exists - cannot create a second one"


# --- Target filter -----------------------------------------------------------


class TargetFilterUnspecifiedError(XvivError): ...


class ProcessorTargetFilterUnspecifiedError(TargetFilterUnspecifiedError):
	def __str__(self) -> str:
		return "processor_target_filter is required but was not set"


class FpgaTargetFilterUnspecifiedError(TargetFilterUnspecifiedError):
	def __str__(self) -> str:
		return "fpga_target_filter is required but was not set"


# --- Hardware programming ----------------------------------------------------


class ResetDurationUnspecifiedError(XvivError):
	def __str__(self) -> str:
		return "processor_reset_duration must be set when programming both bitstream and ELF"


# --- Catalog -----------------------------------------------------------------


class CoreVlnvNotInCatalogError(XvivError):
	def __init__(self, name: str, vlnv: str) -> None:
		self.name = name
		self.vlnv = vlnv
		super().__init__(vlnv)

	def __str__(self) -> str:
		return f"Core '{self.name}': VLNV '{self.vlnv}' not found in IP catalog"


# --- Synth (builder) ---------------------------------------------------------


class SynthNoIdentifierError(XvivError):
	def __str__(self) -> str:
		return "synth: specify at least one of --bd, --design, or --core"


class SynthConfigConflictError(XvivError): ...


class SynthBitstreamRequiresRouteError(SynthConfigConflictError):
	def __str__(self) -> str:
		return "bitstream_file is set but run_route=False - route must complete before bitstream generation"


class SynthXsaRequiresRouteError(SynthConfigConflictError):
	def __str__(self) -> str:
		return "hw_platform_xsa_file is set but run_route=False - route must complete before XSA export"


class SynthResumeDcpMissingError(XvivError):
	def __init__(self, stage: str, path: str | None) -> None:
		self.stage = stage
		self.path = path
		super().__init__(path or "<none>")

	def __str__(self) -> str:
		return f"resume={self.stage}: DCP not found: '{self.path}'"


class SynthResumeInvalidError(XvivError):
	def __init__(self, stage: str, VALID=("auto", "synth", "place", "route")) -> None:
		self.stage = stage
		self.VALID = VALID
		super().__init__(stage)

	def __str__(self) -> str:
		valid = ", ".join(f"'{s}'" for s in self.VALID)
		return f"Invalid resume stage '{self.stage}' - must be one of: {valid}"


class OocStubMissingError(XvivError):
	def __init__(self, core: str, path: str) -> None:
		self.core = core
		self.path = path
		super().__init__(path)

	def __str__(self) -> str:
		return f"OOC stub missing for subcore '{self.core}': '{self.path}'\n  hint: run 'xviv synth --core {self.core}' first"


# cmd - Synthesis


class SynthUsrAccessValueEmbedGitShaError(XvivError):
	def __str__(self) -> str:
		return "usr_access_type='git' requires a valid Git SHA. Verify that this project is inside an initialized Git repository."


class ProjectConfigTomlFileMissingError(XvivError):
	def __str__(self) -> str:
		return "project.toml missing"


class ProjectConfigUnknownKeyError(XvivError):
	def __init__(self, key: str, file: str):
		self.key = key
		self.file = file
		super().__init__(key)

	def __str__(self) -> str:
		return f"unknown key '{self.key}' in config file '{self.file}'"


class ProgramUnspecifiedIdentifiersError(XvivError):
	def __str__(self) -> str:
		return "specify (app_name | elf_file) and/or (platform_name | bitstream_file)"


class PlatformBspDirectoryMissingError(XvivError):
	def __init__(self, name: str, dir: str):
		self.name = name
		self.dir = dir
		super().__init__(name)

	def __str__(self) -> str:
		return f"BSP directory not found: {self.dir}\n\tRun: xviv create --platform {self.name}"


class ToolError(XvivError):
	"""Base for internal tool-resolution errors."""


class BashNotFoundError(ToolError):
	def __str__(self) -> str:
		return "bash is required but not found on PATH"


class SettingsEnvUnsetError(ToolError):
	def __init__(self, tool: str, SETTINGS_ENV_VAR: str) -> None:
		self.tool = tool
		self.SETTINGS_ENV_VAR = SETTINGS_ENV_VAR

	def __str__(self) -> str:
		return (
			f"'{self.tool}' not found on PATH and {self.SETTINGS_ENV_VAR} is not set.\n"
			f"Set it to the path of your settings script, e.g.:\n"
			f"  export {self.SETTINGS_ENV_VAR}=/tools/Xilinx/<version>/settings64.sh"
		)


class SettingsFileNotFoundError(ToolError):
	def __init__(self, path: str) -> None:
		self.path = path

	def __str__(self) -> str:
		return f"settings file not found: {self.path!r}"


class SettingsSourceError(ToolError):
	def __init__(self, path: str, stderr: str) -> None:
		self.path = path
		self.stderr = stderr

	def __str__(self) -> str:
		return f"failed to source {self.path!r}:\n{self.stderr}"


class ToolBinaryNotFoundError(ToolError):
	def __init__(self, tool: str, _TOOL_NOT_FOUND_HINT: str, SETTINGS_ENV_VAR: str) -> None:
		self.tool = tool
		self._TOOL_NOT_FOUND_HINT = _TOOL_NOT_FOUND_HINT
		self.SETTINGS_ENV_VAR = SETTINGS_ENV_VAR

	def __str__(self) -> str:
		return self._TOOL_NOT_FOUND_HINT.format(tool=self.tool, env_var=self.SETTINGS_ENV_VAR)


class JobFailedError(XvivError):
	"""Raised by run_jobs() when one or more jobs exit with a non-zero status.

	Attributes:
		failed: List of (label, exc) pairs for every job that failed.
				exc is either a CalledProcessError (non-zero returncode) or
				another BaseException (unexpected error in the sink).
	"""

	def __init__(self, failed: list[tuple[str, BaseException]]) -> None:
		self.failed = failed
		labels = ", ".join(label for label, _ in failed)
		super().__init__(f"{len(failed)} job(s) failed: {labels}")


class VivadoBinaryNotFoundError(XvivError):
	"""Raised when the Vivado binary cannot be located."""
