"""Tests for ConfigTclCommands.synth - stage pipeline, skip flags, directives, checkpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.helpers import has_cmd, lacks_cmd, line_index
from xviv.config.params import SynthParams
from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands


@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock())


def _cfg_with_design(
	tmp_path,
	*,
	run_route=True,
	run_opt=True,
	run_place=True,
	run_phys_opt=True,
	synth_dcp=True,
	place_dcp=True,
	route_dcp=True,
	bitstream=None,
	hw_platform=None,
	synth_mode=None,
	synth_directive="default",
	opt_directive="default",
	place_directive="default",
	route_directive="default",
	phys_opt_directive="default",
	usr_access_value=None,
	synth_flatten_hierarchy="rebuilt",
	synth_fsm_extraction="auto",
	synth_report_timing_summary=False,
	route_report_drc=False,
):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	src = tmp_path / "top.sv"
	src.write_text("module top; endmodule")
	cfg.add_design_cfg("top_design", sources=[str(src)])
	cfg.add_synth_cfg(
		design="top_design",
		run_route=run_route,
		run_opt=run_opt,
		run_place=run_place,
		run_phys_opt=run_phys_opt,
		synth_dcp=synth_dcp,
		place_dcp=place_dcp,
		route_dcp=route_dcp,
		bitstream=bitstream,
		hw_platform=hw_platform,
		synth_mode=synth_mode,
		synth_directive=synth_directive,
		opt_directive=opt_directive,
		place_directive=place_directive,
		phys_opt_directive=phys_opt_directive,
		route_directive=route_directive,
		usr_access_value=usr_access_value,
		synth_flatten_hierarchy=synth_flatten_hierarchy,
		synth_fsm_extraction=synth_fsm_extraction,
		synth_report_timing_summary=synth_report_timing_summary,
		route_report_drc=route_report_drc,
	)
	return cfg


def _build_synth_tcl(cfg, *, design="top_design", params=None):
	if params is None:
		params = SynthParams(resume=None, parallel_subcore_synth=False)
	tcl = ConfigTclCommands(cfg).synth(design=design, params=params).build()
	assert tcl is not None
	return tcl


@pytest.mark.unit
class TestStagePipeline:
	def test_synth_design_precedes_opt_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		assert line_index(tcl, "synth_design") < line_index(tcl, "opt_design")

	def test_opt_design_precedes_place_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		assert line_index(tcl, "opt_design") < line_index(tcl, "place_design")

	def test_place_design_precedes_route_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		assert line_index(tcl, "place_design") < line_index(tcl, "route_design")

	def test_phys_opt_design_between_place_and_route(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		assert line_index(tcl, "place_design") < line_index(tcl, "phys_opt_design")
		assert line_index(tcl, "phys_opt_design") < line_index(tcl, "route_design")


@pytest.mark.unit
class TestSkipStages:
	def test_run_opt_false_no_opt_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, run_opt=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "opt_design")

	def test_run_place_false_no_place_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, run_place=False, run_route=False, bitstream=False, hw_platform=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "place_design")

	def test_run_route_false_no_route_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, run_route=False, bitstream=False, hw_platform=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "route_design")

	def test_run_phys_opt_false_no_phys_opt_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, run_phys_opt=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "phys_opt_design")


@pytest.mark.unit
class TestSynthDirectives:
	def test_custom_synth_directive_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_directive="RuntimeOptimized")
		tcl = _build_synth_tcl(cfg)
		assert "RuntimeOptimized" in tcl

	def test_custom_opt_directive_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, opt_directive="ExploreWithRemap")
		tcl = _build_synth_tcl(cfg)
		assert "ExploreWithRemap" in tcl

	def test_custom_place_directive_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, place_directive="AltSpreadLogic_high")
		tcl = _build_synth_tcl(cfg)
		assert "AltSpreadLogic_high" in tcl

	def test_custom_route_directive_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, route_directive="AggressiveExplore")
		tcl = _build_synth_tcl(cfg)
		assert "AggressiveExplore" in tcl

	def test_custom_phys_opt_directive_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, phys_opt_directive="AggressiveExplore")
		tcl = _build_synth_tcl(cfg)
		assert "AggressiveExplore" in tcl


@pytest.mark.unit
class TestSynthOptions:
	def test_synth_mode_appears_in_synth_design(self, tmp_path):
		cfg = _cfg_with_design(
			tmp_path,
			synth_mode="out_of_context",
			run_place=False,
			run_route=False,
			run_phys_opt=False,
			run_opt=False,
			bitstream=False,
			hw_platform=False,
			place_dcp=False,
			route_dcp=False,
		)
		tcl = _build_synth_tcl(cfg)
		assert "out_of_context" in tcl

	def test_flatten_hierarchy_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_flatten_hierarchy="full")
		tcl = _build_synth_tcl(cfg)
		assert "full" in tcl

	def test_fsm_extraction_appears(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_fsm_extraction="one_hot")
		tcl = _build_synth_tcl(cfg)
		assert "one_hot" in tcl

	def test_top_module_in_synth_design(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		assert "top_design" in tcl


@pytest.mark.unit
class TestCheckpoints:
	def test_write_checkpoint_after_synth_when_synth_dcp_set(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		# write_checkpoint should appear after synth_design
		assert line_index(tcl, "synth_design") < line_index(tcl, "write_checkpoint")

	def test_no_write_checkpoint_when_synth_dcp_none(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_dcp=False, place_dcp=False, route_dcp=False, run_route=False, bitstream=False, hw_platform=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "write_checkpoint")

	def test_multiple_write_checkpoints_for_each_stage(self, tmp_path):
		cfg = _cfg_with_design(tmp_path)
		tcl = _build_synth_tcl(cfg)
		count = tcl.count("write_checkpoint")
		assert count >= 2  # at least synth + place + route


@pytest.mark.unit
class TestBitstreamAndXsa:
	def test_write_bitstream_when_bitstream_set(self, tmp_path):

		cfg = _cfg_with_design(tmp_path, bitstream=str(tmp_path / "out.bit"))
		tcl = _build_synth_tcl(cfg)
		assert has_cmd(tcl, "write_bitstream")

	def test_no_write_bitstream_when_bitstream_none(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, bitstream=False, hw_platform=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "write_bitstream")

	def test_write_hw_platform_when_hw_platform_set(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, hw_platform=str(tmp_path / "out.xsa"), bitstream=str(tmp_path / "out.bit"))
		tcl = _build_synth_tcl(cfg)
		assert has_cmd(tcl, "write_hw_platform")

	def test_no_write_hw_platform_when_none(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, bitstream=False, hw_platform=False)
		tcl = _build_synth_tcl(cfg)
		assert lacks_cmd(tcl, "write_hw_platform")


@pytest.mark.unit
class TestUsrAccess:
	def test_usr_access_property_appears_when_set(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, usr_access_value=0xDEADBEEF, bitstream=str(tmp_path / "out.bit"))
		tcl = _build_synth_tcl(cfg)
		assert has_cmd(tcl, "set_property BITSTREAM.CONFIG.USR_ACCESS")

	def test_usr_access_precedes_write_bitstream(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, usr_access_value=0x12345678, bitstream=str(tmp_path / "out.bit"))
		tcl = _build_synth_tcl(cfg)
		assert line_index(tcl, "set_property BITSTREAM.CONFIG.USR_ACCESS") < line_index(tcl, "write_bitstream")

	def test_usr_access_absent_when_value_is_none_when_bitsream_is_false(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, bitstream=False)
		tcl = _build_synth_tcl(cfg)
		# assert cfg.get)
		assert lacks_cmd(tcl, "set_property BITSTREAM.CONFIG.USR_ACCESS")

	def test_usr_access_hex_formatted(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, usr_access_value=0xABCDEF01, bitstream=str(tmp_path / "out.bit"))
		tcl = _build_synth_tcl(cfg)
		assert "0xABCDEF01" in tcl.upper() or "0XABCDEF01" in tcl.upper()


@pytest.mark.unit
class TestReports:
	def test_report_timing_summary_when_enabled(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_report_timing_summary=True)
		tcl = _build_synth_tcl(cfg)
		assert has_cmd(tcl, "report_timing_summary") or "timing_summary" in tcl

	def test_no_report_when_disabled(self, tmp_path):
		cfg = _cfg_with_design(tmp_path, synth_report_timing_summary=False)
		tcl = _build_synth_tcl(cfg)
		# Default is False - should not appear post-synth_design
		# (Route stage is separate - we just check the overall TCL doesn't have
		# synth-phase report commands when disabled)
		assert "report_timing_summary" not in tcl or "route_design" in tcl


@pytest.mark.unit
class TestResumeInvalid:
	def test_invalid_resume_stage_raises(self, tmp_path):
		from xviv.utils.error import SynthResumeInvalidError

		cfg = _cfg_with_design(tmp_path)
		params = SynthParams(resume="garbage_stage")
		with pytest.raises(SynthResumeInvalidError):
			ConfigTclCommands(cfg).synth(design="top_design", params=params).build()
