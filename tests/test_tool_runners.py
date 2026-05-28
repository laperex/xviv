import logging
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from xviv.utils.process import run_tool

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


def make_interactive_proc(returncode: int = 0) -> MagicMock:
	"""Mock returned by _run_interactive_pty."""
	proc = MagicMock()
	proc.returncode = returncode
	return proc


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------


class TestDryRun:
	def test_returns_none(self, tmp_path):
		result = run_tool(["echo", "hi"], cwd=str(tmp_path), dry_run=True, label="test")
		assert result is None

	def test_never_calls_subprocess(self, tmp_path):
		with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
			run_tool(["echo", "hi"], cwd=str(tmp_path), dry_run=True, label="test")
			mock_popen.assert_not_called()
			mock_run.assert_not_called()

	def test_still_not_creates_cwd(self, tmp_path):
		new_dir = tmp_path / "new" / "subdir"
		run_tool(["echo"], cwd=str(new_dir), dry_run=True, label="test")
		assert not new_dir.is_dir()


# ---------------------------------------------------------------------------
# cwd creation
# ---------------------------------------------------------------------------


class TestCwdCreation:
	def test_creates_nested_cwd(self, tmp_path):
		new_dir = str(tmp_path / "a" / "b" / "c")
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=new_dir, label="test")
		assert os.path.isdir(new_dir)

	def test_existing_cwd_is_fine(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=str(tmp_path), label="test")  # already exists


# ---------------------------------------------------------------------------
# popen mode
# ---------------------------------------------------------------------------


class TestPopenMode:
	def test_returns_pid(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 4242
		with patch("subprocess.Popen", return_value=mock_proc):
			pid = run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True, label="test")
		assert pid == 4242

	def test_does_not_wait(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc):
			run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True, label="test")
		mock_proc.wait.assert_not_called()

	def test_does_not_read_stdout(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc):
			run_tool(["sleep", "60"], cwd=str(tmp_path), popen=True, label="test")
		mock_proc.__enter__.assert_not_called()

	def test_passes_cwd(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 1
		with patch("subprocess.Popen", return_value=mock_proc) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path), popen=True, label="test")
		_, kwargs = mock_cls.call_args
		assert kwargs.get("cwd") == str(tmp_path)


# ---------------------------------------------------------------------------
# interactive mode  (uses _run_interactive_pty internally)
# ---------------------------------------------------------------------------

_PTY_FUNC = "xviv.utils.process._run_interactive_pty"


class TestInteractiveMode:
	def test_calls_run_interactive_pty(self, tmp_path):
		with patch(_PTY_FUNC, return_value=make_interactive_proc()) as mock_pty:
			run_tool(["vivado"], cwd=str(tmp_path), interactive=True, label="test")
		mock_pty.assert_called_once()

	def test_passes_cwd(self, tmp_path):
		with patch(_PTY_FUNC, return_value=make_interactive_proc()) as mock_pty:
			run_tool(["vivado"], cwd=str(tmp_path), interactive=True, label="test")
		assert mock_pty.call_args.kwargs.get("cwd") == str(tmp_path)

	def test_returns_zero_on_success(self, tmp_path):
		with patch(_PTY_FUNC, return_value=make_interactive_proc(returncode=0)):
			result = run_tool(["vivado"], cwd=str(tmp_path), interactive=True, label="test")
		assert result == 0

	def test_raises_on_nonzero(self, tmp_path):
		with patch(_PTY_FUNC, return_value=make_interactive_proc(returncode=3)):
			with pytest.raises(subprocess.CalledProcessError) as exc_info:
				run_tool(["vivado"], cwd=str(tmp_path), interactive=True, label="test")
		assert exc_info.value.returncode == 3


# ---------------------------------------------------------------------------
# streaming mode
# ---------------------------------------------------------------------------


class TestStreamingMode:
	def test_prints_output(self, tmp_path, capsys):
		popen_cm = make_popen_cm(["hello\n", "world\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["echo"], cwd=str(tmp_path), label="test")
		out = capsys.readouterr().out
		assert "hello" in out
		assert "world" in out

	def test_strips_newline_for_print(self, tmp_path, capsys):
		popen_cm = make_popen_cm(["line\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			with patch("xviv.utils.process.print_terminal_divider"):
				run_tool(["echo"], cwd=str(tmp_path), label="test")
		out = capsys.readouterr().out
		# "line" must appear; no double-blank-line from stray \n
		assert "line" in out
		assert "\n\n\n" not in out

	def test_returns_zero_on_success(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			result = run_tool(["echo"], cwd=str(tmp_path), label="test")
		assert result == 0

	def test_raises_on_nonzero(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=2)
		with patch("subprocess.Popen", return_value=popen_cm):
			with pytest.raises(subprocess.CalledProcessError) as exc_info:
				run_tool(["false"], cwd=str(tmp_path), label="test")
		assert exc_info.value.returncode == 2

	def test_passes_cwd(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path), label="test")
		_, kwargs = mock_cls.call_args
		assert kwargs["cwd"] == str(tmp_path)

	def test_stderr_merged_into_stdout(self, tmp_path):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm) as mock_cls:
			run_tool(["cmd"], cwd=str(tmp_path), label="test")
		_, kwargs = mock_cls.call_args
		assert kwargs["stderr"] == subprocess.STDOUT

	def test_logs_at_debug(self, tmp_path, caplog):
		popen_cm = make_popen_cm(["msg\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			with caplog.at_level(logging.DEBUG, logger="xviv.utils.process"):
				run_tool(["cmd"], cwd=str(tmp_path), label="test")
		assert any("msg" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# log_file_path
# ---------------------------------------------------------------------------


class TestLogPath:
	def test_writes_lines_to_file(self, tmp_path):
		log_path = str(tmp_path / "out.log")
		popen_cm = make_popen_cm(["line1\n", "line2\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_file_path=log_path, label="test")
		content = open(log_path).read()
		assert "line1\n" in content
		assert "line2\n" in content

	def test_creates_parent_directories_via_log_dir(self, tmp_path):
		log_dir = str(tmp_path / "a" / "b")
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_dir=log_dir, label="test")
		assert os.path.isdir(log_dir)

	def test_file_closed_after_success(self, tmp_path):
		log_path = str(tmp_path / "out.log")
		popen_cm = make_popen_cm(["x\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_file_path=log_path, label="test")
		with open(log_path) as f:
			assert f.read()

	def test_file_closed_after_error(self, tmp_path):
		log_path = str(tmp_path / "out.log")
		popen_cm = make_popen_cm([], returncode=1)
		with patch("subprocess.Popen", return_value=popen_cm):
			with pytest.raises(subprocess.CalledProcessError):
				run_tool(["cmd"], cwd=str(tmp_path), log_file_path=log_path, label="test")
		with open(log_path) as f:
			f.read()  # would raise if handle leaked

	def test_not_written_when_none(self, tmp_path):
		popen_cm = make_popen_cm(["data\n"], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			run_tool(["cmd"], cwd=str(tmp_path), log_file_path=None, label="test")
		assert list(tmp_path.glob("*.log")) == []


# ---------------------------------------------------------------------------
# label-based logging  (replaces old "custom logger" API)
# ---------------------------------------------------------------------------


class TestLabelLogging:
	def test_label_creates_child_logger(self, tmp_path, caplog):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			with caplog.at_level(logging.DEBUG):
				run_tool(["cmd"], cwd=str(tmp_path), label="my.job")
		assert any("my.job" in r.name for r in caplog.records)

	def test_dry_run_logs_command_at_info(self, tmp_path, caplog):
		with caplog.at_level(logging.INFO):
			run_tool(["echo", "hello"], cwd=str(tmp_path), dry_run=True, label="test")
		assert any("echo" in r.message for r in caplog.records)

	def test_parallel_logs_command_at_info(self, tmp_path, caplog):
		popen_cm = make_popen_cm([], returncode=0)
		with patch("subprocess.Popen", return_value=popen_cm):
			with caplog.at_level(logging.INFO):
				run_tool(["cmd"], cwd=str(tmp_path), label="test", parallel=True)
		assert any("cmd" in r.message for r in caplog.records)
