from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from xviv.utils.log import (
	BOLD,
	DIM,
	GREEN,
	LEVEL_COLORS,
	RED,
	RESET,
	_supports_color,
)
from xviv.utils.term import terminal_full_length_divider

if TYPE_CHECKING:
	from xviv.utils.job import Job, JobResult
	from xviv.utils.stream import OutputLine

MAGENTA: str = LEVEL_COLORS[logging.CRITICAL]
YELLOW: str = LEVEL_COLORS[logging.WARNING]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@dataclass
class EvDispatch:
	job: Job
	parallel: bool


@dataclass
class EvLine:
	job: Job
	line: OutputLine


@dataclass
class EvComplete:
	job: Job
	result: JobResult
	index: int
	total: int
	parallel: bool


@dataclass
class EvSummary:
	results: list[JobResult]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fmt_duration(seconds: float) -> str:
	m, s = divmod(int(seconds), 60)
	return f"{m}m {s}s" if m else f"{s}s"


def _rel_path(path: str) -> str:
	try:
		return os.path.relpath(path)
	except ValueError:  # Windows: different drives
		return path


def _render_output_line(line: OutputLine) -> str:
	if not _supports_color():
		_PREFIX = {
			logging.INFO: "INFO:",
			logging.WARNING: "WARNING:",
			logging.ERROR: "ERROR:",
			logging.CRITICAL: "CRITICAL WARNING:",
		}
		pfx = _PREFIX.get(line.level, "")
		return f"{pfx} {line.text}".lstrip() if pfx else line.text

	lvl = line.level
	text = line.text

	if lvl == logging.DEBUG:
		return f"{text}"
	if lvl == logging.INFO:
		c = LEVEL_COLORS[logging.INFO]
		return f"{c}{BOLD}INFO:{RESET} {text}"
	if lvl == logging.WARNING:
		c = LEVEL_COLORS[logging.WARNING]
		return f"{c}{BOLD}WARNING:{RESET} {c}{text}{RESET}"
	if lvl == logging.ERROR:
		c = LEVEL_COLORS[logging.ERROR]
		return f"{c}{BOLD}ERROR:{RESET} {c}{text}{RESET}"
	if lvl == logging.CRITICAL:
		c = LEVEL_COLORS[logging.CRITICAL]
		return f"{c}{BOLD}CRITICAL WARNING:{RESET} {c}{text}{RESET}"
	return text


def _counter(index: int, total: int, suffix: str = "") -> str:
	mid = f"{index}/{total} {suffix}".rstrip() if suffix else f"{index}/{total}"
	return f"{DIM}[{RESET}{mid}{DIM}]{RESET}"


def _header_line(result: JobResult, index: int, total: int, suffix: str = "") -> str:
	ctr = _counter(index, total, suffix)
	label = f"{BOLD}{result.job.label}{RESET}"
	elapsed = result.elapsed
	dur = _fmt_duration(elapsed) if elapsed is not None else "?"

	verb = ""
	status = ""
	if result.returncode is not None:
		if result.succeeded:
			verb = "finished in"
			status = f"{GREEN}{BOLD}OK{RESET}"
		else:
			verb = "after"
			status = f"{RED}{BOLD}FAILED{RESET}"

	timing = f"{DIM}{verb} {dur}{RESET}"
	return f"{ctr}  {label}  {status}  {timing}"


def _build_parallel_block(
	result: JobResult,
	index: int,
	total: int,
	*,
	counter_suffix: str = "",
	trim_debug: bool = False,
) -> str:
	div = terminal_full_length_divider()
	log_path = _rel_path(result.job.log_file)

	captured = result.captured
	if trim_debug and len(captured) > 40:
		display_lines = [ln for ln in captured if ln.level > logging.DEBUG]
		omitted = len(captured) - len(display_lines)
	else:
		display_lines = list(captured)
		omitted = 0

	parts: list[str] = [
		"",
		_header_line(result, index, total, counter_suffix),
		f"{DIM}{div}{RESET}",
	]

	if display_lines:
		for ln in display_lines:
			parts.append(f"  {_render_output_line(ln)}")
	else:
		parts.append(f"  {DIM}(no output){RESET}")

	if omitted:
		parts.append(f"  {DIM}... {omitted} lines omitted ...{RESET}")

	parts.append(f"  {DIM}{BOLD}LOG{RESET} {DIM}{log_path}{RESET}")
	parts.append(f"{DIM}{div}{RESET}")

	return "\n".join(parts)


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


def _on_dispatch_sequential(ev: EvDispatch) -> None:
	div = terminal_full_length_divider()
	cmd_str = " ".join(ev.job.cmd)
	print(f"{DIM}{div}{RESET}")
	print(f"{DIM}{BOLD}▶{RESET} {BOLD}{cmd_str}{RESET}")


def _on_dispatch_parallel(ev: EvDispatch) -> None:
	log_path = _rel_path(ev.job.log_file)
	print(f"{MAGENTA}{BOLD}DISPATCH{RESET} {BOLD}{ev.job.label}{RESET} {DIM}{log_path}{RESET}")


def _on_line(ev: EvLine) -> None:
	print(_render_output_line(ev.line))


def _on_complete_sequential(ev: EvComplete) -> None:
	div = terminal_full_length_divider()
	log_path = _rel_path(ev.job.log_file)

	print(f"{DIM}{BOLD}LOG{RESET} {DIM}{log_path}{RESET}")
	print(f"{DIM}{div}{RESET}")
	print(_header_line(ev.result, ev.index, ev.total))


def _on_complete_parallel(ev: EvComplete) -> None:
	print(_build_parallel_block(ev.result, ev.index, ev.total))


def _on_summary(ev: EvSummary) -> None:
	results = ev.results
	total = len(results)
	failures = [r for r in results if r.failed]

	if not failures:
		return

	div = terminal_full_length_divider()
	f = len(failures)
	s = total - f

	print(f"\n{RED}{BOLD}{div}{RESET}")
	print(f"{RED}{BOLD}  {f} job(s) failed  ({s}/{total} succeeded){RESET}")
	print(f"{RED}{BOLD}{div}{RESET}")

	for i, result in enumerate(failures, start=1):
		print(
			_build_parallel_block(
				result,
				i,
				f,
				counter_suffix="failed",
				trim_debug=True,
			)
		)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def emit(event: EvDispatch | EvLine | EvComplete | EvSummary) -> None:
	if isinstance(event, EvDispatch):
		if event.parallel:
			_on_dispatch_parallel(event)
		else:
			_on_dispatch_sequential(event)

	elif isinstance(event, EvLine):
		_on_line(event)

	elif isinstance(event, EvComplete):
		if event.parallel:
			_on_complete_parallel(event)
		else:
			_on_complete_sequential(event)

	elif isinstance(event, EvSummary):
		_on_summary(event)
