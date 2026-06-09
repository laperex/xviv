"""Tests for tools/vivado.py - ToolRunner hierarchy, VivadoRunner, XilinxToolRunner.classify."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from xviv.tools.vivado import (
	VivadoRunner,
	XilinxToolRunner,
)
from xviv.utils.stream import OutputLine


def _make_cfg(tmp_path):
	"""Build a minimal XvivConfig with vivado configured."""
	from xviv.config.project import XvivConfig

	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	cfg.add_vivado_cfg(path=None)
	return cfg


@pytest.mark.unit
class TestClassify:
	"""XilinxToolRunner.classify maps log prefixes to correct levels."""

	def test_error_prefix_maps_to_error(self):
		line = XilinxToolRunner.classify("ERROR: something went wrong")
		assert line.level == logging.ERROR

	def test_warning_prefix_maps_to_warning(self):
		line = XilinxToolRunner.classify("WARNING: check your settings")
		assert line.level == logging.WARNING

	def test_info_prefix_maps_to_info(self):
		line = XilinxToolRunner.classify("INFO: starting synthesis")
		assert line.level == logging.INFO

	def test_critical_warning_maps_to_critical(self):
		line = XilinxToolRunner.classify("CRITICAL WARNING: power issue")
		assert line.level == logging.CRITICAL

	def test_unknown_prefix_maps_to_debug(self):
		line = XilinxToolRunner.classify("some random output")
		assert line.level == logging.DEBUG

	def test_text_is_stripped_of_prefix(self):
		line = XilinxToolRunner.classify("ERROR: the message")
		assert "the message" in line.text
		assert "ERROR:" not in line.text

	def test_raw_is_preserved(self):
		raw = "WARNING: original raw text"
		line = XilinxToolRunner.classify(raw)
		assert line.raw == raw


@pytest.mark.unit
class TestMakePairs:
	def test_make_pairs_calls_tcl_fn_for_each_name(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)

		called_names = []

		def tcl_fn(name: str) -> str:
			called_names.append(name)
			return f"# TCL for {name}\n"

		runner.make_pairs(
			["alpha", "beta", "gamma"],
			tcl_fn,
			label_prefix="synth",
			log_prefix="synth",
		)
		assert called_names == ["alpha", "beta", "gamma"]

	def test_make_pairs_empty_names_empty_pairs(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.make_pairs([], lambda n: "", label_prefix="x", log_prefix="x")
		assert runner._pairs == []

	def test_make_pairs_returns_self_for_chaining(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		result = runner.make_pairs(["a"], lambda n: "", label_prefix="x", log_prefix="x")
		assert result is runner


@pytest.mark.unit
class TestVivadoRunnerJob:
	def test_job_writes_tcl_and_builds_cmd(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL content", label="test_job", log_file=str(tmp_path / "out.log"))
		assert len(runner._pairs) == 1
		_, job = runner._pairs[0]
		assert "vivado" in job.cmd[0].lower() or job.cmd[0] == "vivado"

	def test_job_label_matches(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="my_label", log_file=str(tmp_path / "out.log"))
		_, job = runner._pairs[0]
		assert job.label == "my_label"

	def test_job_cwd_is_work_dir(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="j", log_file=str(tmp_path / "out.log"))
		_, job = runner._pairs[0]
		assert job.cwd == cfg.work_dir

	def test_job_none_tcl_does_not_add_pair(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job(None, label="j", log_file=str(tmp_path / "out.log"))
		assert runner._pairs == []

	def test_job_cmd_contains_mode_and_source(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="j", log_file=str(tmp_path / "out.log"))
		_, job = runner._pairs[0]
		cmd_str = " ".join(job.cmd)
		assert "-mode" in cmd_str
		assert "-source" in cmd_str

	def test_job_classifier_is_xilinx_classify(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="j", log_file=str(tmp_path / "out.log"))
		_, job = runner._pairs[0]
		# classifier should return an OutputLine when called
		result = job.classifier("ERROR: test")
		assert isinstance(result, OutputLine)
		assert result.level == logging.ERROR


@pytest.mark.unit
class TestRunCallsJobList:
	def test_run_calls_run_job_list(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="j", log_file=str(tmp_path / "out.log"))
		with patch("xviv.tools.vivado.run_job_list") as mock_rjl:
			runner.run()
		mock_rjl.assert_called_once()

	def test_run_passes_job_objects(self, tmp_path):
		cfg = _make_cfg(tmp_path)
		runner = VivadoRunner(cfg)
		runner.job("# TCL", label="j1", log_file=str(tmp_path / "j1.log"))
		runner.job("# TCL2", label="j2", log_file=str(tmp_path / "j2.log"))
		captured = {}
		with patch("xviv.tools.vivado.run_job_list", side_effect=lambda jobs, **kw: captured.update({"jobs": jobs})):
			runner.run()
		assert len(captured["jobs"]) == 2


@pytest.mark.unit
class TestJobsCtx:
	def test_yields_only_job_objects(self, tmp_path):
		from pathlib import Path

		from tests.helpers import make_job

		pairs = [(Path("/tmp/tcl.tcl"), make_job(label="j1")), (Path("/tmp/tcl2.tcl"), make_job(label="j2"))]
		with VivadoRunner.jobs_ctx(pairs) as jobs:
			assert len(jobs) == 2
			for job in jobs:
				assert hasattr(job, "label")

	def test_none_pairs_are_filtered(self, tmp_path):
		from pathlib import Path

		from tests.helpers import make_job

		pairs = [None, (Path("/tmp/t.tcl"), make_job(label="j1")), None]
		with VivadoRunner.jobs_ctx(pairs) as jobs:
			assert len(jobs) == 1
