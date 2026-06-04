"""Tests for xviv.utils.display — emit() routing, _fmt_duration, _counter."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

import xviv.utils.display as display
from tests.helpers import make_job
from xviv.utils.display import (
	EvComplete,
	EvDispatch,
	EvLine,
	EvSummary,
	_counter,
	_fmt_duration,
	emit,
)
from xviv.utils.stream import OutputLine


def _make_result(job, *, returncode=0, elapsed=1.0, exc=None):
	from xviv.utils.job import JobResult

	return JobResult(job=job, returncode=returncode, elapsed=elapsed, exc=exc)


@pytest.mark.unit
class TestEmitRouting:
	def test_dispatch_sequential_routes_to_on_dispatch_sequential(self):
		job = make_job(label="test")
		ev = EvDispatch(job=job, parallel=False)
		with patch.object(display, "_on_dispatch_sequential") as m:
			emit(ev)
		m.assert_called_once_with(ev)

	def test_dispatch_parallel_routes_to_on_dispatch_parallel(self):
		job = make_job(label="test")
		ev = EvDispatch(job=job, parallel=True)
		with patch.object(display, "_on_dispatch_parallel") as m:
			emit(ev)
		m.assert_called_once_with(ev)

	def test_line_routes_to_on_line(self):
		job = make_job(label="test")
		line = OutputLine(text="hello", level=logging.DEBUG, raw="hello")
		ev = EvLine(job=job, line=line)
		with patch.object(display, "_on_line") as m:
			emit(ev)
		m.assert_called_once_with(ev)

	def test_complete_sequential_routes_to_on_complete_sequential(self):
		job = make_job(label="test")
		result = _make_result(job)
		ev = EvComplete(job=job, result=result, index=1, total=1, parallel=False)
		with patch.object(display, "_on_complete_sequential") as m:
			emit(ev)
		m.assert_called_once_with(ev)

	def test_complete_parallel_routes_to_on_complete_parallel(self):
		job = make_job(label="test")
		result = _make_result(job)
		ev = EvComplete(job=job, result=result, index=1, total=2, parallel=True)
		with patch.object(display, "_on_complete_parallel") as m:
			emit(ev)
		m.assert_called_once_with(ev)

	def test_summary_routes_to_on_summary(self):
		ev = EvSummary(results=[])
		with patch.object(display, "_on_summary") as m:
			emit(ev)
		m.assert_called_once_with(ev)


@pytest.mark.unit
class TestFmtDuration:
	def test_sub_second_shows_zero_seconds(self):
		result = _fmt_duration(0.5)
		assert "s" in result

	def test_seconds_only(self):
		result = _fmt_duration(45)
		assert "45s" in result
		assert "m" not in result

	def test_minutes_and_seconds(self):
		result = _fmt_duration(125)  # 2m 5s
		assert "2m" in result
		assert "5s" in result

	def test_exactly_one_minute(self):
		result = _fmt_duration(60)
		assert "1m" in result


@pytest.mark.unit
class TestCounter:
	def test_contains_index_and_total(self):
		result = _counter(2, 5)
		assert "2" in result
		assert "5" in result

	def test_both_numbers_present(self):
		result = _counter(7, 10)
		assert "7" in result
		assert "10" in result
