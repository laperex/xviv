"""Tests for XvivConfig.add_synth_cfg - the 30+ parameter complex defaults."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig
from xviv.utils.error import SynthAlreadyExistsError


@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock())


def _cfg_with_design(tmp_path, design_name="my_design"):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	src = tmp_path / "top.sv"
	src.write_text("module top; endmodule")
	cfg.add_design_cfg(design_name, sources=[str(src)])
	return cfg


def _cfg_with_core(tmp_path, core_name="my_core"):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	cfg.add_core_cfg(core_name, vlnv="user.org:user:my_core:1.0")
	return cfg


@pytest.mark.unit
class TestSynthDefaultsByTarget:
	def test_synth_design_inherits_fpga_from_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design")
		synth = cfg.get_synth(design_name="my_design")
		assert synth.fpga == "artix"

	def test_synth_core_default_top_is_core_name(self, tmp_path):
		cfg = _cfg_with_core(tmp_path)
		cfg.add_synth_cfg(core="my_core")
		synth = cfg.get_synth(core_name="my_core")
		assert synth.top == "my_core"

	def test_synth_design_default_top_is_design_name(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, design_name="top_design")
		cfg.add_synth_cfg(design="top_design")
		synth = cfg.get_synth(design_name="top_design")
		assert synth.top == "top_design"


@pytest.mark.unit
class TestSynthCheckpointPaths:
	def test_synth_dcp_defaults_to_checkpoints_dir(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design")
		synth = cfg.get_synth(design_name="my_design")
		assert synth.synth_dcp is not None
		assert "checkpoint" in synth.synth_dcp.lower()

	def test_synth_dcp_false_gives_none(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design", synth_dcp=False)
		synth = cfg.get_synth(design_name="my_design")
		assert synth.synth_dcp is None

	def test_synth_dcp_string_overrides_path(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		custom = "/custom/path/synth.dcp"
		cfg.add_synth_cfg(design="my_design", synth_dcp=custom)
		synth = cfg.get_synth(design_name="my_design")
		assert synth.synth_dcp == custom

	def test_place_dcp_defaults_to_checkpoints_dir(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design")
		synth = cfg.get_synth(design_name="my_design")
		assert synth.place_dcp is not None
		assert "checkpoint" in synth.place_dcp.lower()

	def test_place_dcp_false_gives_none(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design", place_dcp=False)
		synth = cfg.get_synth(design_name="my_design")
		assert synth.place_dcp is None


@pytest.mark.unit
class TestSynthModeOoc:
	def test_ooc_mode_forces_bitstream_to_none(self, tmp_path):
		cfg = _cfg_with_core(tmp_path)
		cfg.add_synth_cfg(core="my_core", synth_mode="out_of_context")
		synth = cfg.get_synth(core_name="my_core")
		assert synth.bitstream is None

	def test_ooc_mode_forces_hw_platform_to_none(self, tmp_path):
		cfg = _cfg_with_core(tmp_path)
		cfg.add_synth_cfg(core="my_core", synth_mode="out_of_context")
		synth = cfg.get_synth(core_name="my_core")
		assert synth.hw_platform is None


@pytest.mark.unit
class TestSynthDuplicateRaises:
	def test_duplicate_design_synth_raises(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_synth_cfg(design="my_design")
		with pytest.raises(SynthAlreadyExistsError):
			cfg.add_synth_cfg(design="my_design")

	def test_duplicate_core_synth_raises(self, tmp_path):
		cfg = _cfg_with_core(tmp_path)
		cfg.add_synth_cfg(core="my_core")
		with pytest.raises(SynthAlreadyExistsError):
			cfg.add_synth_cfg(core="my_core")


@pytest.mark.unit
class TestSynthIdentifierRules:
	def test_zero_identifiers_raises(self, tmp_path):
		pf = tmp_path / "project.toml"
		pf.write_text("")
		cfg = XvivConfig(str(pf))
		cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
		cfg.add_vivado_cfg(path=None)
		with pytest.raises(Exception):
			cfg.add_synth_cfg()  # no design/core/bd

	def test_two_identifiers_raises(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		cfg.add_core_cfg("my_core", vlnv="user.org:user:my_core:1.0")
		with pytest.raises(Exception):
			cfg.add_synth_cfg(design="my_design", core="my_core")
