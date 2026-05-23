from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils import error

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
	config_file = tmp_path / "project.toml"
	config_file.touch()
	c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
	c.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
	return c


@pytest.fixture
def cmd(cfg):
	return ConfigTclCommands(cfg)


@pytest.fixture
def vivado_mock():
	m = MagicMock()
	m.max_threads = 4
	return m


# _require_project succeeds once (needs vivado); subsequent calls check the flag only.
def _prime_project(cmd, cfg, vivado_mock):
	with patch.object(cfg, "get_vivado", return_value=vivado_mock):
		cmd._require_project()


# ---------------------------------------------------------------------------
# _require_project
# ---------------------------------------------------------------------------


class TestRequireProject:
	def test_already_exists(self, cmd, cfg, vivado_mock):
		_prime_project(cmd, cfg, vivado_mock)
		with pytest.raises(error.InMemoryProjectAlreadyExistsError):
			cmd._require_project()

	def test_exists_ok_returns_false(self, cmd, cfg, vivado_mock):
		_prime_project(cmd, cfg, vivado_mock)
		assert cmd._require_project(exists_ok=True) is False


# ---------------------------------------------------------------------------
# _processor_status
# ---------------------------------------------------------------------------


class TestProcessorStatus:
	def test_filter_unspecified(self, cmd):
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd._processor_status()


# ---------------------------------------------------------------------------
# program
# ---------------------------------------------------------------------------


class TestProgram:
	def test_fpga_filter_unspecified(self, cmd):
		with pytest.raises(error.FpgaTargetFilterUnspecifiedError):
			cmd.program(bitstream_file="/any/path.bit")

	def test_bitstream_not_found(self, cmd):
		with pytest.raises(error.InvalidPathError):
			cmd.program(bitstream_file="/nonexistent/top.bit", fpga_target_filter="fpga*")

	def test_elf_not_found(self, cmd):
		with pytest.raises(error.InvalidPathError):
			cmd.program(elf_file="/nonexistent/app.elf")

	def test_reset_duration_unspecified(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		elf = tmp_path / "app.elf"
		elf.touch()
		with pytest.raises(error.ResetDurationUnspecifiedError):
			cmd.program(
				bitstream_file=str(bitstream),
				fpga_target_filter="fpga*",
				elf_file=str(elf),
			)

	def test_processor_filter_unspecified(self, cmd, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd.program(elf_file=str(elf))


# ---------------------------------------------------------------------------
# processor_cntrl
# ---------------------------------------------------------------------------


class TestProcessorCntrl:
	def test_filter_unspecified(self, cmd):
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd.processor_cntrl(reset=True, status=False)


# ---------------------------------------------------------------------------
# create_core
# ---------------------------------------------------------------------------


class TestCreateCore:
	def test_vlnv_not_in_catalog(self, cfg, cmd):
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0")
		with patch.object(cfg, "get_catalog") as mock_catalog:
			mock_catalog.return_value.lookup_optional.return_value = None
			with pytest.raises(error.CoreVlnvNotInCatalogError) as exc_info:
				cmd.create_core("my_core")
		assert exc_info.value.name == "my_core"
		assert exc_info.value.vlnv == "a:b:my_core:1.0"


# ---------------------------------------------------------------------------
# synth - validation (all raised before _require_project)
# ---------------------------------------------------------------------------


class TestSynthValidation:
	def test_no_identifier(self, cmd):
		with pytest.raises(error.SynthNoIdentifierError):
			cmd.synth()

	def test_bitstream_requires_route(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design", run_route=False, bitstream=True)
		with pytest.raises(error.SynthBitstreamRequiresRouteError):
			cmd.synth(design="my_design")

	def test_xsa_requires_route(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design", run_route=False, bitstream=False, hw_platform=True)
		with pytest.raises(error.SynthXsaRequiresRouteError):
			cmd.synth(design="my_design")

	# NOTE: SynthResumeInvalidError requires adding the elif branch to synth():
	#   elif resume is not None:
	#       raise error.SynthResumeInvalidError(resume)
	def test_resume_invalid(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design")
		with pytest.raises(error.SynthResumeInvalidError) as exc_info:
			cmd.synth(design="my_design", resume="badstage")
		assert exc_info.value.stage == "badstage"


# ---------------------------------------------------------------------------
# synth - resume DCP missing (resume branches run before _require_project)
# ---------------------------------------------------------------------------


class TestSynthResumeDcp:
	@pytest.fixture(autouse=True)
	def _setup(self, cfg):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design")

	def test_resume_route_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="route")
		assert exc_info.value.stage == "route"

	def test_resume_place_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="place")
		assert exc_info.value.stage == "place"

	def test_resume_synth_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="synth")
		assert exc_info.value.stage == "synth"


# ---------------------------------------------------------------------------
# synth - OOC stub missing (runs after _require_project; mock vivado)
# ---------------------------------------------------------------------------


class TestSynthOocStub:
	def test_stub_missing(self, cfg, vivado_mock):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(
			design="my_design",
			out_of_context_subcores=True,
			bitstream=False,
			hw_platform=False,
		)
		cfg.add_core_cfg("sub_core", vlnv="a:b:sub_core:1.0")
		cfg.add_subcore_cfg(core="sub_core", inst_hier_path="/top/u_sub", design="my_design")
		cfg.add_synth_cfg(
			core="sub_core",
			run_place=False,
			place_dcp=False,
			run_route=False,
			route_dcp=False,
			run_phys_opt=False,
			run_opt=False,
		)

		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			with pytest.raises(error.OocStubMissingError) as exc_info:
				cmd.synth(design="my_design")

		assert exc_info.value.core == "sub_core"
