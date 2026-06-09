"""Tests for xviv.utils.error - hierarchy and message content."""

import pytest

from xviv.utils.error import (
	AlreadyExistsError,
	AppAlreadyExistsError,
	AppDoesNotExistError,
	BdAlreadyExistsError,
	ConfigError,
	CoreAlreadyExistsError,
	CoreDoesNotExistError,
	DesignAlreadyExistsError,
	DesignDoesNotExistError,
	DoesNotExistError,
	FormalSbyNotFoundError,
	FpgaAlreadyExistsError,
	FpgaPartUnspecifiedError,
	InMemoryProjectAlreadyExistsError,
	InvalidPathError,
	InvalidSimulationBackend,
	InvalidSimulationMode,
	IpAlreadyExistsError,
	IpDoesNotExistError,
	IpSourcesEmptyError,
	IpSourcesMissingError,
	JobFailedError,
	NoFpgaError,
	OocStubMissingError,
	PlatformAlreadyExistsError,
	PlatformDoesNotExistError,
	ProjectConfigUnknownKeyError,
	SimAlreadyExistsError,
	SimDoesNotExistError,
	SourceSpecMissingKeyError,
	SourceSpecUnknownStageError,
	SynthAlreadyExistsError,
	SynthConstraintsMissingError,
	SynthIdentifierMultipleError,
	SynthIdentifierUnspecifiedError,
	SynthResumeDcpMissingError,
	SynthResumeInvalidError,
	SynthUsrAccessValueEmbedGitShaError,
	UninitializedVivadoError,
	VivadoAlreadySpecifiedError,
	XvivError,
)


@pytest.mark.unit
class TestErrorHierarchy:
	"""All XvivError subclasses are properly rooted."""

	def test_config_errors_are_xviv_errors(self):
		for cls in [
			FpgaAlreadyExistsError,
			IpAlreadyExistsError,
			CoreAlreadyExistsError,
			SynthAlreadyExistsError,
			SimAlreadyExistsError,
			BdAlreadyExistsError,
			DesignAlreadyExistsError,
			PlatformAlreadyExistsError,
			AppAlreadyExistsError,
		]:
			assert issubclass(cls, XvivError)
			assert issubclass(cls, Exception)

	def test_does_not_exist_errors(self):
		for cls in [
			FpgaAlreadyExistsError,
			CoreDoesNotExistError,
			DesignDoesNotExistError,
			SimDoesNotExistError,
			PlatformDoesNotExistError,
			AppDoesNotExistError,
			IpDoesNotExistError,
		]:
			assert issubclass(cls, XvivError)

	def test_already_exists_is_config_error(self):
		assert issubclass(AlreadyExistsError, ConfigError)
		assert issubclass(ConfigError, XvivError)

	def test_does_not_exist_is_config_error(self):
		assert issubclass(DoesNotExistError, ConfigError)


@pytest.mark.unit
class TestErrorMessages:
	def test_fpga_already_exists_contains_name(self):
		err = FpgaAlreadyExistsError("my_fpga")
		assert "my_fpga" in str(err)

	def test_core_does_not_exist_contains_name(self):
		err = CoreDoesNotExistError("my_core")
		assert "my_core" in str(err)

	def test_invalid_simulation_backend_contains_backend(self):
		err = InvalidSimulationBackend("ngspice")
		assert "ngspice" in str(err)

	def test_invalid_simulation_mode_contains_mode(self):
		err = InvalidSimulationMode("bogus_mode")
		assert "bogus_mode" in str(err)

	def test_uninitialized_vivado_is_informative(self):
		err = UninitializedVivadoError()
		assert "vivado" in str(err).lower() or "VivadoConfig" in str(err)

	def test_fpga_part_unspecified_contains_name(self):
		err = FpgaPartUnspecifiedError("my_fpga")
		assert "my_fpga" in str(err)

	def test_no_fpga_error_is_informative(self):
		err = NoFpgaError()
		assert len(str(err)) > 5

	def test_synth_dcp_missing_contains_stage_and_path(self):
		err = SynthResumeDcpMissingError("place", "/some/path.dcp")
		assert "place" in str(err)
		assert "/some/path.dcp" in str(err)

	def test_synth_resume_invalid_contains_stage(self):
		err = SynthResumeInvalidError("garbage")
		assert "garbage" in str(err)

	def test_ooc_stub_missing_contains_core_and_path(self):
		err = OocStubMissingError("my_core", "/path/to/stub.dcp")
		assert "my_core" in str(err)
		assert "/path/to/stub.dcp" in str(err)

	def test_job_failed_error_contains_labels(self):
		exc = ValueError("exit code 1")
		err = JobFailedError([("job_a", exc), ("job_b", exc)])
		msg = str(err)
		assert "job_a" in msg
		assert "job_b" in msg

	def test_source_spec_unknown_stage_contains_stage(self):
		err = SourceSpecUnknownStageError({"badstage"}, {"file": "x.sv"})
		assert "badstage" in str(err)

	def test_source_spec_missing_key_contains_key(self):
		err = SourceSpecMissingKeyError("used_in", {}, [])
		assert "used_in" in str(err)

	def test_project_config_unknown_key_contains_key(self):
		err = ProjectConfigUnknownKeyError("unknown_thing", "project.toml")
		assert "unknown_thing" in str(err)

	def test_synth_identifier_unspecified_is_informative(self):
		err = SynthIdentifierUnspecifiedError()
		assert len(str(err)) > 5

	def test_synth_identifier_multiple_contains_identifiers(self):
		err = SynthIdentifierMultipleError(design="d1", core="c1", bd=None)
		assert "d1" in str(err)
		assert "c1" in str(err)

	def test_formal_sby_not_found_is_informative(self):
		err = FormalSbyNotFoundError()
		msg = str(err)
		assert "sby" in msg.lower() or "SymbiYosys" in msg

	def test_invalid_path_contains_path(self):
		err = InvalidPathError("/bad/path")
		assert "/bad/path" in str(err)

	def test_vivado_already_specified_is_informative(self):
		err = VivadoAlreadySpecifiedError()
		assert "VivadoConfig" in str(err) or "vivado" in str(err).lower()

	def test_in_memory_project_already_exists_contains_name(self):
		err = InMemoryProjectAlreadyExistsError("proj")
		assert "proj" in str(err)

	def test_ip_sources_empty_contains_name(self):
		err = IpSourcesEmptyError("my_ip")
		assert "my_ip" in str(err)

	def test_ip_sources_missing_contains_path(self):
		err = IpSourcesMissingError("my_ip", "/missing/file.sv")
		assert "/missing/file.sv" in str(err)

	def test_synth_constraints_missing_contains_path(self):
		err = SynthConstraintsMissingError("my_synth", "Design", "/missing/const.xdc")
		assert "/missing/const.xdc" in str(err)

	def test_usr_access_git_sha_error_is_informative(self):
		err = SynthUsrAccessValueEmbedGitShaError()
		assert len(str(err)) > 10
