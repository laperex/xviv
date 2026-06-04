"""Tests for xviv.utils.job — Job, JobResult, LiveSink, BufferedSink, run_job_list."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import patch

import pytest

from tests.helpers import make_job
from xviv.utils.display import EvComplete, EvDispatch, EvSummary
from xviv.utils.error import JobFailedError
from xviv.utils.job import (
	BufferedSink,
	Job,
	JobResult,
	LiveSink,
	_run_parallel,
	_run_sequential,
	run_job_list,
)
from xviv.utils.stream import OutputLine, identity_classifier

# ---------------------------------------------------------------------------
# Job dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJobDataclass:
	def test_job_is_frozen(self):
		job = make_job()
		with pytest.raises((AttributeError, TypeError)):
			job.label = "modified"  # type: ignore[misc]

	def test_log_file_defaults_to_empty_string(self):
		job = Job(
			label="x",
			cmd=("echo",),
			cwd="/tmp",
			classifier=identity_classifier,
			dry_run=False,
			interactive=False,
			detach=False,
		)
		assert job.log_file == ""

	def test_cmd_is_tuple(self):
		job = make_job(cmd=("vivado", "-mode", "batch"))
		assert isinstance(job.cmd, tuple)

	def test_all_required_fields(self):
		job = make_job()
		assert job.label is not None
		assert job.cmd is not None
		assert job.cwd is not None
		assert job.classifier is not None


# ---------------------------------------------------------------------------
# JobResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJobResult:
	def test_succeeded_when_no_exc_and_zero_rc(self):
		job = make_job()
		result = JobResult(job=job, returncode=0, elapsed=1.0, exc=None)
		assert result.succeeded is True
		assert result.failed is False

	def test_failed_when_exc_set(self):
		job = make_job()
		result = JobResult(job=job, returncode=0, elapsed=1.0, exc=ValueError("oops"))
		assert result.failed is True
		assert result.succeeded is False

	def test_failed_when_nonzero_rc(self):
		job = make_job()
		result = JobResult(job=job, returncode=1, elapsed=1.0, exc=None)
		assert result.failed is True

	def test_succeeded_when_returncode_is_none(self):
		"""dry-run sets returncode=None — that counts as success."""
		job = make_job()
		result = JobResult(job=job, returncode=None, elapsed=None, exc=None)
		assert result.succeeded is True

	def test_failed_is_inverse_of_succeeded(self):
		job = make_job()
		for rc, exc in [(0, None), (1, None), (0, Exception()), (None, None)]:
			result = JobResult(job=job, returncode=rc, elapsed=0.0, exc=exc)
			assert result.failed == (not result.succeeded)


# ---------------------------------------------------------------------------
# LiveSink
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLiveSinkDryRun:
	def test_dry_run_returns_none_rc_none_elapsed(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		result = LiveSink().run(job)
		assert result.returncode is None
		assert result.elapsed is None
		assert result.exc is None

	def test_dry_run_never_calls_stream_pipe(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		with patch("xviv.utils.job.stream_pipe") as mock_pipe:
			LiveSink().run(job)
		mock_pipe.assert_not_called()


@pytest.mark.unit
class TestLiveSinkDetach:
	def test_detach_calls_stream_popen(self, tmp_path: Path):
		job = make_job(detach=True, log_file=str(tmp_path / "l.log"))
		with patch("xviv.utils.job.stream_popen", return_value=42) as mock_popen:
			result = LiveSink().run(job)
		mock_popen.assert_called_once()
		assert result.returncode == 42

	def test_detach_does_not_wait(self, tmp_path: Path):
		job = make_job(detach=True, log_file=str(tmp_path / "l.log"))
		with patch("xviv.utils.job.stream_popen", return_value=99):
			result = LiveSink().run(job)
		assert result.elapsed == 0.0


@pytest.mark.unit
class TestLiveSinkPipe:
	def _make_pipe_lines(self, lines):
		return [OutputLine(text=i, level=logging.DEBUG, raw=i) for i in lines]

	def test_success_zero_rc(self, tmp_path: Path):
		log = tmp_path / "out.log"
		job = make_job(log_file=str(log), cmd=("echo", "hi"))
		with patch("xviv.utils.job.stream_pipe", return_value=iter(self._make_pipe_lines(["hi"]))):
			with patch("xviv.utils.display.emit"):
				result = LiveSink().run(job)
		assert result.succeeded

	def test_called_process_error_sets_exc_and_rc(self, tmp_path: Path):
		log = tmp_path / "out.log"
		job = make_job(log_file=str(log))

		def _raise(*a, **kw):
			raise CalledProcessError(2, ["false"])
			yield  # make it a generator

		with patch("xviv.utils.job.stream_pipe", side_effect=CalledProcessError(2, ["false"])):
			with patch("xviv.utils.display.emit"):
				result = LiveSink().run(job)
		assert result.exc is not None
		assert result.returncode == 2


# ---------------------------------------------------------------------------
# BufferedSink
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBufferedSinkDryRun:
	def test_dry_run_returns_none_rc(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		result = BufferedSink().run(job)
		assert result.returncode is None

	def test_dry_run_never_calls_stream_pipe(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		with patch("xviv.utils.job.stream_pipe") as mock_pipe:
			BufferedSink().run(job)
		mock_pipe.assert_not_called()


@pytest.mark.unit
class TestBufferedSinkCapture:
	def _make_lines(self, texts):
		return [OutputLine(text=t, level=logging.DEBUG, raw=t) for t in texts]

	def test_captured_contains_all_lines(self, tmp_path: Path):
		log = tmp_path / "out.log"
		job = make_job(log_file=str(log))
		texts = ["alpha", "beta", "gamma"]
		with patch("xviv.utils.job.stream_pipe", return_value=iter(self._make_lines(texts))):
			result = BufferedSink().run(job)
		assert len(result.captured) == 3
		assert [i.text for i in result.captured] == texts

	def test_zero_rc_on_success(self, tmp_path: Path):
		log = tmp_path / "out.log"
		job = make_job(log_file=str(log))
		with patch("xviv.utils.job.stream_pipe", return_value=iter(self._make_lines(["ok"]))):
			result = BufferedSink().run(job)
		assert result.returncode == 0


# ---------------------------------------------------------------------------
# run_job_list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunJobListEmpty:
	def test_empty_list_returns_immediately(self):
		with patch("xviv.utils.job._run_sequential") as seq, patch("xviv.utils.job._run_parallel") as par:
			run_job_list([])
		seq.assert_not_called()
		par.assert_not_called()


@pytest.mark.unit
class TestRunJobListSingle:
	def test_single_job_calls_run_sequential(self):
		job = make_job()
		with patch("xviv.utils.job._run_sequential") as seq, patch("xviv.utils.job._run_parallel") as par:
			run_job_list([job])
		seq.assert_called_once_with(job)
		par.assert_not_called()


@pytest.mark.unit
class TestRunJobListParallel:
	def test_two_or_more_calls_run_parallel(self):
		jobs = [make_job(label=f"j{i}") for i in range(3)]
		with patch("xviv.utils.job._run_parallel") as par:
			run_job_list(jobs)
		par.assert_called_once()
		par.call_args.args[0], par.call_args.args
		# first positional arg is the jobs list
		assert par.call_args.args[0] == jobs


@pytest.mark.unit
class TestRunJobListSequentialExec:
	def test_sequential_exec_true_calls_sequential_for_each(self):
		jobs = [make_job(label=f"j{i}") for i in range(3)]
		called_labels = []
		with patch("xviv.utils.job._run_sequential", side_effect=lambda j: called_labels.append(j.label)):
			run_job_list(jobs, sequential_exec=True)
		assert called_labels == ["j0", "j1", "j2"]


@pytest.mark.unit
class TestParallelFailure:
	def test_one_failure_raises_job_failed_error(self, tmp_path: Path):
		logs = [str(tmp_path / f"j{i}.log") for i in range(2)]
		good_job = make_job(label="good", dry_run=True, log_file=logs[0])
		bad_job = make_job(label="bad", cmd=("false",), log_file=logs[1], dry_run=False)

		def _fail_if_bad(job):
			if job.label == "bad":
				raise CalledProcessError(1, ["false"])
			return JobResult(job=job, returncode=None, elapsed=None, exc=None)

		with patch.object(BufferedSink, "run", side_effect=_fail_if_bad):
			with patch("xviv.utils.display.emit"):
				with pytest.raises(JobFailedError) as exc_info:
					_run_parallel([good_job, bad_job], max_workers=2)
		err = exc_info.value
		labels = [label for label, _ in err.failed]
		assert "bad" in labels

	def test_multiple_failures_all_in_error(self, tmp_path: Path):
		jobs = [make_job(label=f"fail{i}", cmd=("false",), log_file=str(tmp_path / f"{i}.log")) for i in range(3)]

		def _always_fail(job):
			return JobResult(job=job, returncode=1, elapsed=0.1, exc=ValueError("fail"))

		with patch.object(BufferedSink, "run", side_effect=_always_fail):
			with patch("xviv.utils.display.emit"):
				with pytest.raises(JobFailedError) as exc_info:
					_run_parallel(jobs, max_workers=4)
		err = exc_info.value
		assert len(err.failed) == 3


@pytest.mark.unit
@pytest.mark.slow
class TestParallelConcurrency:
	def test_wall_time_less_than_sum(self, tmp_path: Path):
		"""3 jobs of 0.15s each should finish in < 0.4s with max_workers=3."""
		n = 3
		delay = 0.15
		logs = [str(tmp_path / f"j{i}.log") for i in range(n)]
		jobs = [make_job(label=f"j{i}", log_file=logs[i]) for i in range(n)]

		def _slow_run(job):
			time.sleep(delay)
			return JobResult(job=job, returncode=0, elapsed=delay, exc=None)

		with patch.object(BufferedSink, "run", side_effect=_slow_run):
			with patch("xviv.utils.display.emit"):
				t0 = time.monotonic()
				_run_parallel(jobs, max_workers=n)
				elapsed = time.monotonic() - t0

		assert elapsed < delay * n - 0.05  # Must be significantly faster than serial


@pytest.mark.unit
class TestParallelKeyboardInterrupt:
	def test_keyboard_interrupt_re_raised(self, tmp_path: Path):
		"""KeyboardInterrupt raised in the main thread during as_completed must propagate."""
		jobs = [make_job(label=f"j{i}", dry_run=True, log_file=str(tmp_path / f"{i}.log")) for i in range(2)]

		def _ki_as_completed(fs, *a, **kw):
			raise KeyboardInterrupt()

		with patch("xviv.utils.job.as_completed", side_effect=_ki_as_completed):
			with patch("xviv.utils.display.emit"):
				with pytest.raises(KeyboardInterrupt):
					_run_parallel(jobs, max_workers=2)


@pytest.mark.unit
class TestDisplayEvents:
	def test_ev_dispatch_emitted_before_execution(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		events = []
		with patch("xviv.utils.display.emit", side_effect=lambda ev: events.append(ev)):
			_run_sequential(job)

		assert any(isinstance(e, EvDispatch) for e in events)
		dispatch_idx = next(i for i, e in enumerate(events) if isinstance(e, EvDispatch))
		complete_idx = next((i for i, e in enumerate(events) if isinstance(e, EvComplete)), len(events))
		assert dispatch_idx < complete_idx

	def test_ev_complete_emitted_after_execution(self, tmp_path: Path):
		job = make_job(dry_run=True, log_file=str(tmp_path / "l.log"))
		events = []
		with patch("xviv.utils.display.emit", side_effect=lambda ev: events.append(ev)):
			_run_sequential(job)
		assert any(isinstance(e, EvComplete) for e in events)

	def test_ev_summary_emitted_in_parallel_batch(self, tmp_path: Path):
		jobs = [make_job(label=f"j{i}", dry_run=True, log_file=str(tmp_path / f"{i}.log")) for i in range(2)]
		events = []
		with patch("xviv.utils.display.emit", side_effect=lambda ev: events.append(ev)):
			_run_parallel(jobs, max_workers=2)

		assert any(isinstance(e, EvSummary) for e in events)
