from __future__ import annotations


# =============================================================================
# Root
# =============================================================================

class XvivError(Exception):
    """Base class for all xviv errors."""

class UninitializedError(XvivError):
    """A required component was used before being configured."""


class UninitializedVivadoError(UninitializedError):
    def __str__(self) -> str:
        return "VivadoConfig is not initialized - call add_vivado_cfg() first"


class UninitializedVitisError(UninitializedError):
    def __str__(self) -> str:
        return "VitisConfig is not initialized - call add_vitis_cfg() first"


class UninitializedCoreCatalogError(UninitializedError):
    def __str__(self) -> str:
        return "IP Catalog is not initialized - call add_vivado_cfg() first"


# =============================================================================
# Path errors
# =============================================================================

class InvalidPathError(XvivError):
    def __init__(self, path: str, context: str = ""):
        self.path = path
        self.context = context
        super().__init__(path)

    def __str__(self) -> str:
        suffix = f" ({self.context})" if self.context else ""
        return f"Path does not exist: '{self.path}'{suffix}"


# =============================================================================
# Resolve errors
# =============================================================================

class ResolveError(XvivError):
    """Failed to resolve a value from available data."""


class VlnvResolveError(ResolveError):
    def __init__(self, vlnv: str):
        self.vlnv = vlnv
        super().__init__(vlnv)

    def __str__(self) -> str:
        return f"Unable to resolve VLNV '{self.vlnv}' - check your IP repos and catalog entries"


class FpgaResolveError(ResolveError):
    def __init__(self, fpga: str):
        self.fpga = fpga
        super().__init__(fpga)

    def __str__(self) -> str:
        return f"Unable to resolve FPGA '{self.fpga}'"


# =============================================================================
# Config errors - base classes
# =============================================================================

class ConfigError(XvivError):
    """Base for all configuration errors."""


class AlreadyExistsError(ConfigError):
    def __init__(self, kind: str, name: str):
        self.kind = kind
        self.name = name
        super().__init__(name)

    def __str__(self) -> str:
        return f"{self.kind} entry already exists: '{self.name}'"


class DoesNotExistError(ConfigError):
    def __init__(self, kind: str, name: str):
        self.kind = kind
        self.name = name
        super().__init__(name)

    def __str__(self) -> str:
        return f"{self.kind} entry not found: '{self.name}'"


# =============================================================================
# AlreadyExists - one subclass per entity type
# (Keeps isinstance checks and catch blocks precise)
# =============================================================================

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


class SubCoreAlreadyExistsError(AlreadyExistsError):
    def __init__(self, name: str) -> None:
        super().__init__("SubCore", name)


# =============================================================================
# DoesNotExist - one subclass per entity type
# =============================================================================
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


class SynthDoesNotExistError(DoesNotExistError):
    def __init__(self, design: str | None, core: str | None, bd: str | None) -> None:
        self.design = design
        self.core = core
        self.bd = bd
        name = design or core or bd or "<unknown>"
        super().__init__("SynthConfig", name)

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


# =============================================================================
# FPGA-specific
# =============================================================================

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

# =============================================================================
# Wrapper-specific
# =============================================================================

class WrapperIpMissing(ConfigError):
    def __init__(self, ip_name: str) -> None:
        self.ip_name = ip_name
        super().__init__(ip_name)

    def __str__(self) -> str:
        return f"IP '{self.ip_name}' is missing or cannot be determined. Make sure add_ip_cfg() is called before add_wrapper_cfg()."


# =============================================================================
# Source
# =============================================================================

class SourceError(ConfigError):
    """Base for wrapper source list problems."""

class SourceEmptyError(SourceError):
    def __init__(self, prefix: str, name: str) -> None:
        self.name = name
        self.prefix = prefix
        super().__init__(name)

    def __str__(self) -> str:
        return f"{self.prefix} '{self.name}' requires at least one source file"

class SourceMissingError(SourceError):
    def __init__(self, prefix: str, name: str, path: str, file_type: str = 'source') -> None:
        self.name = name
        self.prefix = prefix
        self.path = path
        self.file_type = file_type
        super().__init__(name)

    def __str__(self) -> str:
        return f"{self.prefix} '{self.name}' {self.file_type} file not found: '{self.path}'"


class WrapperSourcesEmptyError(SourceEmptyError):
    def __init__(self, name: str) -> None:
        super().__init__('Wrapper for IP', name)

class IpSourcesEmptyError(SourceEmptyError):
    def __init__(self, name: str) -> None:
        super().__init__('IP', name)


class WrapperSourcesMissingError(SourceMissingError):
    def __init__(self, name: str, path: str) -> None:
        super().__init__('Wrapper for IP', name, path)

class IpSourcesMissingError(SourceMissingError):
    def __init__(self, name: str, path: str) -> None:
        super().__init__('IP', name, path)

class SynthConstraintsSourcesMissingError(SourceMissingError):
    def __init__(self, name: str, name_type: str, path: str) -> None:
        super().__init__(f'Synth for {name_type}', name, path, file_type='constraints')

# =============================================================================
# SubCore identifier
# =============================================================================

class SubCoreIdentifierError(ConfigError):
    """Base for subcore bd/design identifier problems."""


class SubCoreIdentifierUnspecifiedError(SubCoreIdentifierError):
    def __init__(self, inst_hier_path: str, core: str) -> None:
        self.inst_hier_path = inst_hier_path
        self.core = core
        super().__init__(core)

    def __str__(self) -> str:
        return f"SubCore '{self.core}' at '{self.inst_hier_path}' requires exactly one of: bd, design"


class SubCoreIdentifierMultipleError(SubCoreIdentifierError):
    def __init__(self, core: str, bd: str, design: str) -> None:
        # self.inst_hier_path = inst_hier_path
        self.core = core
        self.bd = bd
        self.design = design
        super().__init__(core)

    def __str__(self) -> str:
        # return f"SubCore '{self.core}' at '{self.inst_hier_path}' specifies both bd='{self.bd}' and design='{self.design}' - pick one"
        return f"SubCore '{self.core}' specifies both bd='{self.bd}' and design='{self.design}' - pick one"


# =============================================================================
# Synth identifier
# =============================================================================

class SynthIdentifierError(ConfigError):
    """Base for synth bd/core/design identifier problems."""


class SynthIdentifierUnspecifiedError(SynthIdentifierError):
    def __str__(self) -> str:
        return "SynthConfig requires exactly one of: bd, core, design"


class SynthIdentifierMultipleError(SynthIdentifierError):
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        super().__init__(ids)

    def __str__(self) -> str:
        return f"SynthConfig received multiple identifiers: {self.ids} - specify exactly one"


# =============================================================================
# Platform identifier
# =============================================================================

class PlatformIdentifierError(ConfigError):
    """Base for platform bd/design/xsa identifier problems."""


class PlatformIdentifierUnspecifiedError(PlatformIdentifierError):
    def __str__(self) -> str:
        return "PlatformConfig requires exactly one of: bd, design, xsa"


class PlatformIdentifierMultipleError(PlatformIdentifierError):
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        super().__init__(ids)

    def __str__(self) -> str:
        return f"PlatformConfig received multiple identifiers: {self.ids} - specify exactly one"


# =============================================================================
# App-specific
# =============================================================================

class AppPlatformUnspecifiedError(ConfigError):
    def __init__(self, app_name: str) -> None:
        self.app_name = app_name
        super().__init__(app_name)

    def __str__(self) -> str:
        return f"AppConfig '{self.app_name}' requires a platform - pass platform=<name>"

# =============================================================================
# Ambiguous
# =============================================================================

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

