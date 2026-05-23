from __future__ import annotations

import pytest
from xviv.config.project import XvivConfig
from xviv.utils import error

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path) -> XvivConfig:
	"""Bare XvivConfig - no vivado/vitis/fpga configured."""
	config_file = tmp_path / "project.toml"
	config_file.touch()
	return XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))


@pytest.fixture
def cfg_with_fpga(cfg) -> XvivConfig:
	cfg.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
	return cfg


@pytest.fixture
def cfg_with_vivado(cfg_with_fpga, tmp_path) -> XvivConfig:
	vivado = tmp_path / "vivado"
	vivado.mkdir()
	cfg_with_fpga.add_vivado_cfg(str(vivado))
	return cfg_with_fpga


@pytest.fixture
def cfg_full(cfg_with_vivado, tmp_path) -> XvivConfig:
	vitis = tmp_path / "vitis"
	vitis.mkdir()
	cfg_with_vivado.add_vitis_cfg(str(vitis))
	return cfg_with_vivado


# ---------------------------------------------------------------------------
# Uninitialized
# ---------------------------------------------------------------------------


class TestUninitialized:
	def test_vivado(self, cfg):
		with pytest.raises(error.UninitializedVivadoError):
			cfg.get_vivado()

	def test_vitis(self, cfg):
		with pytest.raises(error.UninitializedVitisError):
			cfg.get_vitis()

	def test_catalog(self, cfg):
		with pytest.raises(error.UninitializedCoreCatalogError):
			cfg.get_catalog()


# ---------------------------------------------------------------------------
# InvalidPathError  (build())
# ---------------------------------------------------------------------------


class TestBuildInvalidPath:
	def test_bad_vivado_path(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
		c.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
		c.add_vivado_cfg("/nonexistent/vivado")
		c.add_vitis_cfg("/nonexistent/vitis")
		with pytest.raises(error.InvalidPathError):
			c.build()

	def test_bad_vitis_path(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
		c.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
		c.add_vivado_cfg(str(vivado))
		c.add_vitis_cfg("/nonexistent/vitis")
		with pytest.raises(error.InvalidPathError):
			c.build()


# ---------------------------------------------------------------------------
# FPGA
# ---------------------------------------------------------------------------


class TestFpga:
	def test_no_fpga(self, cfg):
		with pytest.raises(error.NoFpgaError):
			_ = cfg._get_fpga_cfg_default

	def test_part_unspecified(self, cfg):
		with pytest.raises(error.FpgaPartUnspecifiedError):
			cfg.add_fpga_cfg("xczu9")

	def test_already_exists(self, cfg_with_fpga):
		with pytest.raises(error.FpgaAlreadyExistsError):
			cfg_with_fpga.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.FpgaDoesNotExistError):
			cfg_with_fpga.get_fpga("missing")

	def test_resolve_error(self, cfg_with_fpga):
		with pytest.raises(error.FpgaResolveError):
			cfg_with_fpga._resolve_fpga("nonexistent_fpga")

	def test_ref_mismatch(self, cfg):
		cfg.add_fpga_cfg("fpga_a", fpga_part="xczu9eg-ffvb1156-2-e")
		cfg.add_fpga_cfg("fpga_b", fpga_part="xczu7ev-fbvb900-1-i")
		cfg.add_design_cfg("my_design", sources=[], fpga="fpga_a")
		with pytest.raises(error.FpgaRefMismatchError):
			cfg.add_synth_cfg(design="my_design", fpga="fpga_b")


# ---------------------------------------------------------------------------
# VivadoConfig / VitisConfig
# ---------------------------------------------------------------------------


class TestVivadoVitis:
	def test_vivado_already_specified(self, cfg_with_vivado, tmp_path):
		with pytest.raises(error.VivadoAlreadySpecifiedError):
			cfg_with_vivado.add_vivado_cfg(str(tmp_path))

	def test_vitis_already_specified(self, cfg_full, tmp_path):
		with pytest.raises(error.VitisAlreadySpecifiedError):
			cfg_full.add_vitis_cfg(str(tmp_path))


# ---------------------------------------------------------------------------
# IP
# ---------------------------------------------------------------------------


class TestIp:
	def test_already_exists(self, cfg_with_fpga, tmp_path):
		src = tmp_path / "a.v"
		src.touch()
		cfg_with_fpga.add_ip_cfg("my_ip", sources=[str(src)])
		with pytest.raises(error.IpAlreadyExistsError):
			cfg_with_fpga.add_ip_cfg("my_ip", sources=[str(src)])

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.IpDoesNotExistError):
			cfg_with_fpga.get_ip("missing")

	def test_sources_empty(self, cfg_with_fpga):
		cfg_with_fpga.add_ip_cfg("my_ip", sources=[])
		with pytest.raises(error.IpSourcesEmptyError):
			cfg_with_fpga.validate_ip("my_ip")

	def test_sources_missing(self, cfg_with_fpga):
		cfg_with_fpga.add_ip_cfg("my_ip", sources=["/nonexistent/file.v"])
		with pytest.raises(error.IpSourcesMissingError):
			cfg_with_fpga.validate_ip("my_ip")


# ---------------------------------------------------------------------------
# Wrapper
# ---------------------------------------------------------------------------


class TestWrapper:
	def _add_ip(self, cfg, tmp_path):
		src = tmp_path / "a.v"
		src.touch()
		cfg.add_ip_cfg("my_ip", sources=[str(src)])

	def test_ip_missing(self, cfg_with_fpga):
		with pytest.raises(error.WrapperIpMissing):
			cfg_with_fpga.add_wrapper_cfg(ip="ghost", sources=[])

	def test_already_exists(self, cfg_with_fpga, tmp_path):
		self._add_ip(cfg_with_fpga, tmp_path)
		src = tmp_path / "wrap.sv"
		src.touch()
		cfg_with_fpga.add_wrapper_cfg(ip="my_ip", sources=[str(src)])
		with pytest.raises(error.WrapperAlreadyExistsError):
			cfg_with_fpga.add_wrapper_cfg(ip="my_ip", sources=[str(src)])

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.WrapperDoesNotExistError):
			cfg_with_fpga.get_wrapper("missing")

	def test_sources_empty(self, cfg_with_fpga, tmp_path):
		self._add_ip(cfg_with_fpga, tmp_path)
		cfg_with_fpga.add_wrapper_cfg(ip="my_ip", sources=[])
		with pytest.raises(error.WrapperSourcesEmptyError):
			cfg_with_fpga.validate_wrapper("my_ip")

	def test_sources_missing(self, cfg_with_fpga, tmp_path):
		self._add_ip(cfg_with_fpga, tmp_path)
		cfg_with_fpga.add_wrapper_cfg(ip="my_ip", sources=["/nonexistent/wrap.sv"])
		with pytest.raises(error.WrapperSourcesMissingError):
			cfg_with_fpga.validate_wrapper("my_ip")


# ---------------------------------------------------------------------------
# BD
# ---------------------------------------------------------------------------


class TestBd:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_bd_cfg("my_bd")
		with pytest.raises(error.BdAlreadyExistsError):
			cfg_with_fpga.add_bd_cfg("my_bd")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.BdDoesNotExistError):
			cfg_with_fpga.get_bd("missing")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


class TestCore:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		with pytest.raises(error.CoreAlreadyExistsError):
			cfg_with_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.CoreDoesNotExistError):
			cfg_with_fpga.get_core("missing")

	def test_identifier_unspecified(self, cfg_with_fpga):
		with pytest.raises(error.CoreIdentifierUnspecifiedError):
			cfg_with_fpga.add_core_cfg("my_core")

	def test_identifier_multiple(self, cfg_with_fpga, tmp_path):
		src = tmp_path / "a.v"
		src.touch()
		cfg_with_fpga.add_ip_cfg("my_ip", sources=[str(src)])
		with pytest.raises(error.CoreIdentifierMultipleError):
			cfg_with_fpga.add_core_cfg("my_core", ip="my_ip", vlnv="a:b:c:1.0")


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------


class TestDesign:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		with pytest.raises(error.DesignAlreadyExistsError):
			cfg_with_fpga.add_design_cfg("my_design", sources=[])

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.DesignDoesNotExistError):
			cfg_with_fpga.get_design("missing")

	def test_sources_missing(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=["/nonexistent/top.sv"])
		with pytest.raises(error.DesignSourcesMissingError):
			cfg_with_fpga.validate_design("my_design")


# ---------------------------------------------------------------------------
# Synth
# ---------------------------------------------------------------------------


class TestSynth:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		cfg_with_fpga.add_synth_cfg(design="my_design")
		with pytest.raises(error.SynthAlreadyExistsError):
			cfg_with_fpga.add_synth_cfg(design="my_design")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.SynthDoesNotExistError):
			cfg_with_fpga.get_synth(design_name="missing")

	def test_identifier_unspecified(self, cfg_with_fpga):
		with pytest.raises(error.SynthIdentifierUnspecifiedError):
			cfg_with_fpga._get_synth_cfg_optional()

	def test_identifier_multiple(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		cfg_with_fpga.add_bd_cfg("my_bd")
		with pytest.raises(error.SynthIdentifierMultipleError):
			cfg_with_fpga._get_synth_cfg_optional(design_name="my_design", bd_name="my_bd")

	def test_constraints_missing(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		cfg_with_fpga.add_synth_cfg(design="my_design", constraints=["/nonexistent/top.xdc"])
		with pytest.raises(error.SynthConstraintsMissingError):
			cfg_with_fpga.validate_synth(design="my_design")


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class TestSim:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_sim_cfg("my_sim", sources=[])
		with pytest.raises(error.SimAlreadyExistsError):
			cfg_with_fpga.add_sim_cfg("my_sim", sources=[])

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.SimDoesNotExistError):
			cfg_with_fpga.get_sim("missing")

	def test_invalid_backend(self, cfg_with_fpga):
		with pytest.raises(error.InvalidSimulationBackend):
			cfg_with_fpga.add_sim_cfg("my_sim", sources=[], backend="badbackend")


# ---------------------------------------------------------------------------
# UVM
# ---------------------------------------------------------------------------


class TestUvm:
	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.UvmDoesNotExistError):
			cfg_with_fpga.get_uvm("missing_test", "missing_sim")

	def test_pkg_dir_required_for_verilator(self, cfg_with_fpga):
		cfg_with_fpga.add_sim_cfg("my_sim", sources=[], backend="verilator")
		with pytest.raises(error.UvmPkgDirRequiredError):
			cfg_with_fpga.add_uvm_cfg("my_test", "my_sim")


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


class TestPlatform:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		cfg_with_fpga.add_synth_cfg(design="my_design")
		cfg_with_fpga.add_platform_cfg("my_platform", design="my_design")
		with pytest.raises(error.PlatformAlreadyExistsError):
			cfg_with_fpga.add_platform_cfg("my_platform", design="my_design")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.PlatformDoesNotExistError):
			cfg_with_fpga.get_platform("missing")

	def test_identifier_unspecified(self, cfg_with_fpga):
		with pytest.raises(error.PlatformIdentifierUnspecifiedError):
			cfg_with_fpga.add_platform_cfg("my_platform")

	def test_identifier_multiple(self, cfg_with_fpga):
		with pytest.raises(error.PlatformIdentifierMultipleError):
			cfg_with_fpga.add_platform_cfg("my_platform", bd="some_bd", design="some_design")

	def test_xsa_missing(self, cfg_with_fpga, tmp_path):
		cfg_with_fpga.add_platform_cfg("my_platform", xsa="/nonexistent/top.xsa", bitstream="/nonexistent/top.bit")
		with pytest.raises(error.PlatformXsaMissingError):
			cfg_with_fpga.validate_platform("my_platform")

	def test_bitstream_missing(self, cfg_with_fpga, tmp_path):
		xsa = tmp_path / "top.xsa"
		xsa.touch()
		cfg_with_fpga.add_platform_cfg("my_platform", xsa=str(xsa), bitstream="/nonexistent/top.bit")
		with pytest.raises(error.PlatformBitstreamMissingError):
			cfg_with_fpga.validate_platform("my_platform")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class TestApp:
	def test_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_app_cfg("my_app", platform="some_platform")
		with pytest.raises(error.AppAlreadyExistsError):
			cfg_with_fpga.add_app_cfg("my_app", platform="some_platform")

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.AppDoesNotExistError):
			cfg_with_fpga.get_app("missing")

	def test_sources_empty(self, cfg_with_fpga, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		cfg_with_fpga.add_app_cfg("my_app", platform="p", sources=[])
		app = cfg_with_fpga.get_app("my_app")
		app.elf_file = str(elf)
		with pytest.raises(error.AppSourcesEmptyError):
			cfg_with_fpga.validate_app("my_app")

	def test_sources_missing(self, cfg_with_fpga, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		cfg_with_fpga.add_app_cfg("my_app", platform="p", sources=["/nonexistent/main.c"])
		app = cfg_with_fpga.get_app("my_app")
		app.elf_file = str(elf)
		with pytest.raises(error.AppSourcesMissingError):
			cfg_with_fpga.validate_app("my_app")

	def test_elf_missing(self, cfg_with_fpga):
		cfg_with_fpga.add_app_cfg("my_app", platform="p")
		with pytest.raises(error.AppElfMissingError):
			cfg_with_fpga.validate_app("my_app", check_sources=False, check_elf=True)


# ---------------------------------------------------------------------------
# SubCore
# ---------------------------------------------------------------------------


class TestSubCore:
	def test_identifier_unspecified(self, cfg_with_fpga):
		cfg_with_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		with pytest.raises(error.SubCoreIdentifierUnspecifiedError):
			cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst")

	def test_identifier_multiple(self, cfg_with_fpga):
		cfg_with_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_with_fpga.add_bd_cfg("my_bd")
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		with pytest.raises(error.SubCoreIdentifierMultipleError):
			cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", bd="my_bd", design="my_design")

	def test_bd_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_with_fpga.add_bd_cfg("my_bd")
		cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", bd="my_bd")
		with pytest.raises(error.SubCoreBdAlreadyExistsError):
			cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", bd="my_bd")

	def test_design_already_exists(self, cfg_with_fpga):
		cfg_with_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_with_fpga.add_design_cfg("my_design", sources=[])
		cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", design="my_design")
		with pytest.raises(error.SubCoreDesignAlreadyExistsError):
			cfg_with_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", design="my_design")

	def test_list_identifier_unspecified(self, cfg_with_fpga):
		with pytest.raises(error.SubCoreListIdentifierUnspecifiedError):
			cfg_with_fpga.get_subcore_list()

	def test_list_identifier_multiple(self, cfg_with_fpga):
		with pytest.raises(error.SubCoreListIdentifierMultipleError):
			cfg_with_fpga.get_subcore_list(bd_name="my_bd", design_name="my_design")


# ---------------------------------------------------------------------------
# Formal
# ---------------------------------------------------------------------------


class TestFormal:
	def test_already_exists(self, cfg_with_fpga, tmp_path):
		src = tmp_path / "top.sv"
		src.touch()
		cfg_with_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[str(src)])
		with pytest.raises(error.FormalAlreadyExistsError):
			cfg_with_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[str(src)])

	def test_does_not_exist(self, cfg_with_fpga):
		with pytest.raises(error.FormalDoesNotExistError):
			cfg_with_fpga.get_formal("missing")

	def test_source_missing(self, cfg_with_fpga):
		cfg_with_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=["/nonexistent/top.sv"])
		with pytest.raises(error.FormalSourceMissingError):
			cfg_with_fpga.validate_formal("my_formal")

	def test_invalid_mode(self, cfg_with_fpga, tmp_path):
		src = tmp_path / "top.sv"
		src.touch()
		with pytest.raises(error.FormalInvalidModeError):
			cfg_with_fpga.add_formal_cfg("my_formal", top="top", mode="badmode", sources=[str(src)])


# ---------------------------------------------------------------------------
# _resolve_sources - SourceSpec errors
# ---------------------------------------------------------------------------


class TestResolveSourcesSpec:
	def test_missing_used_in(self, cfg_with_fpga):
		with pytest.raises(error.SourceSpecMissingKeyError) as exc_info:
			cfg_with_fpga._resolve_sources([{"files": ["a.v"]}])
		assert exc_info.value.key == "used_in"

	def test_missing_files(self, cfg_with_fpga):
		with pytest.raises(error.SourceSpecMissingKeyError) as exc_info:
			cfg_with_fpga._resolve_sources([{"used_in": ["synth"]}])
		assert exc_info.value.key == "files"

	def test_unknown_stage(self, cfg_with_fpga):
		with pytest.raises(error.SourceSpecUnknownStageError) as exc_info:
			cfg_with_fpga._resolve_sources([{"used_in": ["synth", "invalid_stage"], "files": ["a.v"]}])
		assert "invalid_stage" in exc_info.value.unknown
