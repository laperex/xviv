"""Tests for XvivConfig.generate_lock - validity, paths, idempotency."""

from __future__ import annotations

import os
import tomllib
from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig


@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock())


def _cfg(tmp_path, *, fpga_part="xc7a100tcsg324-1"):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part=fpga_part)
	cfg.add_vivado_cfg(path=None)
	return cfg


@pytest.mark.unit
class TestGenerateLock:
	def test_writes_lock_file_at_base_dir(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		lock_path = tmp_path / "project.lock"
		assert lock_path.exists()

	def test_lock_is_valid_toml(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		content = (tmp_path / "project.lock").read_text()
		parsed = tomllib.loads(content)
		assert isinstance(parsed, dict)

	def test_none_values_not_in_lock(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		content = (tmp_path / "project.lock").read_text()
		assert "null" not in content.lower()
		# None in TOML means no key - not "null" literal
		parsed = tomllib.loads(content)

		def _check_no_none(d):
			if isinstance(d, dict):
				for v in d.values():
					assert v is not None, "None value found in lock"
					_check_no_none(v)
			elif isinstance(d, list):
				for item in d:
					_check_no_none(item)

		_check_no_none(parsed)

	def test_fpga_section_present(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		assert "fpga" in parsed

	def test_idempotent_two_writes_identical(self, tmp_path):
		cfg = _cfg(tmp_path)
		lock1 = tmp_path / "project.lock"
		lock2 = tmp_path / "project2.lock"
		cfg.generate_lock(str(lock1))
		cfg.generate_lock(str(lock2))
		assert lock1.read_bytes() == lock2.read_bytes()

	def test_paths_in_lock_are_relative(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		content = (tmp_path / "project.lock").read_text()
		parsed = tomllib.loads(content)
		# work_dir in project section should be relative
		project = parsed.get("project", {})
		if "work_dir" in project:
			assert not os.path.isabs(project["work_dir"])

	def test_custom_lock_file_path(self, tmp_path):
		cfg = _cfg(tmp_path)
		custom = tmp_path / "custom.lock"
		cfg.generate_lock(str(custom))
		assert custom.exists()


@pytest.mark.unit
class TestLockContent:
	def test_fpga_name_in_lock(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		fpga_list = parsed.get("fpga", [])
		names = [f.get("name") for f in fpga_list]
		assert "artix" in names

	def test_design_appears_in_lock(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("module top; endmodule")
		cfg.add_design_cfg("my_design", sources=[str(f)])
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		design_list = parsed.get("design", [])
		names = [d.get("name") for d in design_list]
		assert "my_design" in names

	def test_simulation_appears_in_lock(self, tmp_path):
		cfg = _cfg(tmp_path)
		cfg.add_sim_cfg("my_sim", top="tb_top", backend="xsim", sources=[])
		cfg.generate_lock()
		parsed = tomllib.loads((tmp_path / "project.lock").read_text())
		sims = parsed.get("simulation", [])
		assert any(s.get("name") == "my_sim" for s in sims)
