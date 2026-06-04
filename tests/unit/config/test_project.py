"""Tests for xviv.config.project.XvivConfig — constructor, add/get methods."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig
from xviv.utils.error import (
	FpgaAlreadyExistsError,
	FpgaPartUnspecifiedError,
	NoFpgaError,
	SimAlreadyExistsError,
	UninitializedVivadoError,
	VivadoAlreadySpecifiedError,
)


# Autouse fixture to avoid pyslang import in this test module
@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr(
		"xviv.generator.wrapper.SystemVerilogWrapper",
		MagicMock(),
	)


def _cfg(tmp_path, **kwargs):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	return XvivConfig(str(pf), **kwargs)


@pytest.mark.unit
class TestConstructor:
	def test_work_dir_defaults_under_base_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.work_dir == os.path.join(cfg.base_dir, "build")

	def test_explicit_work_dir(self, tmp_path):
		wd = str(tmp_path / "my_build")
		cfg = _cfg(tmp_path, work_dir=wd)
		assert cfg.work_dir == wd

	def test_log_file_defaults_under_work_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.log_file.startswith(cfg.work_dir)
		assert cfg.log_file.endswith(".log")

	def test_board_repo_nonexistent_filtered(self, tmp_path):
		cfg = _cfg(tmp_path, board_repo=["/nonexistent/path/abc"])
		assert len(cfg.board_repo_list) == 0

	def test_ip_repo_existing_included(self, tmp_path):
		repo = tmp_path / "my_ips"
		repo.mkdir()
		cfg = _cfg(tmp_path, ip_repo=[str(repo)])
		assert str(repo) in cfg.ip_repo_list

	def test_ip_repo_deduplicated(self, tmp_path):
		repo = tmp_path / "my_ips"
		repo.mkdir()
		cfg = _cfg(tmp_path, ip_repo=[str(repo), str(repo)])
		# no duplicates for the user-supplied path
		assert cfg.ip_repo_list.count(str(repo)) == 1

	def test_dry_run_starts_false(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.dry_run is False

	def test_check_starts_false(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.check is False

	def test_fpga_list_starts_empty(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg._fpga_list == []

	def test_base_dir_is_directory_of_project_file(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.base_dir == str(tmp_path)


@pytest.mark.unit
class TestPathProperties:
	def test_synth_dir_under_work_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.synth_dir.startswith(cfg.work_dir)

	def test_core_dir_under_work_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.core_dir.startswith(cfg.work_dir)

	def test_bd_dir_under_work_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		assert cfg.bd_dir.startswith(cfg.work_dir)

	def test_all_path_properties_are_absolute(self, tmp_path):
		cfg = _cfg(tmp_path)
		for attr in ["synth_dir", "core_dir", "bd_dir", "formal_dir", "wrapper_dir"]:
			val = getattr(cfg, attr)
			assert os.path.isabs(val), f"{attr} is not absolute: {val}"


@pytest.mark.unit
class TestAddFpga:
	def test_add_by_fpga_part(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		assert len(cfg._fpga_list) == 1

	def test_add_by_board_part(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("basys3", board_part="digilentinc.com:basys3:part0:1.1")
		assert len(cfg._fpga_list) == 1

	def test_first_fpga_is_default(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("first", fpga_part="xc7a100tcsg324-1")
		cfg.add_fpga_cfg("second", fpga_part="xc7z020clg400-1")
		default = cfg.get_fpga(None)
		assert default.name == "first"

	def test_get_fpga_by_name(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_fpga_cfg("zynq", fpga_part="xc7z020clg400-1")
		assert cfg.get_fpga("zynq").name == "zynq"

	def test_duplicate_fpga_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		with pytest.raises(FpgaAlreadyExistsError):
			cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")

	def test_missing_part_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises(FpgaPartUnspecifiedError):
			cfg.add_fpga_cfg("artix")

	def test_get_fpga_none_on_empty_list_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises((NoFpgaError, Exception)):
			cfg.get_fpga(None)  # empty _fpga_list → _get_fpga_cfg_default → NoFpgaError


@pytest.mark.unit
class TestAddVivado:
	def test_add_vivado_stores_mode(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=None, mode="batch")
		assert cfg._vivado_cfg.mode == "batch"

	def test_add_vivado_default_max_threads(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=None)
		assert cfg._vivado_cfg.max_threads == 10

	def test_add_vivado_none_path_leaves_binary_names_bare(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=None)
		assert cfg._vivado_cfg.vivado_bin == "vivado"
		assert cfg._vivado_cfg.xvlog_bin == "xvlog"

	def test_add_vivado_with_path_prefixes_bins(self, tmp_path):
		viv_path = str(tmp_path / "vivado_dir")
		os.makedirs(viv_path)
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=viv_path)
		assert cfg._vivado_cfg.vivado_bin.startswith(viv_path)

	def test_get_vivado_raises_before_add(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises(UninitializedVivadoError):
			cfg.get_vivado()

	def test_second_add_vivado_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=None)
		with pytest.raises(VivadoAlreadySpecifiedError):
			cfg.add_vivado_cfg(path=None)

	def test_add_vivado_initialises_catalog(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_vivado_cfg(path=None)
		assert cfg._catalog_cfg is not None


@pytest.mark.unit
class TestAddSim:
	def test_add_sim_default_backend_xsim(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_vivado_cfg(path=None)
		cfg.add_sim_cfg("my_sim", top="top", sources=[])
		sim = cfg.get_sim("my_sim")
		assert sim.backend == "xsim"

	def test_add_sim_custom_backend(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_vivado_cfg(path=None)
		cfg.add_sim_cfg("my_sim", top="top", backend="verilator", sources=[])
		sim = cfg.get_sim("my_sim")
		assert sim.backend == "verilator"

	def test_add_sim_invalid_backend_raises(self, tmp_path):
		from xviv.utils.error import InvalidSimulationBackend

		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_vivado_cfg(path=None)
		with pytest.raises(InvalidSimulationBackend):
			cfg.add_sim_cfg("my_sim", top="top", backend="ngspice", sources=[])

	def test_add_sim_duplicate_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_vivado_cfg(path=None)
		cfg.add_sim_cfg("my_sim", top="top", sources=[])
		with pytest.raises(SimAlreadyExistsError):
			cfg.add_sim_cfg("my_sim", top="top", sources=[])
