"""Tests for tools/verilator.py — VerilatorRunner.compile_job, sim_job."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_cfg(tmp_path):
	from xviv.config.project import XvivConfig

	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	return cfg


@pytest.mark.unit
class TestCompileJob:
	def test_compile_job_returns_self_for_chaining(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="compile",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
				# fileset=[str(sv_file)],
			)

		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")

		result = runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		assert result is runner

	def test_compile_job_adds_to_pairs(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="compile",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
			)
		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")
		runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		assert len(runner._pairs) == 1

	def test_compile_job_cmd_contains_verilator(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="compile",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
			)
		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")
		runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		_, job = runner._pairs[0]
		assert "verilator" in job.cmd[0]


@pytest.mark.unit
class TestSimJob:
	def test_sim_job_appends_to_pairs(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		cfg.dry_run = True  # bypass binary-exists check in sim_job
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="compile",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
			)
		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")
		runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		runner.sim_job()
		assert len(runner._pairs) == 2

	def test_sim_job_cmd_references_binary(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		cfg.dry_run = True
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="compile",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
			)
		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")
		runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		runner.sim_job()
		_, job = runner._pairs[1]
		# sim job should reference the compiled binary path
		assert runner.binary in job.cmd[0] or any(runner.binary in c for c in job.cmd)


@pytest.mark.unit
class TestRunCallsJobList:
	def test_run_calls_run_job_list(self, tmp_path):
		from xviv.tools.verilator import VerilatorRunner

		cfg = _make_cfg(tmp_path)
		with patch("xviv.tools.verilator.find_verilator_bin", return_value="verilator"):
			runner = VerilatorRunner(cfg).configure(
				str(tmp_path),
				label="c",
				compile_log_file=str(tmp_path / "compile.log"),
				sim_log_file=str(tmp_path / "sim.log"),
			)
		sv_file = tmp_path / "top.sv"
		sv_file.write_text("module top; endmodule")
		runner.compile_job(
			top="top",
			fileset=[str(sv_file)],
		)
		# Patch run_job_list in the vivado module namespace (where ToolRunner._run_internal lives)
		with patch("xviv.tools.vivado.run_job_list") as mock_rjl:
			runner.run()
		mock_rjl.assert_called_once()
