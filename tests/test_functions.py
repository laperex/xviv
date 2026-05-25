from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from xviv.functions.bd import cmd_bd_create, cmd_bd_edit, cmd_bd_generate
from xviv.functions.core import (
	cmd_core_create,
	cmd_core_edit,
	cmd_core_generate,
	cmd_search_core,
)
from xviv.functions.formal import cmd_formal
from xviv.functions.ip import cmd_ip_create, cmd_ip_edit
from xviv.functions.simulation import cmd_simulate, cmd_wdb_open, cmd_wdb_reload
from xviv.utils import error

# ---------------------------------------------------------------------------
# Module-path constants used for patching
# ---------------------------------------------------------------------------

SIM_MODULE = "xviv.functions.simulation"
FORMAL_MODULE = "xviv.functions.formal"
IP_MODULE = "xviv.functions.ip"
BD_MODULE = "xviv.functions.bd"
CORE_MODULE = "xviv.functions.core"

# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------


def _make_cfg(*, dry_run: bool = False) -> MagicMock:
	cfg = MagicMock()
	cfg.dry_run = dry_run
	return cfg


def _make_sim_cfg(
	*,
	name: str = "my_sim",
	top: str = "tb_top",
	backend: str = "xsim",
	design: str | None = None,
	work_dir: str = "/build/sim/my_sim",
	sdfmax: list[str] | None = None,
	sdfmin: list[str] | None = None,
) -> MagicMock:
	sim_cfg = MagicMock()
	sim_cfg.name = name
	sim_cfg.top = top
	sim_cfg.backend = backend
	sim_cfg.design = design
	sim_cfg.work_dir = work_dir
	sim_cfg.timescale = "1ns/1ps"
	sim_cfg.defines = []
	sim_cfg.include_dirs = []
	sim_cfg.plusargs = []
	sim_cfg.sdfmax = sdfmax or []
	sim_cfg.sdfmin = sdfmin or []
	src = MagicMock()
	src.file = "sim_top.sv"
	sim_cfg.sources = [src]
	return sim_cfg


def _make_formal_result(*, passed: bool = True, vcd: str | None = None, name: str = "test_formal") -> MagicMock:
	r = MagicMock()
	r.name = name
	r.passed = passed
	r.vcd = vcd
	return r


def _make_formal_cfg(*, name: str = "my_formal", mode: str = "bmc") -> MagicMock:
	fcfg = MagicMock()
	fcfg.name = name
	fcfg.mode = mode
	fcfg.depth = 20
	return fcfg


def _make_catalog_entry(
	*,
	vlnv: str = "xilinx.com:ip:fifo_generator:13.2",
	name: str = "fifo_generator",
	display_name: str = "FIFO Generator",
	description: str = "Generates FIFOs of various types",
	hidden: bool = False,
	board_dependent: bool = False,
	ipi_only: bool = False,
) -> MagicMock:
	entry = MagicMock()
	entry.vlnv = vlnv
	entry.name = name
	entry.display_name = display_name
	entry.description = description
	entry.hidden = hidden
	entry.board_dependent = board_dependent
	entry.ipi_only = ipi_only
	return entry


def _make_catalog(entries: list[MagicMock]) -> MagicMock:
	catalog = MagicMock()
	catalog.values.return_value = entries
	return catalog


# ===========================================================================
# cmd_simulate
# ===========================================================================


class TestCmdSimulate:
	# -- backend dispatch --------------------------------------------------

	def test_xsim_backend_dispatches_to_run_xsim(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg(backend="xsim")
		with (
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._run_verilator") as mock_vrl,
		):
			cmd_simulate(cfg, sim_name="my_sim")
		mock_xsim.assert_called_once()
		mock_vrl.assert_not_called()

	def test_verilator_backend_dispatches_to_run_verilator(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg(backend="verilator")
		with (
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._run_verilator") as mock_vrl,
		):
			cmd_simulate(cfg, sim_name="my_sim")
		mock_vrl.assert_called_once()
		mock_xsim.assert_not_called()

	# -- run argument ------------------------------------------------------

	def test_run_defaults_to_all(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg()
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim")
		# positional: (cfg, sim_name, uvm_name, svlog_files, sdfmax, sdfmin, run)
		run_arg = mock_xsim.call_args[0][6]
		assert run_arg == "all"

	def test_explicit_run_value_forwarded(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg()
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim", run="100ns")
		run_arg = mock_xsim.call_args[0][6]
		assert run_arg == "100ns"

	# -- UVM forwarding ----------------------------------------------------

	def test_uvm_name_forwarded_to_run_xsim(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg()
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim", uvm_name="my_uvm_test")
		uvm_name_arg = mock_xsim.call_args[0][2]
		assert uvm_name_arg == "my_uvm_test"

	def test_uvm_name_none_forwarded_when_not_provided(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg()
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim")
		uvm_name_arg = mock_xsim.call_args[0][2]
		assert uvm_name_arg is None

	# -- source file accumulation -----------------------------------------

	def test_sim_sources_always_appended(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		sim_cfg.design = None
		src = MagicMock()
		src.file = "tb_explicit.sv"
		sim_cfg.sources = [src]
		cfg.get_sim.return_value = sim_cfg
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim")
		svlog_files = mock_xsim.call_args[0][3]
		assert "tb_explicit.sv" in svlog_files

	def test_design_sources_included_in_default_mode(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		dsrc = MagicMock()
		dsrc.file = "top.sv"
		design_cfg = MagicMock()
		design_cfg.sources = [dsrc]
		cfg.get_design.return_value = design_cfg
		with patch(f"{SIM_MODULE}._run_xsim") as mock_xsim:
			cmd_simulate(cfg, sim_name="my_sim", mode="default")
		svlog_files = mock_xsim.call_args[0][3]
		assert "top.sv" in svlog_files

	def test_design_sources_not_fetched_in_post_synth_mode(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.synth_functional_netlist_file = "/build/synth/func.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim"),
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_synth_functional")
		cfg.get_design.assert_not_called()

	# -- post-synthesis modes ----------------------------------------------

	def test_post_synth_functional_uses_synth_functional_netlist(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.synth_functional_netlist_file = "/build/synth/func.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_synth_functional")
		svlog_files = mock_xsim.call_args[0][3]
		assert "/build/synth/func.v" in svlog_files

	def test_post_synth_functional_calls_assert_file_exists(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.synth_functional_netlist_file = "/build/synth/func.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists") as mock_assert,
			patch(f"{SIM_MODULE}._run_xsim"),
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_synth_functional")
		mock_assert.assert_called_with(synth_cfg.synth_functional_netlist_file)

	def test_post_synth_timing_uses_timing_netlist(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.synth_timing_netlist_file = "/build/synth/timing.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_synth_timing")
		svlog_files = mock_xsim.call_args[0][3]
		assert "/build/synth/timing.v" in svlog_files

	def test_post_impl_functional_uses_impl_functional_netlist(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.impl_functional_netlist_file = "/build/synth/impl_func.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_impl_functional")
		svlog_files = mock_xsim.call_args[0][3]
		assert "/build/synth/impl_func.v" in svlog_files

	def test_post_impl_timing_appends_timing_netlist_to_svlog_files(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design", sdfmax=["tb_top/dut"])
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.impl_timing_sdf_file = "/build/synth/timing.sdf"
		synth_cfg.impl_timing_netlist_file = "/build/synth/timing.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_impl_timing")
		svlog_files = mock_xsim.call_args[0][3]
		assert "/build/synth/timing.v" in svlog_files

	def test_post_impl_timing_builds_sdfmax_entries(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design", sdfmax=["tb_top/dut"])
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.impl_timing_sdf_file = "/build/synth/timing.sdf"
		synth_cfg.impl_timing_netlist_file = "/build/synth/timing.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_impl_timing")
		sdfmax_entries = mock_xsim.call_args[0][4]
		assert any("/build/synth/timing.sdf" in e for e in sdfmax_entries)
		assert any("tb_top/dut" in e for e in sdfmax_entries)

	def test_post_impl_timing_builds_sdfmin_entries(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design", sdfmin=["tb_top/dut"])
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.impl_timing_sdf_file = "/build/synth/timing.sdf"
		synth_cfg.impl_timing_netlist_file = "/build/synth/timing.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}._run_xsim") as mock_xsim,
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_impl_timing")
		sdfmin_entries = mock_xsim.call_args[0][5]
		assert any("/build/synth/timing.sdf" in e for e in sdfmin_entries)

	def test_post_impl_timing_calls_assert_for_both_sdf_and_netlist(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		synth_cfg = MagicMock()
		synth_cfg.impl_timing_sdf_file = "/build/synth/timing.sdf"
		synth_cfg.impl_timing_netlist_file = "/build/synth/timing.v"
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SIM_MODULE}.assert_file_exists") as mock_assert,
			patch(f"{SIM_MODULE}._run_xsim"),
		):
			cmd_simulate(cfg, sim_name="my_sim", mode="post_impl_timing")
		assert mock_assert.call_count == 2

	def test_invalid_mode_raises_error(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(design="my_design")
		cfg.get_sim.return_value = sim_cfg
		cfg.get_synth.return_value = MagicMock()
		with pytest.raises(error.InvalidSimulationMode):
			cmd_simulate(cfg, sim_name="my_sim", mode="bad_mode")

	def test_no_design_skips_source_file_resolution(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		sim_cfg.design = None
		cfg.get_sim.return_value = sim_cfg
		with patch(f"{SIM_MODULE}._run_xsim"):
			cmd_simulate(cfg, sim_name="my_sim")
		cfg.get_design.assert_not_called()
		cfg.get_synth.assert_not_called()

	def test_get_sim_called_with_sim_name(self):
		cfg = _make_cfg()
		cfg.get_sim.return_value = _make_sim_cfg()
		with patch(f"{SIM_MODULE}._run_xsim"):
			cmd_simulate(cfg, sim_name="my_sim")
		cfg.get_sim.assert_called_once_with("my_sim")


# ===========================================================================
# cmd_wdb_open
# ===========================================================================


class TestCmdWdbOpen:
	def _setup(self, cfg, sim_cfg):
		cfg.get_sim.return_value = sim_cfg

	def test_calls_waveform_setup_with_correct_top_name(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(top="tb_top", work_dir="/build/sim/my_sim")
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim"),
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		kwargs = MockTcl.return_value.waveform_setup.call_args[1]
		assert kwargs["top_name"] == "tb_top"

	def test_wdb_file_uses_top_name_and_work_dir(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(top="tb_top", work_dir="/build/sim/my_sim")
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim"),
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		kwargs = MockTcl.return_value.waveform_setup.call_args[1]
		assert kwargs["wdb_file"] == "/build/sim/my_sim/tb_top.wdb"
		assert kwargs["wcfg_file"] == "/build/sim/my_sim/tb_top.wcfg"
		assert kwargs["fifo_file"] == f"{kwargs['wdb_file']}.fifo"

	def test_ensures_fifo_before_running_xsim(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		self._setup(cfg, sim_cfg)
		call_order = []
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim", side_effect=lambda *a, **k: call_order.append("xsim")),
			patch(f"{SIM_MODULE}._ensure_fifo", side_effect=lambda *a: call_order.append("fifo")),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert call_order.index("fifo") < call_order.index("xsim")

	def test_ensure_fifo_called_with_correct_path(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(top="tb_top", work_dir="/build/sim/my_sim")
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim"),
			patch(f"{SIM_MODULE}._ensure_fifo") as mock_fifo,
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		mock_fifo.assert_called_once_with("/build/sim/my_sim/tb_top.wdb.fifo")

	def test_runs_xsim_in_popen_mode(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert mock_xsim.call_args[1]["popen"] is True

	def test_stats_is_false(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert mock_xsim.call_args[1]["stats"] is False

	def test_wdb_file_forwarded_to_xsim(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(top="tb_top", work_dir="/build/sim/my_sim")
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert mock_xsim.call_args[1]["wdb_file"] == "/build/sim/my_sim/tb_top.wdb"

	def test_nogui_true_forwarded_to_xsim(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim", nogui=True)
		assert mock_xsim.call_args[1]["nogui"] is True

	def test_nogui_false_by_default(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg()
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert mock_xsim.call_args[1]["nogui"] is False

	def test_target_dir_matches_sim_work_dir(self):
		cfg = _make_cfg()
		sim_cfg = _make_sim_cfg(work_dir="/build/sim/my_sim")
		self._setup(cfg, sim_cfg)
		with (
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}.vivado.run_vivado_xsim") as mock_xsim,
			patch(f"{SIM_MODULE}._ensure_fifo"),
		):
			MockTcl.return_value.waveform_setup.return_value.build.return_value = MagicMock()
			cmd_wdb_open(cfg, sim_name="my_sim")
		assert mock_xsim.call_args[1]["target_dir"] == "/build/sim/my_sim"


# ===========================================================================
# cmd_wdb_reload
# ===========================================================================


class TestCmdWdbReload:
	def _setup(self, cfg):
		sim_cfg = _make_sim_cfg(top="tb_top", work_dir="/build/sim/my_sim")
		cfg.get_sim.return_value = sim_cfg
		return sim_cfg

	def test_asserts_fifo_file_exists(self):
		cfg = _make_cfg()
		self._setup(cfg)
		with (
			patch(f"{SIM_MODULE}.assert_file_exists") as mock_assert,
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}._fifo_send"),
		):
			MockTcl.return_value.waveform_reload.return_value.build.return_value = MagicMock()
			cmd_wdb_reload(cfg, sim_name="my_sim")
		mock_assert.assert_called_once_with("/build/sim/my_sim/tb_top.wdb.fifo")

	def test_sends_reload_command_via_fifo(self):
		cfg = _make_cfg()
		self._setup(cfg)
		mock_cmd = "reload_command_tcl"
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}._fifo_send") as mock_send,
		):
			MockTcl.return_value.waveform_reload.return_value.build.return_value = mock_cmd
			cmd_wdb_reload(cfg, sim_name="my_sim")
		mock_send.assert_called_once_with("/build/sim/my_sim/tb_top.wdb.fifo", mock_cmd)

	def test_fifo_send_receives_built_tcl(self):
		cfg = _make_cfg()
		self._setup(cfg)
		expected_tcl = "waveform reload tcl script"
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}._fifo_send") as mock_send,
		):
			MockTcl.return_value.waveform_reload.return_value.build.return_value = expected_tcl
			cmd_wdb_reload(cfg, sim_name="my_sim")
		_, cmd_arg = mock_send.call_args[0]
		assert cmd_arg == expected_tcl

	def test_get_sim_called_with_sim_name(self):
		cfg = _make_cfg()
		self._setup(cfg)
		with (
			patch(f"{SIM_MODULE}.assert_file_exists"),
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}._fifo_send"),
		):
			MockTcl.return_value.waveform_reload.return_value.build.return_value = MagicMock()
			cmd_wdb_reload(cfg, sim_name="my_sim")
		cfg.get_sim.assert_called_once_with("my_sim")

	def test_assert_called_before_send(self):
		cfg = _make_cfg()
		self._setup(cfg)
		order = []
		with (
			patch(f"{SIM_MODULE}.assert_file_exists", side_effect=lambda *a: order.append("assert")),
			patch(f"{SIM_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SIM_MODULE}._fifo_send", side_effect=lambda *a: order.append("send")),
		):
			MockTcl.return_value.waveform_reload.return_value.build.return_value = MagicMock()
			cmd_wdb_reload(cfg, sim_name="my_sim")
		assert order == ["assert", "send"]


# ===========================================================================
# cmd_formal
# ===========================================================================


class TestCmdFormal:
	def test_raises_formal_no_targets_error_when_list_empty(self):
		cfg = _make_cfg()
		cfg.get_formal_list.return_value = []
		with pytest.raises(error.FormalNoTargetsError):
			cmd_formal(cfg)

	def test_validates_each_target(self):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		result = _make_formal_result()
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=result):
			cmd_formal(cfg)
		cfg.validate_formal.assert_called_once_with(fcfg.name)

	def test_runs_formal_for_all_targets_when_no_target_specified(self):
		cfg = _make_cfg()
		fcfg_a = _make_formal_cfg(name="formal_a")
		fcfg_b = _make_formal_cfg(name="formal_b")
		cfg.get_formal_list.return_value = [fcfg_a, fcfg_b]
		with patch(
			f"{FORMAL_MODULE}.run_formal", side_effect=[_make_formal_result(), _make_formal_result()]
		) as mock_run:
			cmd_formal(cfg)
		assert mock_run.call_count == 2

	def test_runs_only_specific_target_when_target_provided(self):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg(name="specific_formal")
		other = _make_formal_cfg(name="other_formal")
		cfg.get_formal_list.return_value = [fcfg, other]
		cfg.get_formal.return_value = fcfg
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result()) as mock_run:
			cmd_formal(cfg, target="specific_formal")
		mock_run.assert_called_once()
		cfg.get_formal.assert_called_once_with("specific_formal")

	def test_validates_before_running(self):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		order = []
		cfg.validate_formal.side_effect = lambda *a: order.append("validate")
		with patch(
			f"{FORMAL_MODULE}.run_formal", side_effect=lambda *a, **k: (order.append("run"), _make_formal_result())[1]
		):
			cmd_formal(cfg)
		assert order == ["validate", "run"]

	def test_passes_dry_run_true(self):
		cfg = _make_cfg(dry_run=True)
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result()) as mock_run:
			cmd_formal(cfg)
		_, kwargs = mock_run.call_args
		assert kwargs["dry_run"] is True

	def test_passes_dry_run_false(self):
		cfg = _make_cfg(dry_run=False)
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result()) as mock_run:
			cmd_formal(cfg)
		_, kwargs = mock_run.call_args
		assert kwargs["dry_run"] is False

	def test_does_not_raise_when_all_pass(self):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result(passed=True)):
			cmd_formal(cfg)  # must not raise

	def test_raises_system_exit_1_when_any_formal_fails(self):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result(passed=False)):
			with pytest.raises(SystemExit) as exc_info:
				cmd_formal(cfg)
		assert exc_info.value.code == 1

	def test_raises_system_exit_1_when_one_of_many_fails(self):
		cfg = _make_cfg()
		fcfg_a = _make_formal_cfg(name="a")
		fcfg_b = _make_formal_cfg(name="b")
		cfg.get_formal_list.return_value = [fcfg_a, fcfg_b]
		with patch(
			f"{FORMAL_MODULE}.run_formal",
			side_effect=[_make_formal_result(passed=True), _make_formal_result(passed=False)],
		):
			with pytest.raises(SystemExit) as exc_info:
				cmd_formal(cfg)
		assert exc_info.value.code == 1

	def test_prints_vcd_path_when_result_has_trace(self, capsys):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(
			f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result(passed=False, vcd="/path/to/trace.vcd")
		):
			with pytest.raises(SystemExit):
				cmd_formal(cfg)
		out = capsys.readouterr().out
		assert "trace.vcd" in out

	def test_no_vcd_output_when_vcd_is_none(self, capsys):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg()
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result(passed=True, vcd=None)):
			cmd_formal(cfg)
		out = capsys.readouterr().out
		assert "gtkwave" not in out

	def test_summary_table_printed(self, capsys):
		cfg = _make_cfg()
		fcfg = _make_formal_cfg(name="my_check")
		cfg.get_formal_list.return_value = [fcfg]
		with patch(f"{FORMAL_MODULE}.run_formal", return_value=_make_formal_result(passed=True)):
			cmd_formal(cfg)
		out = capsys.readouterr().out
		assert "my_check" in out


# ===========================================================================
# cmd_ip_create
# ===========================================================================


class TestCmdIpCreate:
	def _setup_ip_cfg(self, cfg, vlnv="xviv.org:xviv:my_ip:1.0"):
		ip_cfg = MagicMock()
		ip_cfg.vlnv = vlnv
		cfg.get_ip.return_value = ip_cfg
		cfg._core_list = []
		return ip_cfg

	def test_validates_ip_before_anything_else(self):
		cfg = _make_cfg()
		ip_cfg = self._setup_ip_cfg(cfg)
		order = []
		cfg.validate_ip.side_effect = lambda *a, **k: order.append("validate")
		cfg.build_attach_ip_wrapper.side_effect = lambda *a, **k: order.append("attach")
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel"),
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()
			cmd_ip_create(cfg, ip_name="my_ip")
		assert order[0] == "validate"
		cfg.validate_ip.assert_called_once_with("my_ip")

	def test_attaches_wrapper_after_validation(self):
		cfg = _make_cfg()
		self._setup_ip_cfg(cfg)
		order = []
		cfg.validate_ip.side_effect = lambda *a, **k: order.append("validate")
		cfg.build_attach_ip_wrapper.side_effect = lambda *a, **k: order.append("attach")
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel"),
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()
			cmd_ip_create(cfg, ip_name="my_ip")
		assert order.index("validate") < order.index("attach")
		cfg.build_attach_ip_wrapper.assert_called_once_with("my_ip")

	def test_runs_vivado_with_create_ip_config(self):
		cfg = _make_cfg()
		self._setup_ip_cfg(cfg)
		mock_config = MagicMock()
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado") as mock_vivado,
			patch(f"{IP_MODULE}.run_parallel"),
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = mock_config
			cmd_ip_create(cfg, ip_name="my_ip")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_create_ip_tcl_built_for_correct_ip(self):
		cfg = _make_cfg()
		self._setup_ip_cfg(cfg)
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel"),
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()
			cmd_ip_create(cfg, ip_name="my_ip")
		MockTcl.return_value.create_ip.assert_called_once_with("my_ip", edit=False, nogui=False)

	def test_runs_parallel_for_matching_cores_with_existing_xci(self, tmp_path):
		cfg = _make_cfg()
		self._setup_ip_cfg(cfg, vlnv="xviv.org:xviv:my_ip:1.0")

		xci = tmp_path / "my_core.xci"
		xci.touch()

		core = MagicMock()
		core.name = "my_core"
		core.vlnv = "xviv.org:xviv:my_ip:1.0"
		core.xci_file = str(xci)

		cfg._core_list = [core]

		catalog_entry = MagicMock()
		catalog_entry.vlnv = "xviv.org:xviv:my_ip:1.0"

		cfg.get_catalog().lookup.return_value = catalog_entry

		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()

			cmd_ip_create(cfg, ip_name="my_ip", regenerate=True)

		mock_parallel.assert_called_once()

		tasks = mock_parallel.call_args[0][0]

		assert len(tasks) == 1

		_, label = tasks[0]

		assert label == "my_core"

	def test_skips_cores_with_mismatched_vlnv(self, tmp_path):
		cfg = _make_cfg()

		self._setup_ip_cfg(cfg, vlnv="xviv.org:xviv:my_ip:1.0")

		xci = tmp_path / "other_core.xci"
		xci.touch()

		core = MagicMock()
		core.name = "other_core"
		core.vlnv = "xviv.org:xviv:different_ip:2.0"
		core.xci_file = str(xci)

		cfg._core_list = [core]

		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()

			cmd_ip_create(cfg, ip_name="my_ip", regenerate=True)

		mock_parallel.assert_called_once()

		tasks = mock_parallel.call_args[0][0]

		assert len(tasks) == 0

	def test_skips_cores_whose_xci_does_not_exist(self):
		cfg = _make_cfg()

		self._setup_ip_cfg(cfg, vlnv="xviv.org:xviv:my_ip:1.0")

		core = MagicMock()
		core.name = "my_core"
		core.vlnv = "xviv.org:xviv:my_ip:1.0"
		core.xci_file = "/nonexistent/my_core.xci"

		cfg._core_list = [core]

		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()

			cmd_ip_create(cfg, ip_name="my_ip", regenerate=True)

		mock_parallel.assert_called_once()

		tasks = mock_parallel.call_args[0][0]

		assert len(tasks) == 0

	def test_multiple_matching_cores_all_included(self, tmp_path):
		cfg = _make_cfg()

		self._setup_ip_cfg(cfg, vlnv="xviv.org:xviv:my_ip:1.0")

		cores = []

		for i in range(3):
			xci = tmp_path / f"core_{i}.xci"
			xci.touch()

			core = MagicMock()
			core.name = f"core_{i}"
			core.vlnv = "xviv.org:xviv:my_ip:1.0"
			core.xci_file = str(xci)

			cores.append(core)

		cfg._core_list = cores

		catalog_entry = MagicMock()
		catalog_entry.vlnv = "xviv.org:xviv:my_ip:1.0"

		cfg.get_catalog().lookup.return_value = catalog_entry

		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
			patch(f"{IP_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.create_ip.return_value.build.return_value = MagicMock()

			cmd_ip_create(cfg, ip_name="my_ip", regenerate=True)

		mock_parallel.assert_called_once()

		tasks = mock_parallel.call_args[0][0]

		assert len(tasks) == 3


# ===========================================================================
# cmd_ip_edit
# ===========================================================================


class TestCmdIpEdit:
	def test_builds_edit_ip_tcl_with_correct_ip_name(self):
		cfg = _make_cfg()
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_ip.return_value.build.return_value = MagicMock()
			cmd_ip_edit(cfg, ip_name="my_ip")
		MockTcl.return_value.edit_ip.assert_called_once_with("my_ip", nogui=False)

	def test_nogui_forwarded_to_edit_ip_tcl(self):
		cfg = _make_cfg()
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_ip.return_value.build.return_value = MagicMock()
			cmd_ip_edit(cfg, ip_name="my_ip", nogui=True)
		MockTcl.return_value.edit_ip.assert_called_once_with("my_ip", nogui=True)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.edit_ip.return_value.build.return_value = mock_config
			cmd_ip_edit(cfg, ip_name="my_ip")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_sets_tcl_mode_on_cfg_vivado_when_nogui(self):
		cfg = _make_cfg()

		vivado_cfg = MagicMock()
		cfg.get_vivado.return_value = vivado_cfg

		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_ip.return_value.build.return_value = MagicMock()

			cmd_ip_edit(cfg, ip_name="my_ip", nogui=True)

		assert vivado_cfg.mode == "tcl"

	def test_does_not_set_tcl_mode_when_not_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with (
			patch(f"{IP_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{IP_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_ip.return_value.build.return_value = MagicMock()
			cmd_ip_edit(cfg, ip_name="my_ip", nogui=False)
		assert vivado_cfg.mode == "batch"


# ===========================================================================
# cmd_bd_create
# ===========================================================================


class TestCmdBdCreate:
	def test_builds_create_bd_tcl_with_generate_true(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.create_bd.return_value.build.return_value = MagicMock()
			cmd_bd_create(cfg, bd_name="my_bd")
		MockTcl.return_value.create_bd.assert_called_once_with(
			"my_bd", generate=True, source_file=True, edit=False, nogui=False
		)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.create_bd.return_value.build.return_value = mock_config
			cmd_bd_create(cfg, bd_name="my_bd")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_configtclcommands_initialised_with_cfg(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.create_bd.return_value.build.return_value = MagicMock()
			cmd_bd_create(cfg, bd_name="my_bd")
		MockTcl.assert_called_once_with(cfg)


# ===========================================================================
# cmd_bd_edit
# ===========================================================================


class TestCmdBdEdit:
	def test_builds_edit_bd_tcl_with_correct_name(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = MagicMock()
			cmd_bd_edit(cfg, bd_name="my_bd")
		MockTcl.return_value.edit_bd.assert_called_once_with("my_bd", nogui=False)

	def test_nogui_forwarded_to_edit_bd_tcl(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = MagicMock()
			cmd_bd_edit(cfg, bd_name="my_bd", nogui=True)
		MockTcl.return_value.edit_bd.assert_called_once_with("my_bd", nogui=True)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = mock_config
			cmd_bd_edit(cfg, bd_name="my_bd")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_sets_tcl_mode_when_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = MagicMock()
			cmd_bd_edit(cfg, bd_name="my_bd", nogui=True)
		assert vivado_cfg.mode == "tcl"

	def test_does_not_change_mode_when_not_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = MagicMock()
			cmd_bd_edit(cfg, bd_name="my_bd", nogui=False)
		assert vivado_cfg.mode == "batch"

	def test_mode_set_before_running_vivado(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		order = []
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado", side_effect=lambda *a, **k: order.append(("run", vivado_cfg.mode))),
		):
			MockTcl.return_value.edit_bd.return_value.build.return_value = MagicMock()
			cmd_bd_edit(cfg, bd_name="my_bd", nogui=True)
		# vivado.mode should already be "tcl" at the time run_vivado is called
		assert order[0] == ("run", "tcl")


# ===========================================================================
# cmd_bd_generate
# ===========================================================================


class TestCmdBdGenerate:
	def test_builds_generate_bd_tcl_with_correct_name(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.generate_bd.return_value.build.return_value = MagicMock()
			cmd_bd_generate(cfg, bd_name="my_bd")
		MockTcl.return_value.generate_bd.assert_called_once_with("my_bd", force=True, reset=True)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.generate_bd.return_value.build.return_value = mock_config
			cmd_bd_generate(cfg, bd_name="my_bd")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_configtclcommands_initialised_with_cfg(self):
		cfg = _make_cfg()
		with (
			patch(f"{BD_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{BD_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.generate_bd.return_value.build.return_value = MagicMock()
			cmd_bd_generate(cfg, bd_name="my_bd")
		MockTcl.assert_called_once_with(cfg)


# ===========================================================================
# cmd_core_create
# ===========================================================================


class TestCmdCoreCreate:
	def test_builds_create_core_tcl_with_correct_name_generate_edit_in_gui(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.create_core.return_value.build.return_value = MagicMock()
			cmd_core_create(cfg, core_name="my_core")
		MockTcl.return_value.create_core.assert_called_once_with("my_core", generate=True, edit=True, nogui=False)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.create_core.return_value.build.return_value = mock_config
			cmd_core_create(cfg, core_name="my_core")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_configtclcommands_initialised_with_cfg(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.create_core.return_value.build.return_value = MagicMock()
			cmd_core_create(cfg, core_name="my_core")
		MockTcl.assert_called_once_with(cfg)


# ===========================================================================
# cmd_core_edit
# ===========================================================================


class TestCmdCoreEdit:
	def test_builds_edit_core_tcl_with_correct_name(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = MagicMock()
			cmd_core_edit(cfg, core_name="my_core")
		MockTcl.return_value.edit_core.assert_called_once_with("my_core", nogui=False)

	def test_nogui_forwarded_to_edit_core_tcl(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = MagicMock()
			cmd_core_edit(cfg, core_name="my_core", nogui=True)
		MockTcl.return_value.edit_core.assert_called_once_with("my_core", nogui=True)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = mock_config
			cmd_core_edit(cfg, core_name="my_core")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_sets_tcl_mode_when_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = MagicMock()
			cmd_core_edit(cfg, core_name="my_core", nogui=True)
		assert vivado_cfg.mode == "tcl"

	def test_does_not_change_mode_when_not_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = MagicMock()
			cmd_core_edit(cfg, core_name="my_core", nogui=False)
		assert vivado_cfg.mode == "batch"

	def test_mode_set_before_running_vivado(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		order = []
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(
				f"{CORE_MODULE}.vivado.run_vivado", side_effect=lambda *a, **k: order.append(("run", vivado_cfg.mode))
			),
		):
			MockTcl.return_value.edit_core.return_value.build.return_value = MagicMock()
			cmd_core_edit(cfg, core_name="my_core", nogui=True)
		assert order[0] == ("run", "tcl")


# ===========================================================================
# cmd_core_generate
# ===========================================================================


class TestCmdCoreGenerate:
	def test_builds_generate_core_tcl_with_correct_name(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.generate_core.return_value.build.return_value = MagicMock()
			cmd_core_generate(cfg, core_name="my_core")
		MockTcl.return_value.generate_core.assert_called_once_with("my_core", force=True, reset=True)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado") as mock_vivado,
		):
			MockTcl.return_value.generate_core.return_value.build.return_value = mock_config
			cmd_core_generate(cfg, core_name="my_core")
		mock_vivado.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_configtclcommands_initialised_with_cfg(self):
		cfg = _make_cfg()
		with (
			patch(f"{CORE_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{CORE_MODULE}.vivado.run_vivado"),
		):
			MockTcl.return_value.generate_core.return_value.build.return_value = MagicMock()
			cmd_core_generate(cfg, core_name="my_core")
		MockTcl.assert_called_once_with(cfg)


# ===========================================================================
# cmd_search_core
# ===========================================================================


class TestCmdSearchCore:
	def _cfg_with_catalog(self, entries: list[MagicMock]) -> MagicMock:
		cfg = _make_cfg()
		cfg.get_catalog.return_value = _make_catalog(entries)
		return cfg

	# -- catalog access ----------------------------------------------------

	def test_calls_get_catalog(self, capsys):
		cfg = self._cfg_with_catalog([])
		cmd_search_core(cfg, query="fifo")
		cfg.get_catalog.assert_called_once()

	# -- no-match path -----------------------------------------------------

	def test_prints_no_results_message_when_no_match(self, capsys):
		cfg = self._cfg_with_catalog([])
		cmd_search_core(cfg, query="xyzzy_unique")
		out = capsys.readouterr().out
		assert "No IPs found" in out

	def test_no_results_message_includes_query(self, capsys):
		cfg = self._cfg_with_catalog([])
		cmd_search_core(cfg, query="xyzzy_unique")
		out = capsys.readouterr().out
		assert "xyzzy_unique" in out

	def test_no_match_prints_tip(self, capsys):
		cfg = self._cfg_with_catalog([])
		cmd_search_core(cfg, query="nothing")
		out = capsys.readouterr().out
		assert "Tip:" in out

	# -- filtering ---------------------------------------------------------

	def test_hidden_entries_excluded_from_results(self, capsys):
		hidden = _make_catalog_entry(
			vlnv="x:y:hidden_core:1.0",
			name="hidden_core",
			display_name="Hidden Core",
			description="A hidden core",
			hidden=True,
		)
		visible = _make_catalog_entry(
			vlnv="x:y:visible_core:1.0",
			name="visible_core",
			display_name="Visible Core",
			description="A visible core",
			hidden=False,
		)
		cfg = self._cfg_with_catalog([hidden, visible])
		cmd_search_core(cfg, query="core")
		out = capsys.readouterr().out
		assert "visible_core" in out
		assert "hidden_core" not in out

	# -- search fields -----------------------------------------------------

	def test_matches_by_vlnv(self, capsys):
		entry = _make_catalog_entry(
			vlnv="xilinx.com:ip:axis_fifo:1.0",
			name="axis_fifo",
			display_name="AXI Stream FIFO",
			description="An AXI-S FIFO",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="axis_fifo")
		out = capsys.readouterr().out
		assert "axis_fifo" in out

	def test_matches_by_display_name(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:z:1.0",
			name="unrelated_name",
			display_name="Spectacular Wizard Core",
			description="Does nothing",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="spectacular")
		out = capsys.readouterr().out
		assert "Spectacular Wizard Core" in out

	def test_matches_by_name(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:unique_ip_name:1.0",
			name="unique_ip_name",
			display_name="Some Display Name",
			description="Some description",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="unique_ip_name")
		out = capsys.readouterr().out
		assert "unique_ip_name" in out

	def test_matches_by_description(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:z:1.0",
			name="z",
			display_name="IP Widget",
			description="Performs advanced flux capacitation",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="flux capacitation")
		out = capsys.readouterr().out
		assert "IP Widget" in out

	def test_search_is_case_insensitive(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:dma_engine:1.0",
			name="dma_engine",
			display_name="DMA Engine",
			description="Direct Memory Access",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="DMA")
		out = capsys.readouterr().out
		assert "DMA Engine" in out

	def test_no_match_returns_early_without_table(self, capsys):
		cfg = self._cfg_with_catalog([])
		cmd_search_core(cfg, query="zzz_no_match")
		out = capsys.readouterr().out
		# Table header should NOT appear when there are no results
		assert "VLNV" not in out

	# -- result table output -----------------------------------------------

	def test_prints_result_count(self, capsys):
		entries = [
			_make_catalog_entry(
				vlnv=f"x:y:ip_{i}:1.0", name=f"ip_{i}", display_name=f"IP {i}", description="Matching desc"
			)
			for i in range(3)
		]
		cfg = self._cfg_with_catalog(entries)
		cmd_search_core(cfg, query="matching desc")
		out = capsys.readouterr().out
		assert "3 result" in out

	def test_single_result_count_singular(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:one:1.0",
			name="one",
			display_name="One IP",
			description="The only one",
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="the only one")
		out = capsys.readouterr().out
		assert "1 result" in out

	def test_table_includes_vlnv_header(self, capsys):
		entry = _make_catalog_entry()
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="fifo")
		out = capsys.readouterr().out
		assert "VLNV" in out

	# -- flags -------------------------------------------------------------

	def test_board_dependent_flag_shown_in_output(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:board_ip:1.0",
			name="board_ip",
			display_name="Board IP",
			description="Board-specific IP",
			board_dependent=True,
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="board")
		out = capsys.readouterr().out
		assert "[board-dep]" in out

	def test_ipi_only_flag_shown_in_output(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:ipi_ip:1.0",
			name="ipi_ip",
			display_name="IPI IP",
			description="IPI only IP",
			ipi_only=True,
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="ipi")
		out = capsys.readouterr().out
		assert "[IPI-only]" in out

	def test_both_flags_shown_together(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:special:1.0",
			name="special",
			display_name="Special IP",
			description="Special IP with both flags",
			board_dependent=True,
			ipi_only=True,
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="special")
		out = capsys.readouterr().out
		assert "[board-dep]" in out
		assert "[IPI-only]" in out

	def test_description_shown_when_no_flags(self, capsys):
		entry = _make_catalog_entry(
			vlnv="x:y:normal:1.0",
			name="normal",
			display_name="Normal IP",
			description="Normal description text",
			board_dependent=False,
			ipi_only=False,
		)
		cfg = self._cfg_with_catalog([entry])
		cmd_search_core(cfg, query="normal")
		out = capsys.readouterr().out
		assert "Normal description text" in out

	# -- sorting -----------------------------------------------------------

	def test_results_sorted_by_vlnv(self, capsys):
		b = _make_catalog_entry(vlnv="z:y:b:1.0", name="b", display_name="B IP", description="b")
		a = _make_catalog_entry(vlnv="a:y:a:1.0", name="a", display_name="A IP", description="a")
		cfg = self._cfg_with_catalog([b, a])
		cmd_search_core(cfg, query="ip")
		out = capsys.readouterr().out
		assert out.index("a:y:a:1.0") < out.index("z:y:b:1.0")
