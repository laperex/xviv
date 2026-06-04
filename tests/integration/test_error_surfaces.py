"""Integration: malformed TOML → typed error raised at load time."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from xviv.utils.error import (
	FpgaAlreadyExistsError,
	InvalidSimulationBackend,
	ProjectConfigUnknownKeyError,
	SynthAlreadyExistsError,
)


def _load(content: str, tmp_path):
	from xviv.config.loader import load_config

	pf = tmp_path / "project.toml"
	pf.write_text(content)
	with (
		patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
		patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		patch("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock()),
	):
		return load_config(str(pf))


@pytest.mark.integration
class TestMissingRequiredKeys:
	def test_fpga_missing_both_part_and_board_part_raises(self, tmp_path):
		from xviv.utils.error import FpgaPartUnspecifiedError

		with pytest.raises(FpgaPartUnspecifiedError):
			_load('[[fpga]]\nname = "artix"\n', tmp_path)


@pytest.mark.integration
class TestReferenceMissing:
	def test_synth_referencing_nonexistent_design_raises(self, tmp_path):
		content = (
			'[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n'
			'[[synth]]\ndesign = "ghost_design"\nrun_route = false\nbitstream = false\nhw_platform = false\n'
		)
		with pytest.raises(Exception):
			_load(content, tmp_path)


@pytest.mark.integration
class TestInvalidValues:
	def test_invalid_simulation_backend_raises(self, tmp_path):
		content = (
			'[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n'
			'[[simulation]]\nname = "tb"\ntop = "tb"\nbackend = "badbackend"\nsources = []\n'
		)
		with pytest.raises(InvalidSimulationBackend):
			_load(content, tmp_path)

	def test_unknown_top_level_key_raises(self, tmp_path):
		content = '[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n[totally_unknown_section]\nfoo = 1\n'
		with pytest.raises(ProjectConfigUnknownKeyError):
			_load(content, tmp_path)

	def test_duplicate_fpga_raises(self, tmp_path):
		content = '[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n[[fpga]]\nname = "artix"\nfpga_part = "xc7a50tcsg324-1"\n'
		with pytest.raises(FpgaAlreadyExistsError):
			_load(content, tmp_path)

	def test_duplicate_synth_raises(self, tmp_path):
		content = (
			'[[fpga]]\nname = "artix"\nfpga_part = "xc7a100tcsg324-1"\n'
			'[[core]]\nname = "c1"\nvlnv = "user.org:user:c1:1.0"\n'
			'[[synth]]\ncore = "c1"\nrun_place = false\nrun_route = false\nrun_phys_opt = false\n'
			"run_opt = false\nbitstream = false\nhw_platform = false\n"
			'[[synth]]\ncore = "c1"\nrun_place = false\nrun_route = false\nrun_phys_opt = false\n'
			"run_opt = false\nbitstream = false\nhw_platform = false\n"
		)
		with pytest.raises(SynthAlreadyExistsError):
			_load(content, tmp_path)
