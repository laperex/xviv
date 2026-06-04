# ---------------------------------------------------------------------------
# Containerized Parameters
# ---------------------------------------------------------------------------

import dataclasses


@dataclasses.dataclass
class CreateParams:
	generate: bool = False
	edit: bool = False
	nogui: bool = False
	recursive: bool = False


@dataclasses.dataclass
class IpCreateParams(CreateParams):
	regenerate: bool = False


@dataclasses.dataclass
class BdCreateParams(CreateParams):
	source_file: str | bool = True


@dataclasses.dataclass
class CoreCreateParams(CreateParams):
	pass


@dataclasses.dataclass
class AppCreateParams:
	build: bool = False


@dataclasses.dataclass
class PlatformCreateParams:
	build: bool = False


@dataclasses.dataclass
class EditParams:
	nogui: bool = False


@dataclasses.dataclass
class GenerateParams:
	force: bool = False
	reset: bool = False


@dataclasses.dataclass
class OpenParams:
	nogui: bool = False


@dataclasses.dataclass
class ProcessorParams:
	processor_target_filter: str = "Microblaze #0*"
	reset: bool = False
	status: bool = False


@dataclasses.dataclass
class AppBuildParams:
	info: bool = False


@dataclasses.dataclass
class PlatformBuildParams:
	pass


@dataclasses.dataclass
class ProgramParams:
	bitstream_file: str | None = None
	elf_file: str | None = None
	app_name: str | None = None
	platform_name: str | None = None
	processor_target_filter: str = "Microblaze #0*"
	processor_reset_duration: int = 500
	fpga_target_filter: str = "xc7a*"


@dataclasses.dataclass
class SimulateParams:
	uvm_name: str | None = None
	run: str = "all"
	mode: str = "default"


@dataclasses.dataclass
class SynthParams:
	resume: str | None = None
	parallel_subcore_synth: bool = False


@dataclasses.dataclass
class ValidateParams:
	level: str | None = None
	io: str | None = None
	design: str | None = None
	bd: str | None = None
	core: str | None = None
