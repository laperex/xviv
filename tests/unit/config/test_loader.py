"""Tests for xviv.config.loader — load_config, resolve_config."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from xviv.config.loader import load_config, resolve_config
from xviv.utils.error import ProjectConfigTomlFileMissingError, ProjectConfigUnknownKeyError

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _load(toml_path: str):
	"""Load config with mocked Vivado/Vitis path finders."""
	with patch("xviv.config.loader.find_vivado_dir_path", return_value=None), patch("xviv.config.loader.find_vitis_dir_path", return_value=None):
		return load_config(toml_path)


@pytest.mark.unit
class TestMinimalLoad:
	def test_minimal_toml_loads_without_error(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert len(cfg._fpga_list) == 1

	def test_all_lists_empty_except_fpga(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert cfg._design_list == []
		assert cfg._core_list == []
		assert cfg._ip_list == []
		assert cfg._synth_list == []
		assert cfg._sim_list == []

	def test_dry_run_defaults_false(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert cfg.dry_run is False

	def test_check_defaults_false(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert cfg.check is False


@pytest.mark.unit
class TestProjectDefaults:
	def test_work_dir_defaults_under_base_dir(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert cfg.work_dir == os.path.join(str(tmp_path), "build")

	def test_log_file_defaults_under_work_dir(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text('[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		cfg = _load(str(pf))
		assert cfg.log_file.startswith(cfg.work_dir)


@pytest.mark.unit
class TestUnknownKeys:
	def test_unknown_top_level_key_raises(self, tmp_path):
		pf = tmp_path / "project.toml"
		# unknown_section_xyz must be a top-level scalar key (not inside [[fpga]])
		pf.write_text('[unknown_section_xyz]\nfoo = 1\n\n[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n')
		with pytest.raises(ProjectConfigUnknownKeyError) as exc_info:
			_load(str(pf))
		assert "unknown_section_xyz" in str(exc_info.value)


@pytest.mark.unit
class TestMissingFile:
	def test_missing_project_toml_raises(self, tmp_path):
		with pytest.raises(ProjectConfigTomlFileMissingError):
			resolve_config(str(tmp_path / "nonexistent.toml"))

	def test_empty_string_raises(self, tmp_path):
		orig_dir = os.getcwd()
		os.chdir(tmp_path)
		try:
			with pytest.raises(ProjectConfigTomlFileMissingError):
				resolve_config()
		finally:
			os.chdir(orig_dir)


@pytest.mark.unit
class TestLoadOrder:
	def test_design_loads_correctly(self, tmp_path):
		"""design section loads in order regardless of position."""
		pf = tmp_path / "project.toml"
		pf.write_text(
			'[[fpga]]\nname = "a"\nfpga_part = "xc7a100tcsg324-1"\n'
			'[[design]]\nname = "d1"\nsources = []\n'
			'[[synth]]\ndesign = "d1"\nrun_route = false\nbitstream = false\nhw_platform = false\n'
		)
		cfg = _load(str(pf))
		assert cfg.get_design("d1") is not None
		assert cfg.get_synth(design_name="d1") is not None

	def test_core_and_synth_order_independent(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text(
			'[[fpga]]\nname = "a"\nfpga_part = "xc7a100tcsg324-1"\n'
			'[[synth]]\ncore = "c1"\nrun_place = false\nrun_route = false\n'
			"run_phys_opt = false\nrun_opt = false\nbitstream = false\nhw_platform = false\n"
			'[[core]]\nname = "c1"\nvlnv = "user.org:user:c1:1.0"\n'
		)
		cfg = _load(str(pf))
		assert cfg.get_core("c1") is not None
		assert cfg.get_synth(core_name="c1") is not None


@pytest.mark.unit
class TestInvalidValues:
	def test_invalid_simulation_backend_raises(self, tmp_path):
		from xviv.utils.error import InvalidSimulationBackend

		pf = tmp_path / "project.toml"
		pf.write_text(
			'[[fpga]]\nname = "a"\nfpga_part = "xc7a100tcsg324-1"\n[[simulation]]\nname = "tb"\ntop = "tb"\nbackend = "ngspice"\nsources = []\n'
		)
		with pytest.raises(InvalidSimulationBackend):
			_load(str(pf))
