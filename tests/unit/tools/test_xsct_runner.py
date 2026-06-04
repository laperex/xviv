"""Tests for tools/xsct.py — XsctRunner.job construction."""

from __future__ import annotations

import pytest

from xviv.tools.xsct import XsctRunner


def _make_cfg(tmp_path):
	from xviv.config.project import XvivConfig

	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("zynq", fpga_part="xc7z020clg400-1")
	cfg.add_vivado_cfg(path=None)
	cfg.add_vitis_cfg(path=None)
	return cfg


@pytest.mark.unit
class TestXsctRunnerJob:
	def test_job_with_tcl_returns_path_and_job_tuple(self, tmp_path):
		cfg = _make_cfg(tmp_path)

		_result = (
			XsctRunner(cfg)
			.job(
				tcl="puts hello",
				label="xsct_test",
				log_file=str(tmp_path / "out.log"),
			)
			._pairs[-1]
		)
		assert _result is not None
		path, job = _result
		assert path is not None
		assert job is not None

	def test_job_cmd_contains_xsct(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		_, job = runner.job(
			tcl="puts hello",
			label="j",
			log_file=str(tmp_path / "out.log"),
		)._pairs[-1]
		assert "xsct" in job.cmd[0].lower() or job.cmd[0] == "xsct"

	def test_job_cmd_contains_tcl_path(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		path, job = runner.job(
			tcl="puts hello",
			label="j",
			log_file=str(tmp_path / "out.log"),
		)._pairs[-1]
		assert str(path) in job.cmd

	def test_job_cwd_is_target_dir(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		cfg.work_dir = str(tmp_path / "target")
		import os

		os.makedirs(cfg.work_dir, exist_ok=True)
		_, job = runner.job(
			tcl="puts hello",
			label="j",
			log_file=str(tmp_path / "out.log"),
		)._pairs[-1]
		assert job.cwd == cfg.work_dir

	def test_job_detach_false_by_default(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		_, job = runner.job(
			tcl="puts hello",
			label="j",
			log_file=str(tmp_path / "out.log"),
		)._pairs[-1]
		assert job.detach is False

	def test_job_popen_true_sets_detach(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		_, job = runner.job(
			tcl="puts hello",
			label="j",
			log_file=str(tmp_path / "out.log"),
			popen=True,
		)._pairs[-1]
		assert job.detach is True


@pytest.mark.unit
class TestXsctRunnerNoneTcl:
	def test_none_tcl_returns_none(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = XsctRunner(cfg)
		runner.job(
			tcl=None,
			label="j",
			log_file=str(tmp_path / "out.log"),
		)

		assert not runner._pairs
