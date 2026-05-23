import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from xviv.utils.process import run_tool

# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vivado_cfg():
	vivado = MagicMock()
	vivado.path = "/opt/xilinx/vivado"
	vivado.dry_run = False
	vivado.mode = "batch"

	cfg = MagicMock()
	cfg.get_vivado.return_value = vivado
	cfg.work_dir = "/work"
	return cfg


@pytest.fixture
def vivado_cfg_dry(vivado_cfg):
	vivado_cfg.get_vivado().dry_run = True
	return vivado_cfg


@pytest.fixture
def vitis_cfg():
	vitis = MagicMock()
	vitis.path = "/opt/xilinx/vitis"
	vitis.dry_run = False

	cfg = MagicMock()
	cfg.get_vitis.return_value = vitis
	return cfg


@pytest.fixture
def vitis_cfg_dry(vitis_cfg):
	vitis_cfg.get_vitis().dry_run = True
	return vitis_cfg


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def make_popen_cm(lines: list[str], returncode: int = 0) -> MagicMock:
	"""Context-manager-compatible Popen mock for the streaming path."""
	proc = MagicMock()
	proc.stdout = iter(lines)
	proc.returncode = returncode
	proc.wait.return_value = None

	popen = MagicMock()
	popen.__enter__ = MagicMock(return_value=proc)
	popen.__exit__ = MagicMock(return_value=False)
	return popen


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------


class TestDryRun:
	def test_returns_none(self, tmp_path):
		result = run_tool(["echo", "hi"], cwd=str(tmp_path), dry_run=True)
		assert result is None

	def test_never_calls_subprocess(self, tmp_path):
		with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
			run_tool(["echo", "hi"], cwd=str(tmp_path), dry_run=True)
			mock_popen.assert_not_called()
			mock_run.assert_not_called()

	def test_still_creates_cwd(self, tmp_path):
		new_dir = tmp_path / "new" / "subdir"
		run_tool(["echo"], cwd=str(new_dir), dry_run=True)
		assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# cwd creation
# ---------------------------------------------------------------------------


class TestCwdCreation:
	def test_creates_nested_cwd(self, tmp_path):
		new_dir = str(tmp_path / "a" / "b" / "c")
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=new_dir)
		assert os.path.isdir(new_dir)

	def test_existing_cwd_is_fine(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=str(tmp_path))  # already exists


# ---------------------------------------------------------------------------
# popen mode
# ---------------------------------------------------------------------------


class TestPopenMode:
	def test_returns_pid(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 4242
		with patch("subprocess.Popen", return_value=mock_proc):
			pid = run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True)
		assert pid == 4242

	def test_does_not_wait(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc):
			run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True)
		mock_proc.wait.assert_not_called()

	def test_does_not_read_stdout(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc):
			run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True)
		mock_proc.stdout  # accessing is fine; reading is not
		mock_proc.__enter__.assert_not_called()

	def test_passes_cwd(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path), popen=True)
		_, kwargs = mock_cls.call_args
		assert kwargs.get("cwd") == str(tmp_path)


# ---------------------------------------------------------------------------
# interactive mode
# ---------------------------------------------------------------------------


class TestInteractiveMode:
	def test_uses_subprocess_run(self, tmp_path):
		with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
			run_tool(["vivado"], cwd=str(tmp_path), interactive=True)
		mock_run.assert_called_once()
		assert mock_run.call_args[0][0] == ["vivado"]

	def test_passes_cwd(self, tmp_path):
		with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
			run_tool(["vivado"], cwd=str(tmp_path), interactive=True)
		assert mock_run.call_args[1].get("cwd") == str(tmp_path)

	def test_returns_none_on_success(self, tmp_path):
		with patch("subprocess.run", return_value=MagicMock(returncode=0)):
			result = run_tool(["vivado"], cwd=str(tmp_path), interactive=True)
		assert result is None

	def test_raises_on_nonzero(self, tmp_path):
		with patch("subprocess.run", return_value=MagicMock(returncode=3)):
			with pytest.raises(subprocess.CalledProcessError) as exc_info:
				run_tool(["vivado"], cwd=str(tmp_path), interactive=True)
		assert exc_info.value.returncode == 3


# ---------------------------------------------------------------------------
# streaming mode
# ---------------------------------------------------------------------------


class TestStreamingMode:
	def test_prints_output(self, tmp_path, capsys):
		popen_cm = make_popen_cm(["hello\n", "world\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=str(tmp_path))
		out = capsys.readouterr().out
		assert "hello" in out
		assert "world" in out

	def test_strips_newline_for_print(self, tmp_path, capsys):
		popen_cm = make_popen_cm(["line\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=str(tmp_path))
		out = capsys.readouterr().out
		# printed as stripped then print() adds its own newline - no double blank line
		assert out == "line\n"

	def test_returns_none_on_success(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			result = run_tool(["echo"], cwd=str(tmp_path))
		assert result is None

	def test_raises_on_nonzero(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=2)
		with patch("subprocess.Popen", return_value=popen_cm):
			with pytest.raises(subprocess.CalledProcessError) as exc_info:
				run_tool(["false"], cwd=str(tmp_path))
		assert exc_info.value.returncode == 2

	def test_passes_cwd(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path))
		_, kwargs = mock_cls.call_args
		assert kwargs["cwd"] == str(tmp_path)

	def test_stderr_merged_into_stdout(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path))
		_, kwargs = mock_cls.call_args
		assert kwargs["stderr"] == subprocess.STDOUT

	def test_logs_at_debug(self, tmp_path):
		popen_cm = make_popen_cm(["msg\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			with patch("xviv.utils.process.logger") as mock_log:
				run_tool(["cmd"], cwd=str(tmp_path))
		debug_calls = [str(c) for c in mock_log.debug.call_args_list]
		assert any("msg" in c for c in debug_calls)


# ---------------------------------------------------------------------------
# log_path
# ---------------------------------------------------------------------------


class TestLogPath:
	def test_writes_lines_to_file(self, tmp_path):
		log_path = tmp_path / "out.log"
		popen_cm = make_popen_cm(["line1\n", "line2\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_path=log_path)
		content = log_path.read_text()
		assert "line1\n" in content
		assert "line2\n" in content

	def test_creates_parent_directories(self, tmp_path):
		log_path = tmp_path / "a" / "b" / "out.log"
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_path=log_path)
		assert log_path.parent.is_dir()

	def test_file_closed_after_success(self, tmp_path):
		log_path = tmp_path / "out.log"
		popen_cm = make_popen_cm(["x\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_path=log_path)
		# File is closed if we can open it exclusively
		with open(log_path) as f:
			assert f.read()

	def test_file_closed_after_error(self, tmp_path):
		log_path = tmp_path / "out.log"
		popen_cm = make_popen_cm([], returncode=1)
		with patch("subprocess.Popen", return_value=popen_cm):
			with pytest.raises(subprocess.CalledProcessError):
				run_tool(["cmd"], cwd=str(tmp_path), log_path=log_path)
		with open(log_path) as f:
			f.read()  # would raise if handle leaked

	def test_not_written_when_none(self, tmp_path):
		popen_cm = make_popen_cm(["data\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_path=None)
		# No log files created in tmp_path
		assert list(tmp_path.glob("*.log")) == []


# ---------------------------------------------------------------------------
# custom logger
# ---------------------------------------------------------------------------


class TestCustomLogger:
	def test_uses_provided_logger(self, tmp_path):
		custom_log = MagicMock()
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log=custom_log)
		custom_log.info.assert_called()

	def test_falls_back_to_module_logger_when_none(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("xviv.utils.process.logger") as mock_log:
			with patch("subprocess.Popen", return_value=popen_cm):
				run_tool(["cmd"], cwd=str(tmp_path), log=None)
		mock_log.info.assert_called()
