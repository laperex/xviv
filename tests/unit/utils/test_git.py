"""Tests for xviv.utils.git — _git_sha_tag."""

from unittest.mock import patch

import pytest

from xviv.utils.git import _git_sha_tag


@pytest.mark.unit
class TestCleanRepo:
	def test_returns_7_char_hex_sha(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"abc1234\n", b""]
			sha, dirty, tag = _git_sha_tag()
		assert sha == "abc1234"
		assert len(sha) == 7

	def test_clean_repo_dirty_is_false(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"abc1234\n", b""]
			_, dirty, _ = _git_sha_tag()
		assert dirty is False

	def test_clean_repo_tag_equals_sha(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"abc1234\n", b""]
			sha, _, tag = _git_sha_tag()
		assert tag == sha


@pytest.mark.unit
class TestDirtyRepo:
	def test_dirty_is_true_when_status_nonempty(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"abc1234\n", b" M src/something.py\n"]
			_, dirty, _ = _git_sha_tag()
		assert dirty is True

	def test_tag_has_dirty_suffix(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"abc1234\n", b" M file.py\n"]
			sha, _, tag = _git_sha_tag()
		assert tag == f"{sha}_dirty"


@pytest.mark.unit
class TestNoRepo:
	def test_no_git_returns_empty_strings(self):
		with patch("subprocess.check_output", side_effect=FileNotFoundError()):
			sha, dirty, tag = _git_sha_tag()
		assert sha == ""
		assert tag == ""
		assert dirty is False

	def test_non_repo_directory_returns_empty(self):
		with patch("subprocess.check_output", side_effect=Exception("not a repo")):
			sha, dirty, tag = _git_sha_tag()
		assert sha == ""


@pytest.mark.unit
class TestWhitespace:
	def test_trailing_newline_stripped(self):
		with patch("subprocess.check_output") as mock_co:
			mock_co.side_effect = [b"deadbee\n", b""]
			sha, _, _ = _git_sha_tag()
		assert sha == "deadbee"
		assert "\n" not in sha
