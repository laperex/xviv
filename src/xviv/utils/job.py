from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from subprocess import CalledProcessError

import xviv.utils.display as _display
from xviv.utils.display import EvComplete, EvDispatch, EvLine, EvSummary
from xviv.utils.error import JobFailedError
from xviv.utils.stream import OutputLine, stream_pipe, stream_popen, stream_pty

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
	label: str
	cmd: tuple[str, ...]
	cwd: str
	dry_run: bool
	interactive: bool = False
	detach: bool = False
	env: dict[str, str] | None = None
	log_file: str = ""
	classifier: Callable[[str], OutputLine] = lambda _l: OutputLine(text=_l, level=logging.NOTSET, raw=_l)


@dataclass
class JobResult:
	job: Job
	returncode: int | None
	elapsed: float | None
	exc: BaseException | None
	captured: list[OutputLine] = field(default_factory=list)

	@property
	def succeeded(self) -> bool:
		return self.exc is None and (self.returncode is None or self.returncode == 0)

	@property
	def failed(self) -> bool:
		return not self.succeeded and (self.returncode is not None)


class LiveSink:
	def run(self, job: Job) -> JobResult:  # noqa: C901
		if job.dry_run:
			logger.debug("dry-run: skipping %s", job.label)
			return JobResult(job=job, returncode=None, elapsed=None, exc=None)

		if job.detach:
			pid = stream_popen(job.cmd, cwd=job.cwd, env=job.env)
			logger.debug("detached %s  pid=%d", job.label, pid)
			return JobResult(job=job, returncode=pid, elapsed=0.0, exc=None)

		os.makedirs(os.path.dirname(os.path.abspath(job.log_file)), exist_ok=True)

		stream_fn = stream_pty if job.interactive else stream_pipe

		t0 = time.monotonic()
		exc: BaseException | None = None
		rc: int | None = 0

		try:
			with open(job.log_file, "w", encoding="utf-8", errors="replace") as fh:
				for line in stream_fn(job.cmd, cwd=job.cwd, env=job.env, classifier=job.classifier):
					fh.write(line.raw + "\n")
					fh.flush()
					if not job.interactive:
						_display.emit(EvLine(job=job, line=line))
		except KeyboardInterrupt:
			logger.warning("Interrupted - cancelling job")
			sys.exit(1)
		except CalledProcessError as e:
			exc = e
			rc = e.returncode
		except BaseException as e:
			exc = e
			rc = -1

		elapsed = time.monotonic() - t0
		return JobResult(job=job, returncode=rc, elapsed=elapsed, exc=exc)


class BufferedSink:
	def run(self, job: Job) -> JobResult:
		try:
			return self._run_inner(job)
		except BaseException as e:  # pragma: no cover - defensive
			logger.exception("Unexpected error in BufferedSink for %s", job.label)
			return JobResult(job=job, returncode=-1, elapsed=None, exc=e)

	def _run_inner(self, job: Job) -> JobResult:
		_log = logging.getLogger(f"xviv.utils.job.{job.label}")

		if job.dry_run:
			_log.debug("dry-run: skipping %s", job.label)
			return JobResult(job=job, returncode=None, elapsed=None, exc=None)

		if job.detach:
			pid = stream_popen(job.cmd, cwd=job.cwd, env=job.env)
			_log.debug("detached %s  pid=%d", job.label, pid)
			return JobResult(job=job, returncode=pid, elapsed=0.0, exc=None)

		if job.interactive:
			_log.warning(
				"%s: interactive=True is not supported in parallel mode; falling back to stream_pipe",
				job.label,
			)

		os.makedirs(os.path.dirname(os.path.abspath(job.log_file)), exist_ok=True)

		t0 = time.monotonic()
		exc: BaseException | None = None
		rc: int | None = 0
		buffer: list[OutputLine] = []

		try:
			with open(job.log_file, "w", encoding="utf-8", errors="replace") as fh:
				for line in stream_pipe(job.cmd, cwd=job.cwd, env=job.env, classifier=job.classifier):
					fh.write(line.raw + "\n")
					fh.flush()
					buffer.append(line)
					_log.debug("[%s] %s", job.label, line.text)
		except CalledProcessError as e:
			exc = e
			rc = e.returncode
		except BaseException as e:
			exc = e
			rc = -1

		elapsed = time.monotonic() - t0
		_log.log(
			logging.ERROR if exc else logging.DEBUG,
			"%s: rc=%s  elapsed=%.1fs",
			job.label,
			rc,
			elapsed,
		)
		return JobResult(job=job, returncode=rc, elapsed=elapsed, exc=exc, captured=buffer)


def _run_sequential(job: Job) -> None:
	_display.emit(EvDispatch(job=job, parallel=False))
	result = LiveSink().run(job)
	_display.emit(EvComplete(job=job, result=result, index=1, total=1, parallel=False))

	if result.failed:
		exc = result.exc or CalledProcessError(result.returncode or -1, list(job.cmd))
		raise JobFailedError([(job.label, exc)])


def _run_parallel(jobs: list[Job], max_workers: int) -> None:
	total = len(jobs)
	logger.debug("Starting %d parallel job(s)  max_workers=%d", total, max_workers)

	for job in jobs:
		_display.emit(EvDispatch(job=job, parallel=True))

	results: list[JobResult] = []
	completed: int = 0
	sink = BufferedSink()

	with ThreadPoolExecutor(max_workers=max_workers) as pool:
		future_to_job = {pool.submit(sink.run, job): job for job in jobs}

		try:
			for future in as_completed(future_to_job):
				completed += 1
				job = future_to_job[future]
				try:
					result = future.result()
				except BaseException as e:  # sink bug - should not happen
					result = JobResult(job=job, returncode=-1, elapsed=None, exc=e)
				results.append(result)
				_display.emit(
					EvComplete(
						job=job,
						result=result,
						index=completed,
						total=total,
						parallel=True,
					)
				)

		except KeyboardInterrupt:
			logger.warning("Interrupted - cancelling remaining parallel jobs")
			for f in future_to_job:
				f.cancel()
			pool.shutdown(wait=False, cancel_futures=True)
			raise

	_display.emit(EvSummary(results=results))

	failures = [r for r in results if r.failed]
	if failures:
		logger.error(
			"%d/%d job(s) failed: %s",
			len(failures),
			total,
			", ".join(r.job.label for r in failures),
		)
		raise JobFailedError([(r.job.label, r.exc or Exception(f"exit code {r.returncode}")) for r in failures])

	logger.debug("All %d job(s) succeeded", total)


def run_job_list(jobs: list[Job], *, max_workers: int = 4, sequential_exec: bool = False, exit_on_fail: bool = False) -> None:
	try:
		if not jobs:
			return

		if len(jobs) == 1 or sequential_exec:
			if sequential_exec:
				for i in jobs:
					_run_sequential(i)
			else:
				_run_sequential(jobs[0])
		else:
			_run_parallel(jobs, max_workers=max_workers)
	except JobFailedError as e:
		if exit_on_fail:
			print(e)
			sys.exit(1)

		raise
		


def run_job(job: Job, exit_on_fail: bool = False):
	run_job_list(jobs=[job], exit_on_fail=exit_on_fail)
