from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from xviv.utils.term import terminal_full_length_divider
from xviv.utils.theme import theme_cfg

if TYPE_CHECKING:
	from xviv.utils.job import Job, JobResult
	from xviv.utils.stream import OutputLine


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


_prev_level: int | None = None


def _render_output_line(line: OutputLine) -> str:
	global _prev_level

	lvl = line.level if _prev_level is None else _prev_level

	if line.text.strip().endswith(":"):
		_prev_level = lvl
	else:
		_prev_level = None

	if lvl != logging.DEBUG and theme_cfg._supports_color():
		if lvl in [logging.ERROR, logging.WARNING]:
			return theme_cfg.level(line.raw, lvl)
		else:
			return theme_cfg.level(line.raw[: line.raw.index(line.text)], lvl) + line.text

	return line.raw


def _counter(index: int, total: int, suffix: str = "") -> str:
	mid = f"{index}/{total} {suffix}".rstrip() if suffix else f"{index}/{total}"
	return f"{theme_cfg.dim('[')}{mid}{theme_cfg.dim(']')}"


def _header_line(result: JobResult, index: int, total: int, suffix: str = "") -> str:
	ctr = _counter(index, total, suffix)
	label = theme_cfg.bold(result.job.label)
	elapsed = result.elapsed
	dur = _fmt_duration(elapsed) if elapsed is not None else "?"

	verb = ""
	status = ""
	if result.returncode is not None:
		if result.succeeded:
			verb = "finished in"
			status = theme_cfg.bold(theme_cfg.green("OK"))
		else:
			verb = "after"
			status = theme_cfg.bold(theme_cfg.red("FAILED"))

	timing = theme_cfg.dim(f"{verb} {dur}")
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
		theme_cfg.dim(div),
	]

	if display_lines:
		for ln in display_lines:
			parts.append(f"  {_render_output_line(ln)}")
	else:
		parts.append(theme_cfg.dim("  (no output)"))

	if omitted:
		parts.append(theme_cfg.dim(f"  ... {omitted} lines omitted ..."))

	if log_path:
		parts.append(f"  {theme_cfg.bold(theme_cfg.dim('LOG'))} {theme_cfg.dim('LOG')}")
	parts.append(theme_cfg.dim(div))

	return "\n".join(parts)


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------


def _on_dispatch_sequential(ev: EvDispatch) -> None:
	div = terminal_full_length_divider()
	cmd_str = " ".join(ev.job.cmd)
	if not ev.job.detach:
		print(theme_cfg.dim(div))

	print(theme_cfg.bold(theme_cfg.dim("▶")), theme_cfg.bold(cmd_str))


def _on_dispatch_parallel(ev: EvDispatch) -> None:
	log_path = _rel_path(ev.job.log_file)
	print(theme_cfg.bold(theme_cfg.magenta("DISPATCH")), theme_cfg.bold(ev.job.label), theme_cfg.dim(log_path))


def _on_line(ev: EvLine) -> None:
	print(_render_output_line(ev.line))


def _on_complete_sequential(ev: EvComplete) -> None:
	div = terminal_full_length_divider()
	log_path = _rel_path(ev.job.log_file)

	if not ev.job.detach:
		print(theme_cfg.bold(theme_cfg.dim("LOG")), theme_cfg.dim(log_path))
		print(theme_cfg.dim(div))
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

	print()
	print(theme_cfg.bold(theme_cfg.red(div)))
	print(theme_cfg.bold(theme_cfg.red(f" {f} job(s) failed  ({s}/{total} succeeded)")))
	print(theme_cfg.bold(theme_cfg.red(div)))

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
