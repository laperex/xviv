import logging
import sys
import tempfile
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from xviv.utils import error
from xviv.utils.log import ColorFormatter, _supports_color

logger = logging.getLogger(__name__)

_RESET = "\033[0m"
_RED   = "\033[31m"
_GREEN = "\033[32m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"


def _make_job_formatter() -> logging.Formatter:
	if _supports_color():
		return ColorFormatter("%(levelname)s %(message)s")
	return logging.Formatter("%(levelname)-8s %(name)s — %(message)s")


# def _print_traceback(exc: BaseException) -> None:
# 	traceback.print_exception(type(exc), exc, exc.__traceback__, colorize=True)
	# try:
	#     return
	# except TypeError:
	#     pass

	# try:
	#     from pygments import highlight
	#     from pygments.formatters import Terminal256Formatter
	#     from pygments.lexers import PythonTracebackLexer

	#     tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
	#     print(highlight(tb_text, PythonTracebackLexer(), Terminal256Formatter(style="native")), end="")
	#     return
	# except ImportError:
	#     pass

	# traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stdout)


def _print_job(
	label: str,
	exc: BaseException | None,
	captured: str,
	index: int,
	total: int,
) -> None:
	failed = exc is not None
	status_color = _RED if failed else _GREEN
	status_text  = "FAILED" if failed else "OK"

	print(f"\n{_DIM}[{index}/{total}]{_RESET} {_BOLD}{label}{_RESET}  {status_color}{status_text}{_RESET}")
	print(f"{_DIM}{'─' * 64}{_RESET}")

	if captured:
		for line in captured.splitlines():
			print(f"  {line}")
	else:
		print(f"  {_DIM}(no output){_RESET}")

	if failed:
		print()
		if exc:
			traceback.print_exception(exc, colorize=True)  # type: ignore[call-overload]

	print(f"{_DIM}{'─' * 64}{_RESET}")


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
		self._lock = threading.Lock()
		self._active: dict[int, tuple[str, logging.FileHandler]] = {}
		self._logs: dict[str, Path] = {}
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
		tmp = Path(tempfile.mktemp(suffix=".log", prefix="xviv_job_"))
		fh = logging.FileHandler(tmp, encoding="utf-8")
		fh.setFormatter(_make_job_formatter())
		tid = threading.get_ident()
		with self._lock:
			self._active[tid] = (label, fh)
			self._logs[label] = tmp

	def unregister(self) -> None:
		tid = threading.get_ident()
		with self._lock:
			entry = self._active.pop(tid, None)
		if entry:
			entry[1].flush()
			entry[1].close()

	def read_log(self, label: str) -> str:
		path = self._logs.get(label)
		return path.read_text(encoding="utf-8") if path and path.exists() else ""

	def detach(self) -> None:
		for hdlr in self._patched_handlers:
			hdlr.removeFilter(self._suppress)
		logging.getLogger().removeHandler(self._capture)
		for path in self._logs.values():
			path.unlink(missing_ok=True)

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
) -> None:
	if not jobs:
		return

	total = len(jobs)
	logger.info("Starting %d parallel job(s) (max_workers=%d)", total, max_workers)

	router = _JobLogRouter(base_logger_name="xviv")
	failures: list[tuple[str, BaseException, str]] = []
	success_count = 0
	completed = 0

	try:
		with ThreadPoolExecutor(max_workers=max_workers) as pool:
			futures: dict[Future[None], str] = {
				pool.submit(_wrap(fn, label, router)): label
				for fn, label in jobs
			}
			for fut in as_completed(futures):
				completed += 1
				label    = futures[fut]
				exc      = fut.exception()
				captured = router.read_log(label).strip()

				if exc is None:
					success_count += 1
					_print_job(label, None, captured, completed, total)
				else:
					failures.append((label, exc, captured))
					print(
						f"\n{_DIM}[{completed}/{total}]{_RESET} "
						f"{_BOLD}{label}{_RESET}  {_RED}FAILED{_RESET} "
						f"{_DIM}(output below){_RESET}"
					)
	finally:
		router.detach()

	if not failures:
		logger.info("parallel run finished: all %d job(s) succeeded", total)
		return

	print(f"\n{_RED}{_BOLD}{'─' * 64}{_RESET}")
	print(f"{_RED}{_BOLD}  {len(failures)} job(s) failed  ({success_count}/{total} succeeded){_RESET}")
	print(f"{_RED}{_BOLD}{'─' * 64}{_RESET}")

	for i, (label, exc, captured) in enumerate(failures, start=1):
		_print_job(label, exc, captured, i, len(failures))

	logger.error(
		"parallel run finished: %d/%d job(s) failed: %s",
		len(failures),
		total,
		", ".join(label for label, _, _ in failures),
	)

	sys.exit(1)