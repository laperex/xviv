"""
Honest audit of xviv — what the original test suite does NOT cover,
and tests that actually expose real bugs or dangerous gaps.

Every test here either:
  (A) Catches a confirmed bug in the code, or
  (B) Tests the TCL generator output (the real deliverable — actual Vivado commands), or
  (C) Guards a dangerous silent-failure case the config layer ignores.

The original test_comprehensive.py tested the config layer (data model, path
generation, error routing). Those tests pass because they match what the code
*does*. These tests ask whether what the code does is *correct*.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from xviv.config.project import XvivConfig
from xviv.functions.simulation import _build_xsim_testplusargs
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils import error

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cfg(tmp_path, *, vivado=True) -> XvivConfig:
	f = tmp_path / "project.toml"
	f.touch()
	cfg = XvivConfig(str(f), work_dir=str(tmp_path / "build"))
	cfg.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
	if vivado:
		cfg.add_vivado_cfg(path=None)
	return cfg


def _touch(p) -> str:
	Path(p).parent.mkdir(parents=True, exist_ok=True)
	Path(p).touch()
	return str(p)


def _tcl(cfg, **kwargs) -> str:
	return ConfigTclCommands(cfg).synth(**kwargs).build()


# ===========================================================================
# CONFIRMED BUG — UnboundLocalError in _build_xsim_testplusargs
# ===========================================================================


class TestUnboundLocalBug:
	"""
	_build_xsim_testplusargs initialises `args` inside an `if uvm_name:` block.
	When uvm_name is falsy the next line `args += [...]` raises UnboundLocalError.

	This is a real crash on every xsim run that has no UVM test.

	Proof: run `xviv simulate --sim tb` without a --uvm flag.
	"""

	def test_no_uvm_with_no_plusargs_crashes(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=[])
		with pytest.raises(UnboundLocalError):
			_build_xsim_testplusargs(cfg, "tb", None)

	def test_no_uvm_with_plusargs_crashes(self, tmp_path):
		"""Even the simplest simulation with a +arg flag crashes."""
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=[], plusargs=["+verbose"])
		with pytest.raises(UnboundLocalError):
			_build_xsim_testplusargs(cfg, "tb", None)

	def test_with_uvm_still_works(self, tmp_path):
		"""The bug does NOT manifest when uvm_name is provided — UVM path is fine."""
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=[], plusargs=["+extra"])
		cfg.add_uvm_cfg(test="my_test", simulation="tb")
		result = _build_xsim_testplusargs(cfg, "tb", "my_test")
		assert "UVM_TESTNAME=my_test" in result
		assert "extra" in result

	def test_correct_fix_would_initialise_args_before_if(self, tmp_path):
		"""
		Demonstrates what the correct behaviour SHOULD be:
		plusargs are stripped of leading '+' and returned even without UVM.

		This test would pass after the bug is fixed.
		"""
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=[], plusargs=["+verbose", "+seed=42"])

		# Replicate the FIXED logic inline:
		sim_cfg = cfg.get_sim("tb")
		args: list[str] = []  # <- the missing initialisation
		# uvm_name is None, so the if block is skipped
		args += [a.lstrip("+") for a in sim_cfg.plusargs]
		assert args == ["verbose", "seed=42"]

		# But the real function still crashes:
		with pytest.raises(UnboundLocalError):
			_build_xsim_testplusargs(cfg, "tb", None)


# ===========================================================================
# SILENT FAILURE — validate_sim does not validate sources
# ===========================================================================


class TestValidateSimIsStub:
	"""
	validate_sim fetches the config and immediately returns.
	It does NOT check whether sources exist on disk.
	An invalid sim that would crash xvlog passes validation.
	"""

	def test_validate_sim_passes_with_nonexistent_sources(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=["/absolute/does/not/exist/tb.sv"])
		# This should raise, but it doesn't — it's a stub
		cfg.validate_sim("tb")  # silently passes — BUG

	def test_validate_sim_passes_with_empty_source_list(self, tmp_path):
		"""Zero sources means nothing to compile — xsim will fail later."""
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("tb", sources=[])
		cfg.validate_sim("tb")  # still silently passes

	def test_contrast_validate_design_does_check_sources(self, tmp_path):
		"""validate_design DOES check — shows validate_sim is inconsistently incomplete."""
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=["/ghost.sv"])
		with pytest.raises(error.DesignSourcesMissingError):
			cfg.validate_design("top")


# ===========================================================================
# SILENT FAILURE — empty-string entity names are accepted
# ===========================================================================


class TestEmptyNameGuards:
	"""
	The source has 7 '# TODO: throw error for invalid name' comments that
	were never implemented. Empty strings are valid dict keys so everything
	appears to work until a TCL script is generated with a blank module name.
	"""

	def test_empty_fpga_name_accepted(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_fpga_cfg("", fpga_part="xc7a35t-1cpg236c")
		# Should raise, but doesn't
		assert cfg.get_fpga("").fpga_part == "xc7a35t-1cpg236c"

	def test_empty_design_name_accepted(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_design_cfg("", sources=[])
		assert cfg.get_design("").name == ""

	def test_empty_sim_name_accepted(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_sim_cfg("", sources=[])
		assert cfg.get_sim("").name == ""

	def test_empty_ip_name_accepted(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_ip_cfg("", sources=[])
		assert cfg.get_ip("").name == ""

	def test_empty_name_reaches_tcl_synth_design(self, tmp_path):
		"""
		Empty design name creates an orphan: add_design_cfg("") succeeds,
		but add_synth_cfg(design="") raises SynthIdentifierUnspecifiedError
		because "" is falsy. You end up with a design that can never be synthesised.

		This is a consequence of both TODOs never being implemented:
		- add_design_cfg does NOT reject empty names
		- _get_synth_cfg_optional uses `if i` to filter, which drops ""
		"""
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("", sources=[])  # silently accepted
		assert cfg.get_design("").name == ""  # design exists
		# But you cannot synth it — "" is falsy so it looks like no identifier
		with pytest.raises(error.SynthIdentifierUnspecifiedError):
			cfg.add_synth_cfg(design="", run_place=False, run_route=False, bitstream=False)


# ===========================================================================
# CONFIG-LAYER GAP — bitstream=True with run_route=False is not caught early
# ===========================================================================


class TestConfigLayerValidationGap:
	"""
	The config layer happily stores bitstream=True and run_route=False together.
	The error is only caught later in ConfigTclCommands.synth().
	This means validate_synth() gives a false "clean" signal.
	"""

	def test_validate_synth_passes_for_invalid_bitstream_no_route(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_route=False, bitstream=True)
		# validate_synth should catch this but it doesn't
		cfg.validate_synth(design="top")  # silently passes

	def test_tcl_layer_does_catch_it(self, tmp_path):
		"""The error IS caught — but only at TCL generation time, not validation time."""
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_route=False, bitstream=True)
		with pytest.raises(error.SynthBitstreamRequiresRouteError):
			_tcl(cfg, design="top")

	def test_validate_synth_passes_for_xsa_no_route(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_bd_cfg("system")
		cfg.add_synth_cfg(bd="system", run_route=False, hw_platform=True)
		cfg.validate_synth(bd="system")  # silently passes too

	def test_tcl_layer_catches_xsa_no_route(self, tmp_path):
		"""
		BD synth defaults bitstream=True, so SynthBitstreamRequiresRouteError fires
		before SynthXsaRequiresRouteError. To isolate the XSA check, disable bitstream.
		"""
		cfg = _cfg(tmp_path)
		cfg.add_bd_cfg("system")
		cfg.add_synth_cfg(bd="system", run_route=False, hw_platform=True, bitstream=False)
		with pytest.raises(error.SynthXsaRequiresRouteError):
			_tcl(cfg, bd="system")


# ===========================================================================
# SILENT AMBIGUITY — get_uvm without sim_name silently returns first match
# ===========================================================================


class TestUvmAmbiguousLookup:
	"""
	get_uvm(test_name) without a sim_name returns the first UVM config that
	matches the test name, regardless of which simulation it belongs to.
	When the same test name is used in two simulations, the wrong one may
	be returned — silently.
	"""

	def test_same_test_name_two_sims_returns_first_silently(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_sim_cfg("tb_a", sources=[])
		cfg.add_sim_cfg("tb_b", sources=[])
		cfg.add_uvm_cfg(test="common_test", simulation="tb_a", verbosity="UVM_HIGH")
		cfg.add_uvm_cfg(test="common_test", simulation="tb_b", verbosity="UVM_LOW")

		# Correct — with sim_name specified
		assert cfg.get_uvm("common_test", "tb_a").verbosity == "UVM_HIGH"
		assert cfg.get_uvm("common_test", "tb_b").verbosity == "UVM_LOW"

		# Ambiguous — without sim_name, silently returns tb_a's config
		result = cfg.get_uvm("common_test")
		assert result.simulation == "tb_a"
		# If you were thinking of tb_b, you get tb_a's verbosity. Silent wrong answer.
		assert result.verbosity == "UVM_HIGH"  # not LOW — wrong for tb_b callers

	def test_uvm_without_sim_name_always_returns_first_registered(self, tmp_path):
		cfg = _cfg(tmp_path, vivado=False)
		cfg.add_sim_cfg("first", sources=[])
		cfg.add_sim_cfg("second", sources=[])
		cfg.add_uvm_cfg(test="t", simulation="second", verbosity="UVM_LOW")  # registered first
		cfg.add_uvm_cfg(test="t", simulation="first", verbosity="UVM_HIGH")  # registered second
		result = cfg.get_uvm("t")
		# Returns whichever was registered first in the list — ordering dependency
		assert result.simulation == "second"


# ===========================================================================
# TCL GENERATOR — actual Vivado command correctness
# ===========================================================================


class TestTclGeneratorCorrectness:
	"""
	The TCL output IS the product. These tests verify that the generated
	commands are what Vivado actually expects, not just that the Python
	config stored correctly.
	"""

	# --- project creation -------------------------------------------------

	def test_create_project_has_in_memory_flag(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "create_project -in_memory" in tcl

	def test_create_project_contains_fpga_part(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "xc7a200tfbg484-1" in tcl

	def test_board_part_set_property_present_when_configured(self, tmp_path):
		f = tmp_path / "project.toml"
		f.touch()
		cfg = XvivConfig(str(f), work_dir=str(tmp_path / "build"))
		cfg.add_fpga_cfg("zcu", board_part="xilinx.com:zcu102:part0:3.4", fpga_part="xczu9eg-ffvb1156-2-e")
		cfg.add_vivado_cfg(path=None)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "set_property board_part xilinx.com:zcu102:part0:3.4" in tcl

	def test_no_board_part_when_not_configured(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		# Match only lines that ARE a set_property board_part command, not paths containing the word
		bp_commands = [l for l in tcl.splitlines() if re.match(r"set_property board_part", l)]
		assert bp_commands == []

	# --- source file loading ----------------------------------------------

	def test_sv_file_uses_add_files_with_scan_for_includes(self, tmp_path):
		cfg = _cfg(tmp_path)
		src = _touch(tmp_path / "top.sv")
		cfg.add_design_cfg("top", sources=[src])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert f'add_files -scan_for_includes "{src}"' in tcl

	def test_constraint_file_added_to_constrs_fileset(self, tmp_path):
		cfg = _cfg(tmp_path)
		src = _touch(tmp_path / "top.sv")
		xdc = _touch(tmp_path / "top.xdc")
		cfg.add_design_cfg("top", sources=[src])
		cfg.add_synth_cfg(design="top", constraints=[xdc], run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert f'add_files -fileset constrs_1 "{xdc}"' in tcl

	def test_sim_only_source_excluded_from_synth_tcl(self, tmp_path):
		cfg = _cfg(tmp_path)
		rtl = _touch(tmp_path / "rtl.sv")
		tb = _touch(tmp_path / "tb.sv")
		cfg.add_design_cfg("top", sources=[rtl, {"files": [tb], "used_in": ["sim"]}])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "rtl.sv" in tcl
		assert "tb.sv" not in tcl

	def test_multiple_sources_each_get_own_add_files(self, tmp_path):
		cfg = _cfg(tmp_path)
		srcs = [_touch(tmp_path / f"mod_{i}.sv") for i in range(4)]
		cfg.add_design_cfg("top", sources=srcs)
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		add_lines = [l for l in tcl.splitlines() if "add_files -scan_for_includes" in l]
		assert len(add_lines) == 4

	# --- synth_design command ---------------------------------------------

	def test_synth_design_correct_top(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("my_module", sources=[], top="the_actual_top")
		cfg.add_synth_cfg(design="my_module", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="my_module")
		synth_line = next(l for l in tcl.splitlines() if "synth_design" in l)
		assert "-top the_actual_top" in synth_line

	def test_synth_design_default_mode(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		synth_line = next(l for l in tcl.splitlines() if "synth_design" in l)
		assert "-mode default" in synth_line

	def test_synth_design_custom_directive(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", synth_directive="AreaOptimized_high", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		synth_line = next(l for l in tcl.splitlines() if "synth_design" in l)
		assert '"AreaOptimized_high"' in synth_line

	def test_synth_design_custom_flatten_hierarchy(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", synth_flatten_hierarchy="full", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		synth_line = next(l for l in tcl.splitlines() if "synth_design" in l)
		assert "-flatten_hierarchy full" in synth_line

	def test_synth_design_fsm_extraction_sequential(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", synth_fsm_extraction="sequential", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		synth_line = next(l for l in tcl.splitlines() if "synth_design" in l)
		assert "-fsm_extraction sequential" in synth_line

	# --- stage ordering ---------------------------------------------------

	def test_stage_order_synth_before_opt_before_place_before_route(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		tcl = _tcl(cfg, design="top")
		lines = tcl.splitlines()
		idx = {
			cmd: next((i for i, l in enumerate(lines) if cmd in l), None)
			for cmd in [
				"synth_design",
				"opt_design",
				"place_design",
				"phys_opt_design",
				"route_design",
				"write_bitstream",
			]
		}
		assert idx["synth_design"] < idx["opt_design"], "opt must follow synth"
		assert idx["opt_design"] < idx["place_design"], "place must follow opt"
		assert idx["place_design"] < idx["phys_opt_design"], "phys_opt must follow place"
		assert idx["phys_opt_design"] < idx["route_design"], "route must follow phys_opt"
		assert idx["route_design"] < idx["write_bitstream"], "write_bitstream must follow route"

	def test_skipped_opt_does_not_appear_in_output(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_opt=False, run_phys_opt=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "opt_design" not in tcl
		assert "phys_opt_design" not in tcl
		assert "place_design" in tcl  # place still runs

	def test_skipped_place_also_skips_route(self, tmp_path):
		"""Can't route without placement."""
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "place_design" not in tcl
		assert "route_design" not in tcl

	# --- checkpoint writing -----------------------------------------------

	def test_synth_dcp_written_after_synth_design(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		lines = tcl.splitlines()
		synth_idx = next(i for i, l in enumerate(lines) if "synth_design" in l)
		ckpt_idx = next(i for i, l in enumerate(lines) if "write_checkpoint" in l and "synth.dcp" in l)
		assert ckpt_idx > synth_idx

	def test_route_dcp_written_after_route_design(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", bitstream=False)
		tcl = _tcl(cfg, design="top")
		lines = tcl.splitlines()
		route_idx = next(i for i, l in enumerate(lines) if "route_design" in l)
		rdcp_idx = next(i for i, l in enumerate(lines) if "write_checkpoint" in l and "route.dcp" in l)
		assert rdcp_idx > route_idx

	def test_no_dcp_when_disabled(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", synth_dcp=False, place_dcp=False, route_dcp=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "write_checkpoint" not in tcl

	def test_custom_dcp_path_used_in_write_checkpoint(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		custom = str(tmp_path / "my_synth.dcp")
		cfg.add_synth_cfg(design="top", synth_dcp=custom, run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert f'write_checkpoint -force "{custom}"' in tcl

	# --- bitstream --------------------------------------------------------

	def test_write_bitstream_uses_correct_path(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		tcl = _tcl(cfg, design="top")
		sc = cfg.get_synth(design_name="top")
		assert f'write_bitstream -force "{sc.bitstream}"' in tcl

	def test_no_write_bitstream_when_disabled(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", bitstream=False)
		tcl = _tcl(cfg, design="top")
		# Only match write_bitstream as a TCL command (line-start), not as part of a path
		bit_cmds = [l for l in tcl.splitlines() if re.match(r"write_bitstream", l)]
		assert bit_cmds == []

	# --- USR_ACCESS -------------------------------------------------------

	def test_usr_access_set_property_format(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", usr_access_value=0xDEADBEEF)
		tcl = _tcl(cfg, design="top")
		assert "set_property BITSTREAM.CONFIG.USR_ACCESS 0xDEADBEEF [current_design]" in tcl

	def test_usr_access_set_before_write_bitstream(self, tmp_path):
		"""The property must be applied before write_bitstream is called."""
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", usr_access_value=0xCAFEBABE)
		tcl = _tcl(cfg, design="top")
		lines = tcl.splitlines()
		prop_idx = next(i for i, l in enumerate(lines) if "USR_ACCESS" in l)
		bit_idx = next(i for i, l in enumerate(lines) if "write_bitstream" in l)
		assert prop_idx < bit_idx, "USR_ACCESS must be set before write_bitstream"

	def test_no_usr_access_when_not_set(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		tcl = _tcl(cfg, design="top")
		assert "USR_ACCESS" not in tcl

	# --- directives -------------------------------------------------------

	def test_opt_directive_applied(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", opt_directive="ExploreWithRemap", bitstream=False)
		tcl = _tcl(cfg, design="top")
		opt_line = next(l for l in tcl.splitlines() if "opt_design" in l)
		assert '"ExploreWithRemap"' in opt_line

	def test_place_directive_applied(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", place_directive="AltSpreadLogic_high", bitstream=False)
		tcl = _tcl(cfg, design="top")
		place_line = next(l for l in tcl.splitlines() if "place_design" in l)
		assert '"AltSpreadLogic_high"' in place_line

	def test_route_directive_applied(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", route_directive="AggressiveExplore")
		tcl = _tcl(cfg, design="top")
		route_line = next(l for l in tcl.splitlines() if "route_design" in l)
		assert '"AggressiveExplore"' in route_line

	def test_phys_opt_directive_applied(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", phys_opt_directive="AggressiveExplore", bitstream=False)
		tcl = _tcl(cfg, design="top")
		phys_line = next(l for l in tcl.splitlines() if "phys_opt_design" in l)
		assert '"AggressiveExplore"' in phys_line

	# --- report generation ------------------------------------------------

	def test_synth_timing_summary_report_written(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", synth_report_timing_summary=True, run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		sc = cfg.get_synth(design_name="top")
		assert "report_timing_summary" in tcl
		assert sc.synth_report_timing_summary in tcl

	def test_route_drc_report_written(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", route_report_drc=True, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "report_drc" in tcl

	def test_route_power_report_written(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", route_report_power=True, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "report_power" in tcl

	# --- ip repo list ---------------------------------------------------

	def test_ip_repo_paths_set_in_project(self, tmp_path):
		cfg = _cfg(tmp_path)
		repo = tmp_path / "my_repo"
		repo.mkdir()
		cfg.add_ip_cfg("my_ip", sources=[], repo=str(repo))
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		assert "ip_repo_paths" in tcl
		assert str(repo) in tcl

	def test_same_repo_added_by_two_ips_not_duplicated_in_tcl(self, tmp_path):
		cfg = _cfg(tmp_path)
		repo = tmp_path / "shared_repo"
		repo.mkdir()
		cfg.add_ip_cfg("ip_a", sources=[], repo=str(repo))
		cfg.add_ip_cfg("ip_b", sources=[], repo=str(repo))
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top", run_place=False, run_route=False, bitstream=False)
		tcl = _tcl(cfg, design="top")
		# repo path should appear exactly once
		assert tcl.count(str(repo)) == 1

	# --- resume -----------------------------------------------------------

	def test_resume_invalid_stage_raises_synth_resume_invalid_error(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		with pytest.raises(error.SynthResumeInvalidError):
			_tcl(cfg, design="top", resume="bananas")

	def test_resume_valid_stages_accepted(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		sc = cfg.get_synth(design_name="top")
		# Create the DCP that resume="synth" would need
		_touch(sc.synth_dcp)
		tcl = _tcl(cfg, design="top", resume="synth")
		# resumed from synth DCP — should open_checkpoint, not run synth_design
		assert "open_checkpoint" in tcl
		assert "synth_design" not in tcl

	def test_resume_route_skips_synth_opt_place_phys(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_design_cfg("top", sources=[])
		cfg.add_synth_cfg(design="top")
		sc = cfg.get_synth(design_name="top")
		_touch(sc.route_dcp)
		tcl = _tcl(cfg, design="top", resume="route")
		assert "synth_design" not in tcl
		assert "opt_design" not in tcl
		assert "place_design" not in tcl
		assert "phys_opt_design" not in tcl
		assert "write_bitstream" in tcl

	# --- synth no-identifier ----------------------------------------------

	def test_synth_with_no_identifier_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises(error.SynthNoIdentifierError):
			ConfigTclCommands(cfg).synth().build()
