"""Integration: each fixture TOML loads without error - regression guard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(toml_path: str):
	from xviv.config.loader import load_config

	with (
		patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
		patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		patch("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock()),
	):
		return load_config(toml_path)


@pytest.mark.integration
class TestFixtureTomlsLoad:
	def test_minimal_toml(self):
		cfg = _load(str(FIXTURES / "minimal.toml"))
		assert len(cfg._fpga_list) >= 1

	def test_design_synth_toml(self):
		cfg = _load(str(FIXTURES / "design_synth.toml"))
		assert cfg.get_design("top_design") is not None

	def test_custom_ip_core_toml(self):
		cfg = _load(str(FIXTURES / "custom_ip_core.toml"))
		assert cfg.get_core("my_core") is not None

	def test_simulation_xsim_toml(self):
		cfg = _load(str(FIXTURES / "simulation_xsim.toml"))
		assert cfg.get_sim("tb_default") is not None

	def test_formal_all_modes_toml(self):
		cfg = _load(str(FIXTURES / "formal_all_modes.toml"))
		assert len(cfg._formal_list) == 3

	def test_multi_fpga_toml(self):
		cfg = _load(str(FIXTURES / "multi_fpga.toml"))
		assert len(cfg._fpga_list) == 2
		assert cfg.get_fpga("artix") is not None
		assert cfg.get_fpga("zynq") is not None
