"""Tests for xviv.utils.hash — sha512_file."""

import pytest

from xviv.utils.hash import sha512_file


@pytest.mark.unit
class TestSha512File:
	def test_existing_file_returns_128_char_hex(self, tmp_path):
		f = tmp_path / "data.bin"
		f.write_bytes(b"hello world")
		result = sha512_file(str(f))
		assert isinstance(result, str)
		assert len(result) == 128
		assert all(c in "0123456789abcdef" for c in result)

	def test_same_content_same_hash(self, tmp_path):
		a = tmp_path / "a.bin"
		b = tmp_path / "b.bin"
		a.write_bytes(b"same content")
		b.write_bytes(b"same content")
		assert sha512_file(str(a)) == sha512_file(str(b))

	def test_different_content_different_hash(self, tmp_path):
		a = tmp_path / "a.bin"
		b = tmp_path / "b.bin"
		a.write_bytes(b"content A")
		b.write_bytes(b"content B")
		assert sha512_file(str(a)) != sha512_file(str(b))

	def test_single_byte_change_different_hash(self, tmp_path):
		a = tmp_path / "a.bin"
		b = tmp_path / "b.bin"
		a.write_bytes(b"hello")
		b.write_bytes(b"Xello")
		assert sha512_file(str(a)) != sha512_file(str(b))

	def test_missing_file_returns_empty_string(self, tmp_path):
		result = sha512_file(str(tmp_path / "nonexistent.bin"))
		assert result == ""

	def test_empty_file_is_not_empty_string(self, tmp_path):
		"""Empty file must return SHA-512 of zero bytes — NOT the sentinel ''."""
		f = tmp_path / "empty.bin"
		f.write_bytes(b"")
		result = sha512_file(str(f))
		assert result != ""
		assert len(result) == 128

	def test_empty_file_differs_from_missing_file(self, tmp_path):
		empty = tmp_path / "empty.bin"
		empty.write_bytes(b"")
		assert sha512_file(str(empty)) != sha512_file(str(tmp_path / "missing.bin"))
