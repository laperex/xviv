"""Tests for xviv.utils.stream - OutputLine, identity_classifier, stream_pipe, stream_popen."""

from __future__ import annotations

import logging
from dataclasses import fields
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

import pytest

from xviv.utils.stream import OutputLine, identity_classifier, stream_pipe, stream_popen, stream_pty


@pytest.mark.unit
class TestOutputLine:
	def test_is_dataclass_with_three_fields(self):
		field_names = {f.name for f in fields(OutputLine)}
		assert "text" in field_names
		assert "level" in field_names
		assert "raw" in field_names

	def test_construction(self):
		line = OutputLine(text="hello", level=logging.DEBUG, raw="hello")
		assert line.text == "hello"
		assert line.level == logging.DEBUG
		assert line.raw == "hello"


@pytest.mark.unit
class TestIdentityClassifier:
	def test_level_is_debug(self):
		line = identity_classifier("some raw output")
		assert line.level == logging.DEBUG

	def test_text_equals_raw(self):
		raw = "some raw output"
		line = identity_classifier(raw)
		assert line.text == raw
		assert line.raw == raw


@pytest.mark.unit
class TestStreamPipe:
	def _make_proc(self, lines: list[str], returncode: int = 0):
		"""Build a fake Popen context manager."""
		proc = MagicMock()
		proc.stdout.__iter__ = MagicMock(return_value=iter(lines))
		proc.returncode = returncode
		proc.__enter__ = MagicMock(return_value=proc)
		proc.__exit__ = MagicMock(return_value=False)
		return proc

	def test_yields_one_line_per_output_line(self, tmp_path):
		lines = ["line one\n", "line two\n", "line three\n"]
		proc = self._make_proc(lines, returncode=0)
		with patch("subprocess.Popen", return_value=proc):
			result = list(stream_pipe(("echo",), cwd=str(tmp_path), classifier=identity_classifier))
		assert len(result) == 3
		assert result[0].text == "line one"
		assert result[1].text == "line two"

	def test_strips_trailing_newline(self, tmp_path):
		proc = self._make_proc(["hello\n"], returncode=0)
		with patch("subprocess.Popen", return_value=proc):
			result = list(stream_pipe(("echo",), cwd=str(tmp_path), classifier=identity_classifier))
		assert result[0].text == "hello"

	def test_nonzero_returncode_raises_called_process_error(self, tmp_path):
		proc = self._make_proc([], returncode=1)
		with patch("subprocess.Popen", return_value=proc):
			with pytest.raises(CalledProcessError):
				list(stream_pipe(("false",), cwd=str(tmp_path), classifier=identity_classifier))

	def test_env_passed_to_popen(self, tmp_path):
		proc = self._make_proc([], returncode=0)
		env = {"MY_VAR": "hello"}
		with patch("subprocess.Popen", return_value=proc) as mock_popen:
			list(stream_pipe(("echo",), cwd=str(tmp_path), env=env, classifier=identity_classifier))
		call_kwargs = mock_popen.call_args
		assert call_kwargs.kwargs.get("env") == env or (len(call_kwargs.args) > 1 and call_kwargs.args[1].get("env") == env)

	def test_classifier_applied_to_each_line(self, tmp_path):
		def upper_classifier(raw: str) -> OutputLine:
			return OutputLine(text=raw.upper(), level=logging.INFO, raw=raw)

		proc = self._make_proc(["hello\n"], returncode=0)
		with patch("subprocess.Popen", return_value=proc):
			result = list(stream_pipe(("echo",), cwd=str(tmp_path), classifier=upper_classifier))
		assert result[0].text == "HELLO"
		assert result[0].level == logging.INFO


@pytest.mark.unit
class TestStreamPopen:
	def test_returns_integer_pid(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 12345
		with patch("subprocess.Popen", return_value=mock_proc):
			pid = stream_popen(("sleep", "1"), cwd=str(tmp_path))
		assert isinstance(pid, int)
		assert pid == 12345

	def test_does_not_wait(self, tmp_path):
		mock_proc = MagicMock()
		mock_proc.pid = 99
		with patch("subprocess.Popen", return_value=mock_proc):
			stream_popen(("sleep", "100"), cwd=str(tmp_path))
		# wait() should NOT have been called
		mock_proc.wait.assert_not_called()


@pytest.mark.unit
class TestStreamPty:
	def test_non_tty_delegates_to_stream_pipe(self, tmp_path):
		"""When stdin is not a tty, stream_pty falls back to stream_pipe."""
		with patch("sys.stdin") as mock_stdin, patch("xviv.utils.stream.stream_pipe") as mock_pipe:
			mock_stdin.isatty.return_value = False
			mock_pipe.return_value = iter([OutputLine(text="ok", level=logging.DEBUG, raw="ok")])
			list(stream_pty(("echo",), cwd=str(tmp_path), classifier=identity_classifier))
		mock_pipe.assert_called_once()
