"""Shared fixtures and helpers for the xviv test suite."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig

# ---------------------------------------------------------------------------
# Core config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bare(tmp_path):
	"""XvivConfig with no FPGA, no Vivado — minimal valid state."""
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	return cfg


@pytest.fixture
def artix(tmp_path):
	"""XvivConfig with one xc7a100tcsg324-1 FPGA entry. No Vivado."""
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	return cfg


@pytest.fixture
def artix_vivado(tmp_path):
	"""artix fixture with add_vivado_cfg(path=None) so get_vivado() succeeds."""
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	return cfg


@pytest.fixture
def zynq(tmp_path):
	"""XvivConfig with xczu9eg-ffvb1156-2-e."""
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("zynq", fpga_part="xczu9eg-ffvb1156-2-e")
	return cfg


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def touch(tmp_path):
	"""Returns a factory that creates empty files and returns their abs path."""

	def _touch(relative_path: str) -> str:
		full = tmp_path / relative_path
		full.parent.mkdir(parents=True, exist_ok=True)
		full.touch()
		return str(full)

	return _touch


@pytest.fixture
def make_toml(tmp_path):
	"""Returns a factory that writes content to tmp_path/project.toml."""

	def _make(content: str) -> Path:
		p = tmp_path / "project.toml"
		p.write_text(content)
		return p

	return _make


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_run_job_list(monkeypatch):
	"""Patches xviv.utils.job.run_job_list to a no-op."""
	m = MagicMock(return_value=None)
	monkeypatch.setattr("xviv.utils.job.run_job_list", m)
	return m


@pytest.fixture
def mock_vivado_runner(monkeypatch):
	"""Patches VivadoRunner.run to a no-op."""
	from xviv.tools.vivado import VivadoRunner

	m = MagicMock(return_value=None)
	monkeypatch.setattr(VivadoRunner, "run", m)
	return m


@pytest.fixture
def mock_xsct_runner(monkeypatch):
	"""Patches XsctRunner.run to a no-op."""
	from xviv.tools.xsct import XsctRunner

	m = MagicMock(return_value=None)
	monkeypatch.setattr(XsctRunner, "run", m)
	return m


@pytest.fixture
def mock_verilator_runner(monkeypatch):
	"""Patches VerilatorRunner.run to a no-op."""
	from xviv.tools.verilator import VerilatorRunner

	m = MagicMock(return_value=None)
	monkeypatch.setattr(VerilatorRunner, "run", m)
	return m
