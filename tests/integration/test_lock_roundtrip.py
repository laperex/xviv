"""Integration: load_config -> generate_lock -> re-parse cycle."""

from __future__ import annotations

import tomllib
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
class TestLockValidity:
	def test_lock_is_valid_toml(self, tmp_path):
		import shutil

		shutil.copy(FIXTURES / "minimal.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		cfg.generate_lock()
		lock_text = (tmp_path / "project.lock").read_text()
		parsed = tomllib.loads(lock_text)
		assert isinstance(parsed, dict)

	def test_none_values_absent(self, tmp_path):
		import shutil

		shutil.copy(FIXTURES / "design_synth.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		cfg.generate_lock()
		lock_text = (tmp_path / "project.lock").read_text()
		parsed = tomllib.loads(lock_text)

		def _check(d):
			if isinstance(d, dict):
				for v in d.values():
					assert v is not None
					_check(v)
			elif isinstance(d, list):
				for item in d:
					_check(item)

		_check(parsed)

	def test_paths_in_lock_are_relative(self, tmp_path):
		import os
		import shutil

		shutil.copy(FIXTURES / "minimal.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		project = parsed.get("project", {})
		for key in ["work_dir", "log_file"]:
			if key in project:
				assert not os.path.isabs(project[key]), f"{key} should be relative"


@pytest.mark.integration
class TestLockContent:
	def test_fpga_names_match_config(self, tmp_path):
		import shutil

		shutil.copy(FIXTURES / "multi_fpga.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		fpga_names = {f["name"] for f in parsed.get("fpga", [])}
		assert "artix" in fpga_names
		assert "zynq" in fpga_names

	def test_simulation_names_match(self, tmp_path):
		import shutil

		shutil.copy(FIXTURES / "simulation_xsim.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		sim_names = {s["name"] for s in parsed.get("simulation", [])}
		assert "tb_default" in sim_names


@pytest.mark.integration
class TestLockIdempotency:
	def test_two_calls_identical_bytes(self, tmp_path):
		import shutil

		shutil.copy(FIXTURES / "minimal.toml", tmp_path / "project.toml")
		cfg = _load(str(tmp_path / "project.toml"))
		lock1 = tmp_path / "a.lock"
		lock2 = tmp_path / "b.lock"
		cfg.generate_lock(str(lock1))
		cfg.generate_lock(str(lock2))
		assert lock1.read_bytes() == lock2.read_bytes()
