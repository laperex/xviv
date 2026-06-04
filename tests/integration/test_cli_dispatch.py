"""Integration: CLI args → cmd_* dispatch; params dataclass contracts."""

from __future__ import annotations

import argparse
import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from xviv.config.params import (
	EditParams,
	GenerateParams,
	IpCreateParams,
	OpenParams,
	ProcessorParams,
	SimulateParams,
	SynthParams,
)


@pytest.mark.integration
class TestParams:
	"""Verify all params dataclasses have the documented field defaults."""

	def test_simulate_params_is_dataclass(self):
		assert dataclasses.is_dataclass(SimulateParams)

	def test_simulate_params_uvm_name_default_none(self):
		p = SimulateParams()
		assert p.uvm_name is None

	def test_simulate_params_run_default_all(self):
		p = SimulateParams()
		assert p.run == "all"

	def test_simulate_params_mode_default_default(self):
		p = SimulateParams()
		assert p.mode == "default"

	def test_synth_params_is_dataclass(self):
		assert dataclasses.is_dataclass(SynthParams)

	def test_synth_params_resume_default_none(self):
		p = SynthParams()
		assert p.resume is None

	def test_synth_params_parallel_subcore_default_false(self):
		p = SynthParams()
		assert p.parallel_subcore_synth is False

	def test_edit_params_nogui_default_false(self):
		p = EditParams()
		assert p.nogui is False

	def test_open_params_nogui_default_false(self):
		p = OpenParams()
		assert p.nogui is False

	def test_generate_params_force_default_false(self):
		p = GenerateParams()
		assert p.force is False

	def test_generate_params_reset_default_false(self):
		p = GenerateParams()
		assert p.reset is False

	def test_processor_params_reset_default_false(self):
		p = ProcessorParams()
		assert p.reset is False

	def test_processor_params_status_default_false(self):
		p = ProcessorParams()
		assert p.status is False

	def test_ip_create_params_regenerate_default_false(self):
		p = IpCreateParams()
		assert p.regenerate is False


@pytest.mark.integration
class TestCommandDispatch:
	"""Test that Command.run routes to the correct cmd_* function with correct kwargs."""

	def _make_cfg(self, tmp_path):
		"""Minimal config for dispatch tests."""

		with patch("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock()):
			from xviv.config.project import XvivConfig

			pf = tmp_path / "project.toml"
			pf.write_text("")
			cfg = XvivConfig(str(pf))
			cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
			cfg.add_vivado_cfg(path=None)
		return cfg

	def test_synth_command_passes_params_as_synth_params(self, tmp_path):
		"""CRITICAL: SynthCommand must pass params=SynthParams(...) not flat kwargs."""
		from xviv.cli.commands import SynthCommand

		cfg = self._make_cfg(tmp_path)
		args = argparse.Namespace(
			dry_run=False,
			check=False,
			design="my_design",
			bd=None,
			core=None,
			usr_access_type="git",
			resume=None,
			parallel=False,
		)
		captured = {}
		with patch("xviv.cli.commands.cmd_synth", side_effect=lambda *a, **kw: captured.update(kw)):
			SynthCommand().run(cfg, args)

		assert "params" in captured
		p = captured["params"]
		assert isinstance(p, SynthParams)

	def test_synth_command_resume_inside_params(self, tmp_path):
		from xviv.cli.commands import SynthCommand

		cfg = self._make_cfg(tmp_path)
		args = argparse.Namespace(
			dry_run=False,
			check=False,
			design="my_design",
			bd=None,
			core=None,
			usr_access_type="git",
			resume="synth",
			parallel=False,
		)
		captured = {}
		with patch("xviv.cli.commands.cmd_synth", side_effect=lambda *a, **kw: captured.update(kw)):
			SynthCommand().run(cfg, args)

		assert captured["params"].resume == "synth"

	def test_formal_command_dispatches_cmd_formal(self, tmp_path):
		from xviv.cli.commands import FormalCommand

		cfg = self._make_cfg(tmp_path)
		args = argparse.Namespace(dry_run=False, check=False, target=None)
		with patch("xviv.cli.commands.cmd_formal") as mock_fn:
			FormalCommand().run(cfg, args)
		mock_fn.assert_called_once()

	def test_simulate_command_passes_mode_and_run(self, tmp_path):
		from xviv.cli.commands import SimulateCommand

		cfg = self._make_cfg(tmp_path)
		args = argparse.Namespace(
			dry_run=False,
			check=False,
			target="my_sim",  # --target maps to args.target
			uvm=None,  # --uvm maps to args.uvm
			mode="post_synth_functional",
			run="100ns",
		)
		captured = {}
		with patch("xviv.cli.commands.cmd_simulate", side_effect=lambda *a, **kw: captured.update(kw)):
			SimulateCommand().run(cfg, args)

		assert "params" in captured
		p = captured["params"]
		assert isinstance(p, SimulateParams)
		assert p.mode == "post_synth_functional"
		assert p.run == "100ns"

	def test_dry_run_propagates_to_cfg(self, tmp_path):
		from xviv.cli.commands import FormalCommand

		cfg = self._make_cfg(tmp_path)
		args = argparse.Namespace(dry_run=True, check=False, target=None)
		with patch("xviv.cli.commands.cmd_formal"):
			FormalCommand().run(cfg, args)
		assert cfg.dry_run is True
