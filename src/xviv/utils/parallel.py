import io
import logging
import os
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from xviv.utils.log import BOLD, DIM, GREEN, LEVEL_COLORS, RED, RESET, get_log_formatter
from xviv.utils.term import terminal_full_length_divider

from xviv.utils import error

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_duration(seconds: float) -> str:
	m, s = divmod(int(seconds), 60)
	return f"{m}m {s}s" if m else f"{s}s"


def _format_exception(exc: BaseException) -> str:
	buf = io.StringIO()
	try:
		traceback.print_exception(exc, file=buf, colorize=True)  # type: ignore[call-overload]
	except TypeError:
		traceback.print_exception(exc, file=buf)
	return buf.getvalue()


def _print_job(
	label: str,
	exc: BaseException | None,
	captured: str,
	index: int,
	total: int,
	elapsed: float | None = None,
	log_file: str | None = None,
	*,
	lock: threading.Lock,
) -> None:
	failed = exc is not None
	status_color = RED if failed else GREEN
	status_text = "FAILED" if failed else "OK"
	duration = f"  {DIM}{'finished in' if not failed else 'after'} {_fmt_duration(elapsed)}{RESET}" if elapsed is not None else ""

	lines: list[str] = []
	lines.append(f"\n{DIM}[{index}/{total}]{RESET} {BOLD}{label}{RESET}  {status_color}{status_text}{RESET}{duration}")
	lines.append(f"{DIM}{terminal_full_length_divider()}{RESET}")

	if captured:
		for line in captured.splitlines():
			lines.append(f"  {line}")
	else:
		lines.append(f"  {DIM}(no output){RESET}")

	if failed and exc and not isinstance(exc, SystemExit):
		lines.append(_format_exception(exc))

	if log_file:
		lines.append(f"  {DIM}{BOLD}LOG{RESET} {DIM}{log_file}{RESET}")

	lines.append(f"{DIM}{terminal_full_length_divider()}{RESET}")

	with lock:
		print("\n".join(lines))


# ---------------------------------------------------------------------------
# Per-job log routing
# ---------------------------------------------------------------------------


class _JobLogRouter:
	class _SuppressWorkerFilter(logging.Filter):
		def __init__(self, router: "_JobLogRouter") -> None:
			super().__init__()
			self._router = router

		def filter(self, record: logging.LogRecord) -> bool:
			return not self._router._is_worker(threading.get_ident())

	class _CaptureHandler(logging.Handler):
		def __init__(self, router: "_JobLogRouter") -> None:
			super().__init__(level=logging.INFO)
			self._router = router

		def emit(self, record: logging.LogRecord) -> None:
			fh = self._router._get_file_handler(threading.get_ident())
			if fh is not None:
				fh.emit(record)

	# ------------------------------------------------------------------
	# Lifecycle
	# ------------------------------------------------------------------

	def __init__(self, base_logger_name: str = "xviv") -> None:
		self._time = time
		self._lock = threading.Lock()
		self._active: dict[int, tuple[str, logging.FileHandler]] = {}
		self._logs: dict[str, str] = {}
		self._start_times: dict[int, float] = {}
		self._elapsed: dict[str, float] = {}

		self._suppress = self._SuppressWorkerFilter(self)
		self._capture = self._CaptureHandler(self)
		self._patched_handlers: list[logging.Handler] = []

		# Walk the logger hierarchy and add _suppress **only** to
		# StreamHandlers that are NOT FileHandlers.
		#
		# FileHandler is a subclass of StreamHandler; without the
		# `not isinstance(..., FileHandler)` guard the isinstance check
		# matches FileHandlers too, which would prevent worker-thread
		# records from reaching the persistent log file.
		node: logging.Logger | None = logging.getLogger(base_logger_name)
		while node:
			for hdlr in node.handlers:
				if isinstance(hdlr, logging.StreamHandler) and not isinstance(hdlr, logging.FileHandler):
					hdlr.addFilter(self._suppress)
					self._patched_handlers.append(hdlr)
			if not node.propagate or node.parent is None:
				break
			node = node.parent

		# _CaptureHandler on the root logger catches every record
		# (regardless of logger hierarchy) and routes it to the
		# per-job temp file.
		logging.getLogger().addHandler(self._capture)

	def register(self, label: str) -> None:
		tmp = tempfile.mktemp(suffix=".log", prefix="xviv_job_")
		fh = logging.FileHandler(tmp, encoding="utf-8")
		fh.setFormatter(get_log_formatter())
		tid = threading.get_ident()
		with self._lock:
			self._active[tid] = (label, fh)
			self._logs[label] = tmp
			self._start_times[tid] = self._time.monotonic()

	def unregister(self) -> None:
		tid = threading.get_ident()
		with self._lock:
			entry = self._active.pop(tid, None)
			start = self._start_times.pop(tid, None)
			if entry and start is not None:
				self._elapsed[entry[0]] = self._time.monotonic() - start
		if entry:
			entry[1].flush()
			entry[1].close()

	def read_log(self, label: str) -> str:
		path = self._logs.get(label)
		if path and os.path.exists(path):
			with open(path, encoding="utf-8") as f:
				return f.read()
		return ""

	def read_elapsed(self, label: str) -> float | None:
		return self._elapsed.get(label)

	def detach(self) -> None:
		for hdlr in self._patched_handlers:
			hdlr.removeFilter(self._suppress)
		logging.getLogger().removeHandler(self._capture)
		for path in self._logs.values():
			try:
				os.unlink(path)
			except FileNotFoundError:
				pass

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _is_worker(self, tid: int) -> bool:
		with self._lock:
			return tid in self._active

	def _get_file_handler(self, tid: int) -> logging.FileHandler | None:
		with self._lock:
			entry = self._active.get(tid)
			return entry[1] if entry else None


# ---------------------------------------------------------------------------
# Job wrapper
# ---------------------------------------------------------------------------


def _wrap(fn: Callable[[], None], label: str, router: _JobLogRouter) -> Callable[[], None]:
	def _inner() -> None:
		router.register(label)
		try:
			fn()
		finally:
			router.unregister()

	return _inner


def _start_log(
	fn: Callable[[], None],
	label: str,
	log_file: str,
	router: _JobLogRouter,
	lock: threading.Lock,
) -> None:
	with lock:
		print(f"{LEVEL_COLORS[logging.CRITICAL]}DISPATCH{RESET} {BOLD}{label}{RESET} {DIM}{log_file}{RESET}")
	_wrap(fn, label, router)()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_parallel(
	jobs: list[tuple[Callable[[], None], str, str]],
	*,
	max_workers: int = 4,
	dry_run: bool = False,
) -> None:
	if not jobs:
		return

	total = len(jobs)
	logger.info("Starting %d parallel job(s) (max_workers=%d)", total, max_workers)

	router = _JobLogRouter(base_logger_name="xviv")
	print_lock = threading.Lock()

	failures: list[tuple[str, BaseException, str, float | None]] = []
	success_count = 0
	completed = 0
	start_times: dict[str, float] = {}

	try:
		with ThreadPoolExecutor(max_workers=max_workers) as pool:
			futures: dict[Future[None], tuple[str, str]] = {}

			for fn, label, log_file in jobs:
				start_times[label] = time.time()
				futures[pool.submit(_start_log, fn, label, log_file, router, print_lock)] = (label, log_file)

			try:
				for fut in as_completed(futures):
					completed += 1
					label, logfile = futures[fut]
					exc = fut.exception()
					captured = router.read_log(label).strip()
					elapsed = None if dry_run else router.read_elapsed(label)

					start_time = start_times.get(label)
					try:
						if logfile is not None:
							log_mtime = os.path.getmtime(logfile)
							active_logfile = logfile if (start_time is not None and log_mtime > start_time) else None
						else:
							active_logfile = None
					except OSError:
						active_logfile = None

					active_logfile = logfile if (logfile is not None and os.path.exists(logfile)) else None

					if exc is None:
						success_count += 1
						_print_job(
							label,
							None,
							captured,
							completed,
							total,
							elapsed,
							active_logfile,
							lock=print_lock,
						)
					else:
						failures.append((label, exc, captured, elapsed))
						with print_lock:
							print(f"\n{DIM}[{completed}/{total}]{RESET} {BOLD}{label}{RESET}  {RED}FAILED{RESET}")

			except KeyboardInterrupt:
				with print_lock:
					print(f"\n{RED}{BOLD}Interrupted - cancelling jobs…{RESET}")
				for fut in futures:
					fut.cancel()
				pool.shutdown(wait=False, cancel_futures=True)
				router.detach()
				sys.exit(130)

	finally:
		router.detach()

	if not failures:
		logger.info("parallel run finished: all %d job(s) succeeded", total)
		return

	print(f"\n{RED}{BOLD}{terminal_full_length_divider()}{RESET}")
	print(f"{RED}{BOLD}  {len(failures)} job(s) failed  ({success_count}/{total} succeeded){RESET}")
	print(f"{RED}{BOLD}{terminal_full_length_divider()}{RESET}")

	for i, (label, exc, captured, elapsed) in enumerate(failures, start=1):
		_print_job(label, exc, captured, i, len(failures), elapsed, lock=print_lock)

	logger.error(
		"parallel run finished: %d/%d job(s) failed: %s",
		len(failures),
		total,
		", ".join(label for label, _, _, _ in failures),
	)

	raise error.ParallelJobError([(label, exc) for label, exc, _, _ in failures])
