import logging
import os
import sys
import tempfile
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from xviv.utils.log import BOLD, DIM, GREEN, RED, RESET, get_log_formatter
from xviv.utils.term import terminal_full_length_divider

logger = logging.getLogger(__name__)


def _fmt_duration(seconds: float) -> str:
	m, s = divmod(int(seconds), 60)
	return f"{m}m {s}s" if m else f"{s}s"


def _print_job(
	label: str,
	exc: BaseException | None,
	captured: str,
	index: int,
	total: int,
	elapsed: float | None = None,
) -> None:
	failed = exc is not None
	status_color = RED if failed else GREEN
	status_text = "FAILED" if failed else "OK"
	duration = (
		f"  {DIM}{'finished in' if not failed else 'after'} {_fmt_duration(elapsed)}{RESET}"
		if elapsed is not None
		else ""
	)

	print(f"\n{DIM}[{index}/{total}]{RESET} {BOLD}{label}{RESET}  {status_color}{status_text}{RESET}{duration}")
	print(f"{DIM}{terminal_full_length_divider()}{RESET}")

	if captured:
		for line in captured.splitlines():
			print(f"  {line}")
	else:
		print(f"  {DIM}(no output){RESET}")

	if failed and exc:
		if not isinstance(exc, SystemExit):
			traceback.print_exception(exc, colorize=True)  # type: ignore[call-overload]

	print(f"{DIM}{terminal_full_length_divider()}{RESET}")


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

	def __init__(self, base_logger_name: str = "xviv") -> None:
		import time as _time

		self._time = _time
		self._lock = threading.Lock()
		self._active: dict[int, tuple[str, logging.FileHandler]] = {}
		self._logs: dict[str, str] = {}
		self._start_times: dict[int, float] = {}
		self._elapsed: dict[str, float] = {}
		self._suppress = self._SuppressWorkerFilter(self)
		self._capture = self._CaptureHandler(self)
		self._patched_handlers: list[logging.Handler] = []

		node = logging.getLogger(base_logger_name)
		while node:
			for hdlr in node.handlers:
				hdlr.addFilter(self._suppress)
				self._patched_handlers.append(hdlr)
			if not node.propagate or node.parent is None:
				break
			node = node.parent

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

	def _is_worker(self, tid: int) -> bool:
		with self._lock:
			return tid in self._active

	def _get_file_handler(self, tid: int) -> logging.FileHandler | None:
		with self._lock:
			entry = self._active.get(tid)
			return entry[1] if entry else None


def _wrap(fn: Callable[[], None], label: str, router: _JobLogRouter) -> Callable[[], None]:
	def _inner() -> None:
		router.register(label)

		try:
			fn()
		finally:
			router.unregister()

	return _inner


def run_parallel(
	jobs: list[tuple[Callable[[], None], str]],
	*,
	max_workers: int = 4,
	dry_run: bool = False,
) -> None:
	if not jobs:
		return

	total = len(jobs)
	logger.info("Starting %d parallel job(s) (max_workers=%d)", total, max_workers)

	router = _JobLogRouter(base_logger_name="xviv")
	failures: list[tuple[str, BaseException, str, float | None]] = []
	success_count = 0
	completed = 0

	try:
		with ThreadPoolExecutor(max_workers=max_workers) as pool:
			futures: dict[Future[None], str] = {pool.submit(_wrap(fn, label, router)): label for fn, label in jobs}
			for fut in as_completed(futures):
				completed += 1
				label = futures[fut]
				exc = fut.exception()
				captured = router.read_log(label).strip()
				elapsed = None if dry_run else router.read_elapsed(label)

				if exc is None:
					success_count += 1
					_print_job(label, None, captured, completed, total, elapsed)
				else:
					failures.append((label, exc, captured, elapsed))
					print(f"\n{DIM}[{completed}/{total}]{RESET} {BOLD}{label}{RESET}  {RED}FAILED{RESET} ")
	finally:
		router.detach()

	if not failures:
		logger.info("parallel run finished: all %d job(s) succeeded", total)
		return

	print(f"\n{RED}{BOLD}{terminal_full_length_divider()}{RESET}")
	print(f"{RED}{BOLD}  {len(failures)} job(s) failed  ({success_count}/{total} succeeded){RESET}")
	print(f"{RED}{BOLD}{terminal_full_length_divider()}{RESET}")

	for i, (label, exc, captured, elapsed) in enumerate(failures, start=1):
		_print_job(label, exc, captured, i, len(failures), elapsed)

	logger.error(
		"parallel run finished: %d/%d job(s) failed: %s",
		len(failures),
		total,
		", ".join(label for label, _, _, _ in failures),
	)

	sys.exit(1)
