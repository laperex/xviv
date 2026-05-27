from __future__ import annotations

import os

import pytest

from xviv.config.project import XvivConfig
from xviv.utils import error

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path, *, work_dir=None) -> XvivConfig:
	config_file = tmp_path / "project.toml"
	config_file.touch()
	kw = {}
	if work_dir is not None:
		kw["work_dir"] = work_dir
	else:
		kw["work_dir"] = str(tmp_path / "build")
	return XvivConfig(str(config_file), **kw)


def _touch(path) -> str:
	"""Create an empty file and return its string path."""
	path = str(path)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	open(path, "w").close()
	return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path) -> XvivConfig:
	return _make_cfg(tmp_path)


@pytest.fixture
def cfg_fpga(cfg) -> XvivConfig:
	cfg.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
	return cfg


@pytest.fixture
def cfg_vivado(cfg_fpga, tmp_path) -> XvivConfig:
	vivado = tmp_path / "vivado"
	vivado.mkdir()
	cfg_fpga.add_vivado_cfg(str(vivado))
	return cfg_fpga


@pytest.fixture
def cfg_full(cfg_vivado, tmp_path) -> XvivConfig:
	vitis = tmp_path / "vitis"
	vitis.mkdir()
	cfg_vivado.add_vitis_cfg(str(vitis))
	return cfg_vivado


# ===========================================================================
# Constructor
# ===========================================================================


class TestConstructor:
	def test_default_work_dir_is_build(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(str(config_file), work_dir=None)
		assert c.work_dir == os.path.join(c.base_dir, "build")

	def test_explicit_work_dir(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(str(config_file), work_dir=str(tmp_path / "custom_build"))
		assert c.work_dir.endswith("custom_build")

	def test_base_dir_matches_config_file_parent(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
		assert c.base_dir == str(tmp_path)

	def test_board_repo_nonexistent_is_filtered(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(
			str(config_file),
			work_dir=str(tmp_path / "build"),
			board_repo=["/nonexistent/boards"],
		)
		assert "/nonexistent/boards" not in c.board_repo_list

	def test_board_repo_existing_is_included(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		boards = tmp_path / "boards"
		boards.mkdir()
		c = XvivConfig(
			str(config_file),
			work_dir=str(tmp_path / "build"),
			board_repo=[str(boards)],
		)
		assert str(boards) in c.board_repo_list

	def test_ip_repo_nonexistent_is_filtered(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		c = XvivConfig(
			str(config_file),
			work_dir=str(tmp_path / "build"),
			ip_repo=["/nonexistent/ip"],
		)
		assert "/nonexistent/ip" not in c.ip_repo_list

	def test_ip_repo_existing_is_included(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		ip_repo = tmp_path / "ip_repo"
		ip_repo.mkdir()
		c = XvivConfig(
			str(config_file),
			work_dir=str(tmp_path / "build"),
			ip_repo=[str(ip_repo)],
		)
		assert str(ip_repo) in c.ip_repo_list

	def test_ip_repo_duplicates_are_deduplicated(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		ip_repo = tmp_path / "ip_repo"
		ip_repo.mkdir()
		c = XvivConfig(
			str(config_file),
			work_dir=str(tmp_path / "build"),
			ip_repo=[str(ip_repo), str(ip_repo)],
		)
		assert c.ip_repo_list.count(str(ip_repo)) == 1

	def test_lists_are_initially_empty(self, cfg):
		for attr in (
			"_fpga_list",
			"_ip_list",
			"_wrapper_list",
			"_bd_list",
			"_core_list",
			"_subcore_list",
			"_design_list",
			"_synth_list",
			"_sim_list",
			"_platform_list",
			"_app_list",
			"_formal_list",
			"_uvm_list",
		):
			assert getattr(cfg, attr) == []

	def test_vivado_and_vitis_initially_none(self, cfg):
		assert cfg._vivado_cfg is None
		assert cfg._vitis_cfg is None


# ===========================================================================
# Path properties
# ===========================================================================


class TestPathProperties:
	def test_synth_dir_under_work_dir(self, cfg):
		assert cfg.synth_dir == os.path.join(cfg.work_dir, "synth")

	def test_bd_dir_under_work_dir(self, cfg):
		assert cfg.bd_dir == os.path.join(cfg.work_dir, "bd")

	def test_core_dir_under_work_dir(self, cfg):
		assert cfg.core_dir == os.path.join(cfg.work_dir, "core")

	def test_formal_dir_under_work_dir(self, cfg):
		assert cfg.formal_dir == os.path.join(cfg.work_dir, "formal")

	def test_wrapper_dir_under_work_dir(self, cfg):
		assert cfg.wrapper_dir == os.path.join(cfg.work_dir, "wrapper")

	def test_scripts_dir_under_base_dir(self, cfg):
		assert cfg.scripts_dir == os.path.join(cfg.base_dir, "scripts", "xviv")


# ===========================================================================
# FPGA
# ===========================================================================


class TestFpgaPositive:
	def test_add_and_get_fpga(self, cfg):
		cfg.add_fpga_cfg("zu9", fpga_part="xczu9eg-ffvb1156-2-e")
		fpga = cfg.get_fpga("zu9")
		assert fpga.name == "zu9"
		assert fpga.fpga_part == "xczu9eg-ffvb1156-2-e"

	def test_add_fpga_with_board_part(self, cfg):
		cfg.add_fpga_cfg("zu9", board_part="xilinx.com:zcu102:part0:3.4")
		fpga = cfg.get_fpga("zu9")
		assert fpga.board_part == "xilinx.com:zcu102:part0:3.4"
		assert fpga.fpga_part is None

	def test_multiple_fpgas_default_is_first(self, cfg):
		cfg.add_fpga_cfg("fpga_a", fpga_part="xczu9eg-ffvb1156-2-e")
		cfg.add_fpga_cfg("fpga_b", fpga_part="xczu7ev-fbvb900-1-i")
		assert cfg._get_fpga_cfg_default.name == "fpga_a"

	def test_add_fpga_returns_self(self, cfg):
		result = cfg.add_fpga_cfg("zu9", fpga_part="xczu9eg-ffvb1156-2-e")
		assert result is cfg

	def test_get_fpga_none_returns_default(self, cfg):
		cfg.add_fpga_cfg("zu9", fpga_part="xczu9eg-ffvb1156-2-e")
		fpga = cfg.get_fpga(None)
		assert fpga.name == "zu9"


# ===========================================================================
# VivadoConfig / VitisConfig
# ===========================================================================


class TestVivadoVitisPositive:
	def test_add_vivado_cfg_stores_path(self, cfg_fpga, tmp_path):
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		cfg_fpga.add_vivado_cfg(str(vivado))
		assert cfg_fpga.get_vivado().path == str(vivado)

	def test_add_vivado_cfg_defaults(self, cfg_fpga, tmp_path):
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		cfg_fpga.add_vivado_cfg(str(vivado))
		v = cfg_fpga.get_vivado()
		assert v.mode == "batch"
		assert v.max_threads == 10

	def test_add_vivado_cfg_custom_mode(self, cfg_fpga, tmp_path):
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		cfg_fpga.add_vivado_cfg(str(vivado), mode="gui")
		assert cfg_fpga.get_vivado().mode == "gui"

	def test_add_vitis_cfg_stores_path(self, cfg_vivado, tmp_path):
		vitis = tmp_path / "vitis"
		vitis.mkdir()
		cfg_vivado.add_vitis_cfg(str(vitis))
		assert cfg_vivado.get_vitis().path == str(vitis)

	def test_add_vivado_initialises_catalog(self, cfg_fpga, tmp_path):
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		cfg_fpga.add_vivado_cfg(str(vivado))
		# Catalog is created; get_catalog() must not raise
		# (Catalog itself may not be queryable without Vivado installed,
		#  but the object should exist)
		assert cfg_fpga._catalog_cfg is not None

	def test_add_vivado_returns_self(self, cfg_fpga, tmp_path):
		vivado = tmp_path / "vivado"
		vivado.mkdir()
		result = cfg_fpga.add_vivado_cfg(str(vivado))
		assert result is cfg_fpga

	def test_add_vitis_returns_self(self, cfg_vivado, tmp_path):
		vitis = tmp_path / "vitis"
		vitis.mkdir()
		result = cfg_vivado.add_vitis_cfg(str(vitis))
		assert result is cfg_vivado


# ===========================================================================
# IP
# ===========================================================================


class TestIpPositive:
	def test_add_and_get_ip(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		ip = cfg_fpga.get_ip("my_ip")
		assert ip.name == "my_ip"

	def test_default_vlnv(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		ip = cfg_fpga.get_ip("my_ip")
		assert ip.vlnv == "xviv.org:xviv:my_ip:1.0"

	def test_custom_vlnv(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", vlnv="acme:lib:my_ip:2.0", sources=[src])
		ip = cfg_fpga.get_ip("my_ip")
		assert ip.vlnv == "acme:lib:my_ip:2.0"

	def test_default_top_equals_name(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		assert cfg_fpga.get_ip("my_ip").top == "my_ip"

	def test_custom_top(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", top="custom_top", sources=[src])
		assert cfg_fpga.get_ip("my_ip").top == "custom_top"

	def test_fpga_ref_stored(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		assert cfg_fpga.get_ip("my_ip").fpga_ref == "xczu9"

	def test_validate_ip_passes_with_existing_source(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		cfg_fpga.validate_ip("my_ip")  # must not raise

	def test_add_ip_returns_self(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga.add_ip_cfg("my_ip", sources=[src])
		assert result is cfg_fpga

	def test_custom_repo_added_to_ip_repo_list(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		custom_repo = tmp_path / "my_repo"
		custom_repo.mkdir()
		cfg_fpga.add_ip_cfg("my_ip", sources=[src], repo=str(custom_repo))
		assert str(custom_repo) in cfg_fpga.ip_repo_list


# ===========================================================================
# Wrapper
# ===========================================================================


class TestWrapperPositive:
	def _setup_ip(self, cfg, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg.add_ip_cfg("my_ip", sources=[src])

	def test_add_and_get_wrapper(self, cfg_fpga, tmp_path):
		self._setup_ip(cfg_fpga, tmp_path)
		wrap = _touch(tmp_path / "wrap.sv")
		cfg_fpga.add_wrapper_cfg(ip="my_ip", sources=[wrap])
		w = cfg_fpga.get_wrapper("my_ip")
		assert w.ip_name == "my_ip"

	def test_default_wrapper_top_name(self, cfg_fpga, tmp_path):
		self._setup_ip(cfg_fpga, tmp_path)
		wrap = _touch(tmp_path / "wrap.sv")
		cfg_fpga.add_wrapper_cfg(ip="my_ip", sources=[wrap])
		w = cfg_fpga.get_wrapper("my_ip")
		assert w.wrapper_top == "my_ip_wrapper"

	def test_custom_wrapper_top(self, cfg_fpga, tmp_path):
		self._setup_ip(cfg_fpga, tmp_path)
		wrap = _touch(tmp_path / "wrap.sv")
		cfg_fpga.add_wrapper_cfg(ip="my_ip", sources=[wrap], wrapper_top="custom_wrapper")
		w = cfg_fpga.get_wrapper("my_ip")
		assert w.wrapper_top == "custom_wrapper"

	def test_validate_wrapper_passes_with_existing_source(self, cfg_fpga, tmp_path):
		self._setup_ip(cfg_fpga, tmp_path)
		wrap = _touch(tmp_path / "wrap.sv")
		cfg_fpga.add_wrapper_cfg(ip="my_ip", sources=[wrap])
		cfg_fpga.validate_wrapper("my_ip")  # must not raise

	def test_ip_top_propagated_to_wrapper(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		cfg_fpga.add_ip_cfg("my_ip", top="ip_top_module", sources=[src])
		wrap = _touch(tmp_path / "wrap.sv")
		cfg_fpga.add_wrapper_cfg(ip="my_ip", sources=[wrap])
		w = cfg_fpga.get_wrapper("my_ip")
		assert w.ip_top == "ip_top_module"


# ===========================================================================
# BD
# ===========================================================================


class TestBdPositive:
	def test_add_and_get_bd(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		bd = cfg_fpga.get_bd("my_bd")
		assert bd.name == "my_bd"

	def test_bd_fpga_ref_stored(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		bd = cfg_fpga.get_bd("my_bd")
		assert bd.fpga_ref == "xczu9"

	def test_bd_default_save_file_path(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		bd = cfg_fpga.get_bd("my_bd")
		assert "my_bd.tcl" in bd.save_file

	def test_bd_default_bd_file_path(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		bd = cfg_fpga.get_bd("my_bd")
		assert bd.bd_file.endswith("my_bd.bd")

	def test_bd_default_wrapper_file_path(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		bd = cfg_fpga.get_bd("my_bd")
		assert bd.bd_wrapper_file.endswith("my_bd_wrapper.v")

	def test_add_bd_returns_self(self, cfg_fpga):
		result = cfg_fpga.add_bd_cfg("my_bd")
		assert result is cfg_fpga


# ===========================================================================
# Core
# ===========================================================================


class TestCorePositive:
	def test_add_and_get_core_by_vlnv(self, cfg_fpga):
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		core = cfg_fpga.get_core("my_core")
		assert core.name == "my_core"
		assert core.vlnv == "a:b:c:1.0"

	def test_default_xci_file_path(self, cfg_fpga):
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		core = cfg_fpga.get_core("my_core")
		assert core.xci_file.endswith("my_core.xci")

	def test_custom_xci_file_path(self, cfg_fpga, tmp_path):
		xci = str(tmp_path / "custom.xci")
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0", xci_file=xci)
		assert cfg_fpga.get_core("my_core").xci_file == xci

	def test_fpga_ref_stored(self, cfg_fpga):
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		assert cfg_fpga.get_core("my_core").fpga_ref == "xczu9"

	def test_add_core_returns_self(self, cfg_fpga):
		result = cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		assert result is cfg_fpga


# ===========================================================================
# Design
# ===========================================================================


class TestDesignPositive:
	def test_add_and_get_design(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		design = cfg_fpga.get_design("my_design")
		assert design.name == "my_design"

	def test_default_top_equals_name(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		assert cfg_fpga.get_design("my_design").top == "my_design"

	def test_custom_top(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[], top="top_module")
		assert cfg_fpga.get_design("my_design").top == "top_module"

	def test_fpga_ref_stored(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		assert cfg_fpga.get_design("my_design").fpga_ref == "xczu9"

	def test_validate_design_passes_for_existing_sources(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_design_cfg("my_design", sources=[src])
		cfg_fpga.validate_design("my_design")  # must not raise

	def test_validate_design_passes_with_no_sources(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.validate_design("my_design")  # must not raise

	def test_add_design_returns_self(self, cfg_fpga):
		result = cfg_fpga.add_design_cfg("my_design", sources=[])
		assert result is cfg_fpga


# ===========================================================================
# Synth
# ===========================================================================


class TestSynthPositive:
	def test_add_synth_for_design(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.design_name == "my_design"

	def test_add_synth_for_bd(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		cfg_fpga.add_synth_cfg(bd="my_bd")
		synth = cfg_fpga.get_synth(bd_name="my_bd")
		assert synth.bd_name == "my_bd"

	def test_add_synth_for_core(self, cfg_fpga):
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		cfg_fpga.add_synth_cfg(core="my_core")
		synth = cfg_fpga.get_synth(core_name="my_core")
		assert synth.core_name == "my_core"

	def test_design_synth_top_defaults_to_design_top(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[], top="top_mod")
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.top == "top_mod"

	def test_bd_synth_top_defaults_to_bd_wrapper(self, cfg_fpga):
		cfg_fpga.add_bd_cfg("my_bd")
		cfg_fpga.add_synth_cfg(bd="my_bd")
		synth = cfg_fpga.get_synth(bd_name="my_bd")
		assert synth.top == "my_bd_wrapper"

	def test_core_synth_mode_is_out_of_context(self, cfg_fpga):
		cfg_fpga.add_core_cfg("my_core", vlnv="a:b:c:1.0")
		cfg_fpga.add_synth_cfg(core="my_core")
		synth = cfg_fpga.get_synth(core_name="my_core")
		assert synth.synth_mode == "out_of_context"

	def test_design_synth_mode_default_is_default(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.synth_mode == "default"

	def test_design_synth_bitstream_file_is_set(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.bitstream_file is not None
		assert "my_design.bit" in synth.bitstream_file

	def test_design_synth_hw_platform_file_is_none(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.hw_platform_xsa_file is None

	def test_synth_bitstream_disabled_with_false(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design", bitstream=False)
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.bitstream_file is None

	def test_synth_custom_bitstream_path(self, cfg_fpga, tmp_path):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		custom_bit = str(tmp_path / "custom.bit")
		cfg_fpga.add_synth_cfg(design="my_design", bitstream=custom_bit)
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.bitstream_file == custom_bit

	def test_synth_dcp_file_path_set_by_default(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.synth_dcp_file is not None
		assert "synth.dcp" in synth.synth_dcp_file

	def test_validate_synth_passes_with_no_constraints(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		cfg_fpga.validate_synth(design="my_design")  # must not raise

	def test_validate_synth_passes_with_existing_constraint(self, cfg_fpga, tmp_path):
		xdc = _touch(tmp_path / "top.xdc")
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design", constraints=[xdc])
		cfg_fpga.validate_synth(design="my_design")  # must not raise

	def test_add_synth_returns_self(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		result = cfg_fpga.add_synth_cfg(design="my_design")
		assert result is cfg_fpga

	def test_fpga_ref_inherited_from_design(self, cfg_fpga):
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_synth_cfg(design="my_design")
		synth = cfg_fpga.get_synth(design_name="my_design")
		assert synth.fpga_ref == "xczu9"


# ===========================================================================
# Simulation
# ===========================================================================


class TestSimPositive:
	def test_add_and_get_sim(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[])
		sim = cfg_fpga.get_sim("my_sim")
		assert sim.name == "my_sim"

	def test_default_top_equals_name(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[])
		assert cfg_fpga.get_sim("my_sim").top == "my_sim"

	def test_custom_top(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[], top="tb_top")
		assert cfg_fpga.get_sim("my_sim").top == "tb_top"

	def test_default_backend_is_xsim(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[])
		assert cfg_fpga.get_sim("my_sim").backend == "xsim"

	def test_verilator_backend(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[], backend="verilator")
		assert cfg_fpga.get_sim("my_sim").backend == "verilator"

	def test_default_timescale(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[])
		assert cfg_fpga.get_sim("my_sim").timescale == "1ns/1ps"

	def test_custom_timescale(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[], timescale="100ps/1ps")
		assert cfg_fpga.get_sim("my_sim").timescale == "100ps/1ps"

	def test_plusargs_stored(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[], plusargs=["key=val"])
		assert "key=val" in cfg_fpga.get_sim("my_sim").plusargs

	def test_defines_stored(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[], defines=["DEBUG"])
		assert "DEBUG" in cfg_fpga.get_sim("my_sim").defines

	def test_include_dirs_stored(self, cfg_fpga, tmp_path):
		inc = str(tmp_path / "include")
		cfg_fpga.add_sim_cfg("my_sim", sources=[], include_dirs=[inc])
		assert inc in cfg_fpga.get_sim("my_sim").include_dirs

	def test_add_sim_returns_self(self, cfg_fpga):
		result = cfg_fpga.add_sim_cfg("my_sim", sources=[])
		assert result is cfg_fpga

	def test_work_dir_under_sim_subdir(self, cfg_fpga):
		cfg_fpga.add_sim_cfg("my_sim", sources=[])
		sim = cfg_fpga.get_sim("my_sim")
		assert "sim" in sim.work_dir
		assert "my_sim" in sim.work_dir


# ===========================================================================
# UVM
# ===========================================================================


class TestUvmPositive:
	def _setup_sim(self, cfg):
		cfg.add_sim_cfg(
			"my_sim",
			sources=[],
			backend="xsim",
			uvm_verbosity="UVM_HIGH",
			uvm_version="1.2",
		)

	def test_add_and_get_uvm(self, cfg_fpga):
		self._setup_sim(cfg_fpga)
		cfg_fpga.add_uvm_cfg("my_test", "my_sim")
		uvm = cfg_fpga.get_uvm("my_test", "my_sim")
		assert uvm.test == "my_test"

	def test_uvm_simulation_stored(self, cfg_fpga):
		self._setup_sim(cfg_fpga)
		cfg_fpga.add_uvm_cfg("my_test", "my_sim")
		assert cfg_fpga.get_uvm("my_test", "my_sim").simulation == "my_sim"

	def test_uvm_inherits_verbosity_from_sim(self, cfg_fpga):
		self._setup_sim(cfg_fpga)
		cfg_fpga.add_uvm_cfg("my_test", "my_sim")
		assert cfg_fpga.get_uvm("my_test", "my_sim").verbosity == "UVM_HIGH"

	def test_uvm_inherits_version_from_sim(self, cfg_fpga):
		self._setup_sim(cfg_fpga)
		cfg_fpga.add_uvm_cfg("my_test", "my_sim")
		assert cfg_fpga.get_uvm("my_test", "my_sim").version == "1.2"

	def test_uvm_verbosity_override(self, cfg_fpga):
		self._setup_sim(cfg_fpga)
		cfg_fpga.add_uvm_cfg("my_test", "my_sim", verbosity="UVM_DEBUG")
		assert cfg_fpga.get_uvm("my_test", "my_sim").verbosity == "UVM_DEBUG"


# ===========================================================================
# Platform
# ===========================================================================


class TestPlatformPositive:
	def _setup_design_synth(self, cfg):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design")

	def test_add_platform_from_design_and_get(self, cfg_fpga):
		self._setup_design_synth(cfg_fpga)
		cfg_fpga.add_platform_cfg("my_platform", design="my_design")
		p = cfg_fpga.get_platform("my_platform")
		assert p.name == "my_platform"

	def test_platform_xsa_derived_from_synth(self, cfg_fpga):
		self._setup_design_synth(cfg_fpga)
		synth = cfg_fpga.get_synth(design_name="my_design")
		cfg_fpga.add_platform_cfg("my_platform", design="my_design")
		p = cfg_fpga.get_platform("my_platform")
		assert p.xsa_file == synth.hw_platform_xsa_file

	def test_platform_bitstream_derived_from_synth(self, cfg_fpga):
		self._setup_design_synth(cfg_fpga)
		synth = cfg_fpga.get_synth(design_name="my_design")
		cfg_fpga.add_platform_cfg("my_platform", design="my_design")
		p = cfg_fpga.get_platform("my_platform")
		assert p.bitstream_file == synth.bitstream_file

	def test_platform_explicit_xsa_and_bitstream(self, cfg_fpga, tmp_path):
		xsa = _touch(tmp_path / "top.xsa")
		bit = _touch(tmp_path / "top.bit")
		cfg_fpga.add_platform_cfg("my_platform", xsa=xsa, bitstream=bit)
		p = cfg_fpga.get_platform("my_platform")
		assert p.xsa_file == xsa
		assert p.bitstream_file == bit

	def test_validate_platform_passes_with_existing_files(self, cfg_fpga, tmp_path):
		xsa = _touch(tmp_path / "top.xsa")
		bit = _touch(tmp_path / "top.bit")
		cfg_fpga.add_platform_cfg("my_platform", xsa=xsa, bitstream=bit)
		cfg_fpga.validate_platform("my_platform")  # must not raise

	def test_platform_default_cpu(self, cfg_fpga, tmp_path):
		xsa = _touch(tmp_path / "top.xsa")
		bit = _touch(tmp_path / "top.bit")
		cfg_fpga.add_platform_cfg("my_platform", xsa=xsa, bitstream=bit)
		assert cfg_fpga.get_platform("my_platform").cpu == "microblaze_0"

	def test_platform_custom_cpu(self, cfg_fpga, tmp_path):
		xsa = _touch(tmp_path / "top.xsa")
		bit = _touch(tmp_path / "top.bit")
		cfg_fpga.add_platform_cfg("my_platform", xsa=xsa, bitstream=bit, cpu="ps7_cortexa9_0")
		assert cfg_fpga.get_platform("my_platform").cpu == "ps7_cortexa9_0"

	def test_add_platform_returns_self(self, cfg_fpga, tmp_path):
		xsa = _touch(tmp_path / "top.xsa")
		bit = _touch(tmp_path / "top.bit")
		result = cfg_fpga.add_platform_cfg("my_platform", xsa=xsa, bitstream=bit)
		assert result is cfg_fpga


# ===========================================================================
# App
# ===========================================================================


class TestAppPositive:
	def test_add_and_get_app(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="p")
		app = cfg_fpga.get_app("my_app")
		assert app.name == "my_app"

	def test_default_template(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="p")
		assert cfg_fpga.get_app("my_app").template == "empty_application"

	def test_custom_template(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="p", template="hello_world")
		assert cfg_fpga.get_app("my_app").template == "hello_world"

	def test_platform_stored(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="my_platform")
		assert cfg_fpga.get_app("my_app").platform == "my_platform"

	def test_elf_file_under_app_subdir(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="p")
		app = cfg_fpga.get_app("my_app")
		assert "my_app" in app.elf_file
		assert app.elf_file.endswith("executable.elf")

	def test_validate_app_skip_both_checks(self, cfg_fpga):
		cfg_fpga.add_app_cfg("my_app", platform="p")
		# Neither check should raise when both flags are False
		cfg_fpga.validate_app("my_app", check_sources=False, check_elf=False)

	def test_validate_app_existing_elf(self, cfg_fpga, tmp_path):
		cfg_fpga.add_app_cfg("my_app", platform="p")
		app = cfg_fpga.get_app("my_app")
		_touch(app.elf_file)
		cfg_fpga.validate_app("my_app", check_sources=False, check_elf=True)

	def test_add_app_returns_self(self, cfg_fpga):
		result = cfg_fpga.add_app_cfg("my_app", platform="p")
		assert result is cfg_fpga


# ===========================================================================
# Formal
# ===========================================================================


class TestFormalPositive:
	def test_add_and_get_formal(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src])
		f = cfg_fpga.get_formal("my_formal")
		assert f.name == "my_formal"

	def test_formal_mode_prove(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="prove", sources=[src])
		assert cfg_fpga.get_formal("my_formal").mode == "prove"

	def test_formal_mode_cover(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="cover", sources=[src])
		assert cfg_fpga.get_formal("my_formal").mode == "cover"

	def test_formal_default_depth(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src])
		assert cfg_fpga.get_formal("my_formal").depth == 20

	def test_formal_custom_depth(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src], depth=50)
		assert cfg_fpga.get_formal("my_formal").depth == 50

	def test_validate_formal_passes(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src])
		cfg_fpga.validate_formal("my_formal")  # must not raise

	def test_formal_work_dir_under_formal_dir(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src])
		f = cfg_fpga.get_formal("my_formal")
		assert "formal" in f.work_dir
		assert "my_formal" in f.work_dir

	def test_formal_list(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		cfg_fpga.add_formal_cfg("f1", top="top", mode="bmc", sources=[src])
		cfg_fpga.add_formal_cfg("f2", top="top", mode="prove", sources=[src])
		names = [f.name for f in cfg_fpga.get_formal_list()]
		assert "f1" in names and "f2" in names

	def test_add_formal_returns_self(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "top.sv")
		result = cfg_fpga.add_formal_cfg("my_formal", top="top", mode="bmc", sources=[src])
		assert result is cfg_fpga


# ===========================================================================
# SubCore
# ===========================================================================


class TestSubCorePositive:
	def test_add_and_list_subcore_by_bd(self, cfg_fpga):
		cfg_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_fpga.add_bd_cfg("my_bd")
		cfg_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", bd="my_bd")
		entries = cfg_fpga.get_subcore_list(bd_name="my_bd")
		assert len(entries) == 1
		assert entries[0].inst_hier_path == "/top/inst"

	def test_add_and_list_subcore_by_design(self, cfg_fpga):
		cfg_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_fpga.add_design_cfg("my_design", sources=[])
		cfg_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", design="my_design")
		entries = cfg_fpga.get_subcore_list(design_name="my_design")
		assert len(entries) == 1
		assert entries[0].core == "core_a"

	def test_multiple_subcores_in_bd(self, cfg_fpga):
		cfg_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_fpga.add_core_cfg("core_b", vlnv="x:y:z:2.0")
		cfg_fpga.add_bd_cfg("my_bd")
		cfg_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst_a", bd="my_bd")
		cfg_fpga.add_subcore_cfg(core="core_b", inst_hier_path="/top/inst_b", bd="my_bd")
		entries = cfg_fpga.get_subcore_list(bd_name="my_bd")
		assert len(entries) == 2

	def test_subcores_are_filtered_by_bd(self, cfg_fpga):
		cfg_fpga.add_core_cfg("core_a", vlnv="a:b:c:1.0")
		cfg_fpga.add_bd_cfg("bd_x")
		cfg_fpga.add_bd_cfg("bd_y")
		cfg_fpga.add_subcore_cfg(core="core_a", inst_hier_path="/top/inst", bd="bd_x")
		entries = cfg_fpga.get_subcore_list(bd_name="bd_y")
		assert entries == []


# ===========================================================================
# _resolve_sources
# ===========================================================================


class TestResolveSources:
	def test_string_source_gets_all_default_stages(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga._resolve_sources([src])
		assert len(result) == 1
		sf = result[0]
		assert sf.used_in_synth
		assert sf.used_in_impl
		assert sf.used_in_sim

	def test_dict_source_restricts_stages(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga._resolve_sources([{"used_in": ["synth"], "files": [src]}])
		sf = result[0]
		assert sf.used_in_synth
		assert not sf.used_in_sim
		assert not sf.used_in_impl

	def test_dict_source_sim_only(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga._resolve_sources([{"used_in": ["sim"], "files": [src]}])
		sf = result[0]
		assert sf.used_in_sim
		assert not sf.used_in_synth

	def test_empty_sources_returns_empty_list(self, cfg_fpga):
		result = cfg_fpga._resolve_sources([])
		assert result == []

	def test_multiple_files_in_dict(self, cfg_fpga, tmp_path):
		src_a = _touch(tmp_path / "a.v")
		src_b = _touch(tmp_path / "b.v")
		result = cfg_fpga._resolve_sources([{"used_in": ["synth", "sim"], "files": [src_a, src_b]}])
		assert len(result) == 2

	def test_used_in_ooc_default_propagated(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga._resolve_sources([src], used_in_ooc=True)
		assert result[0].used_in_ooc

	def test_used_in_ooc_excluded_via_kwarg(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		result = cfg_fpga._resolve_sources([src], used_in_ooc=False)
		assert not result[0].used_in_ooc

	def test_source_spec_with_impl_and_synth(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.xdc")
		result = cfg_fpga._resolve_sources([{"used_in": ["synth", "impl"], "files": [src]}])
		sf = result[0]
		assert sf.used_in_synth
		assert sf.used_in_impl
		assert not sf.used_in_sim

	def test_resolve_sources_unknown_stage_contains_name(self, cfg_fpga):
		with pytest.raises(error.SourceSpecUnknownStageError) as exc_info:
			cfg_fpga._resolve_sources([{"used_in": ["synth", "invalid_stage"], "files": ["a.v"]}])
		assert "invalid_stage" in exc_info.value.unknown

	def test_resolve_sources_missing_used_in_key(self, cfg_fpga):
		with pytest.raises(error.SourceSpecMissingKeyError) as exc_info:
			cfg_fpga._resolve_sources([{"files": ["a.v"]}])
		assert exc_info.value.key == "used_in"

	def test_resolve_sources_missing_files_key(self, cfg_fpga):
		with pytest.raises(error.SourceSpecMissingKeyError) as exc_info:
			cfg_fpga._resolve_sources([{"used_in": ["synth"]}])
		assert exc_info.value.key == "files"


# ===========================================================================
# _resolve_properties
# ===========================================================================


class TestResolveProperties:
	def test_flat_dict(self, cfg_fpga):
		props = cfg_fpga._resolve_properties({"key": "value"})
		assert ("key", "value") in props

	def test_nested_dict_flattened(self, cfg_fpga):
		props = cfg_fpga._resolve_properties({"a": {"b": "c"}})
		assert ("a.b", "c") in props

	def test_deeply_nested(self, cfg_fpga):
		props = cfg_fpga._resolve_properties({"a": {"b": {"c": "d"}}})
		assert ("a.b.c", "d") in props

	def test_empty_dict_returns_empty_list(self, cfg_fpga):
		assert cfg_fpga._resolve_properties({}) == []

	def test_multiple_keys(self, cfg_fpga):
		props = cfg_fpga._resolve_properties({"x": "1", "y": "2"})
		keys = [k for k, _ in props]
		assert "x" in keys and "y" in keys


# ===========================================================================
# _resolve_fpga
# ===========================================================================


class TestResolveFpga:
	def test_resolve_none_returns_default(self, cfg_fpga):
		result = cfg_fpga._resolve_fpga(None)
		assert result == "xczu9"

	def test_resolve_explicit_name(self, cfg_fpga):
		result = cfg_fpga._resolve_fpga("xczu9")
		assert result == "xczu9"

	def test_resolve_with_default_fpga_ref(self, cfg_fpga):
		result = cfg_fpga._resolve_fpga(None, default_fpga_ref="xczu9")
		assert result == "xczu9"

	def test_resolve_nonexistent_raises(self, cfg_fpga):
		with pytest.raises(error.FpgaResolveError):
			cfg_fpga._resolve_fpga("nonexistent")

	def test_mismatch_raises_when_refs_differ(self, cfg_fpga):
		cfg_fpga.add_fpga_cfg("other_fpga", fpga_part="xczu7ev-fbvb900-1-i")
		with pytest.raises(error.FpgaRefMismatchError):
			cfg_fpga._resolve_fpga("other_fpga", default_fpga_ref="xczu9", mismatch_check="Design", mismatch_name="my_design")


# ===========================================================================
# Multiple FPGAs – explicit fpga= on add_* methods
# ===========================================================================


class TestMultipleFpgas:
	def _two_fpga_cfg(self, cfg) -> XvivConfig:
		cfg.add_fpga_cfg("fpga_a", fpga_part="xczu9eg-ffvb1156-2-e")
		cfg.add_fpga_cfg("fpga_b", fpga_part="xczu7ev-fbvb900-1-i")
		return cfg

	def test_ip_explicit_fpga(self, cfg, tmp_path):
		self._two_fpga_cfg(cfg)
		src = _touch(tmp_path / "a.v")
		cfg.add_ip_cfg("my_ip", sources=[src], fpga="fpga_b")
		assert cfg.get_ip("my_ip").fpga_ref == "fpga_b"

	def test_design_explicit_fpga(self, cfg, tmp_path):
		self._two_fpga_cfg(cfg)
		cfg.add_design_cfg("my_design", sources=[], fpga="fpga_b")
		assert cfg.get_design("my_design").fpga_ref == "fpga_b"

	def test_bd_explicit_fpga(self, cfg, tmp_path):
		self._two_fpga_cfg(cfg)
		cfg.add_bd_cfg("my_bd", fpga="fpga_b")
		assert cfg.get_bd("my_bd").fpga_ref == "fpga_b"


# ===========================================================================
# build() success path
# ===========================================================================


class TestBuildSuccess:
	def test_build_returns_self(self, cfg_full):
		# No cores with vlnv to resolve -> build should succeed
		result = cfg_full.build()
		assert result is cfg_full

	def test_build_creates_work_dir(self, cfg_full):
		cfg_full.build()
		assert os.path.isdir(cfg_full.work_dir)

	def test_build_raises_for_bad_vivado_path(self, tmp_path):
		config_file = tmp_path / "project.toml"
		config_file.touch()
		vitis = tmp_path / "vitis"
		vitis.mkdir()
		c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
		c.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
		c.add_vivado_cfg("/nonexistent/vivado")
		c.add_vitis_cfg(str(vitis))
		with pytest.raises(error.InvalidPathError):
			c.build()


# ===========================================================================
# SourceFile dataclass
# ===========================================================================


class TestSourceFile:
	def test_used_in_synth_property(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		sf = cfg_fpga._resolve_sources([src])[0]
		assert sf.used_in_synth is True

	def test_used_in_sim_false_when_excluded(self, cfg_fpga, tmp_path):
		src = _touch(tmp_path / "a.v")
		sf = cfg_fpga._resolve_sources([src], used_in_sim=False)[0]
		assert sf.used_in_sim is False

	def test_from_stages_classmethod(self):
		from xviv.config.model import SourceFile

		sf = SourceFile.from_stages("/some/file.v", {"synth", "impl"})
		assert sf.file == "/some/file.v"
		assert "synth" in sf.used_in
		assert "sim" not in sf.used_in
