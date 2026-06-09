"""Tests for xviv.utils.fs - resolve_globs, is_stale, combined_checksum."""

import os
import time

import pytest

from xviv.utils.fs import combined_checksum, is_stale, resolve_globs


@pytest.mark.unit
class TestResolveGlobs:
	def test_plain_path_returns_absolute(self, tmp_path):
		f = tmp_path / "top.sv"
		f.write_text("module top; endmodule")
		result = resolve_globs(["top.sv"], str(tmp_path))
		assert len(result) == 1
		assert os.path.isabs(result[0])
		assert result[0] == str(f)

	def test_wildcard_matches_multiple_sorted(self, tmp_path):
		for name in ["b.sv", "a.sv", "c.sv"]:
			(tmp_path / name).write_text("")
		result = resolve_globs(["*.sv"], str(tmp_path))
		assert len(result) == 3
		assert result == sorted(result)

	def test_no_match_returns_empty(self, tmp_path):
		result = resolve_globs(["*.sv"], str(tmp_path))
		assert result == []

	def test_recursive_glob(self, tmp_path):
		sub = tmp_path / "sub"
		sub.mkdir()
		(tmp_path / "top.sv").write_text("")
		(sub / "sub.sv").write_text("")
		result = resolve_globs(["**/*.sv"], str(tmp_path))
		assert len(result) == 2

	def test_multiple_patterns(self, tmp_path):
		(tmp_path / "a.sv").write_text("")
		(tmp_path / "b.v").write_text("")
		result = resolve_globs(["a.sv", "b.v"], str(tmp_path))
		assert len(result) == 2


@pytest.mark.unit
class TestIsStale:
	def test_dst_absent_returns_true(self, tmp_path):
		src = tmp_path / "src.sv"
		src.write_text("")
		assert is_stale(str(src), str(tmp_path / "dst.bit")) is True

	def test_src_absent_exit_on_fail_raises(self, tmp_path):
		dst = tmp_path / "dst.bit"
		dst.write_text("")
		with pytest.raises(FileNotFoundError):
			is_stale(str(tmp_path / "missing.sv"), str(dst), exit_on_fail=True)

	def test_src_absent_no_exit_returns_true(self, tmp_path):
		dst = tmp_path / "dst.bit"
		dst.write_text("")
		result = is_stale(str(tmp_path / "missing.sv"), str(dst), exit_on_fail=False)
		assert result is True

	def test_src_newer_returns_true(self, tmp_path):
		dst = tmp_path / "dst.bit"
		dst.write_text("")
		time.sleep(0.05)
		src = tmp_path / "src.sv"
		src.write_text("")
		assert is_stale(str(src), str(dst)) is True

	def test_dst_newer_returns_false(self, tmp_path):
		src = tmp_path / "src.sv"
		src.write_text("")
		time.sleep(0.05)
		dst = tmp_path / "dst.bit"
		dst.write_text("")
		assert is_stale(str(src), str(dst)) is False


@pytest.mark.unit
class TestCombinedChecksum:
	def test_same_files_same_hash(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("content")
		h1 = combined_checksum([str(f)])
		h2 = combined_checksum([str(f)])
		assert h1 == h2

	def test_byte_change_different_hash(self, tmp_path):
		a = tmp_path / "a.sv"
		b = tmp_path / "b.sv"
		a.write_text("hello")
		b.write_text("Xello")
		assert combined_checksum([str(a)]) != combined_checksum([str(b)])

	def test_multiple_files_order_matters(self, tmp_path):
		a = tmp_path / "a.sv"
		b = tmp_path / "b.sv"
		a.write_text("AAA")
		b.write_text("BBB")
		h_ab = combined_checksum([str(a), str(b)])
		h_ba = combined_checksum([str(b), str(a)])
		assert h_ab != h_ba
