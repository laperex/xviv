"""Tests for ConfigTclCommands project-level TCL - _require_project, board_repo, ip_repo."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils.error import InMemoryProjectAlreadyExistsError


@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock())


def _cfg(tmp_path, *, board_repo=None, ip_repo=None):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	kwargs = {}
	if board_repo:
		kwargs["board_repo"] = board_repo
	if ip_repo:
		kwargs["ip_repo"] = ip_repo
	cfg = XvivConfig(str(pf), **kwargs)
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	return cfg


@pytest.mark.unit
class TestRequireProject:
	def test_creates_in_memory_project(self, tmp_path):
		cfg = _cfg(tmp_path)
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert tcl is not None
		assert "create_project" in tcl
		assert "-in_memory" in tcl

	def test_emits_set_part_with_fpga(self, tmp_path):
		cfg = _cfg(tmp_path)
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert "xc7a100tcsg324-1" in tcl

	def test_calling_twice_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		with pytest.raises(InMemoryProjectAlreadyExistsError):
			tcl_obj._require_project()

	def test_exists_ok_returns_false_without_raising(self, tmp_path):
		cfg = _cfg(tmp_path)
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		result = tcl_obj._require_project(exists_ok=True)
		assert result is False


@pytest.mark.unit
class TestBoardRepo:
	def test_board_repo_set_param_when_nonempty(self, tmp_path):
		repo = tmp_path / "boards"
		repo.mkdir()
		cfg = _cfg(tmp_path, board_repo=[str(repo)])
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert "board.repoPaths" in tcl

	def test_no_board_repo_param_when_empty(self, tmp_path):
		cfg = _cfg(tmp_path)  # no board_repo
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert "board.repoPaths" not in tcl


@pytest.mark.unit
class TestIpRepo:
	def test_ip_repo_set_property_when_set(self, tmp_path):
		repo = tmp_path / "my_ips"
		repo.mkdir()
		cfg = _cfg(tmp_path, ip_repo=[str(repo)])
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert "ip_repo_paths" in tcl

	def test_ip_repo_paths_contains_repo_path(self, tmp_path):
		repo = tmp_path / "my_ips"
		repo.mkdir()
		cfg = _cfg(tmp_path, ip_repo=[str(repo)])
		tcl_obj = ConfigTclCommands(cfg)
		tcl_obj._require_project()
		tcl = tcl_obj.build()
		assert str(repo) in tcl
