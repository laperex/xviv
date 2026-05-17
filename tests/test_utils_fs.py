import hashlib
import os
import time

import pytest

from xviv.utils.fs import (
    assert_file_exists,
    combined_checksum,
    is_stale,
    is_stale_list,
    resolve_globs,
)


def test_resolve_globs_handles_literals_and_wildcards(tmp_path):
    literal = tmp_path / "literal.txt"
    wildcard_a = tmp_path / "a.sv"
    wildcard_b = tmp_path / "b.sv"
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "c.sv").write_text("ignore me")
    literal.write_text("L")
    wildcard_a.write_text("A")
    wildcard_b.write_text("B")

    out = resolve_globs(["literal.txt", "*.sv"], str(tmp_path))

    assert str(literal.resolve()) in out
    assert str(wildcard_a.resolve()) in out
    assert str(wildcard_b.resolve()) in out
    assert len(out) == 3


def test_is_stale_true_when_dst_missing(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("x")
    assert is_stale(str(src), str(tmp_path / "missing.txt")) is True


def test_is_stale_system_exit_when_src_missing_and_exit_on_fail(tmp_path):
    dst = tmp_path / "dst.txt"
    dst.write_text("x")

    with pytest.raises(SystemExit):
        is_stale(str(tmp_path / "missing.txt"), str(dst), exit_on_fail=True)


def test_is_stale_true_when_src_newer_false_when_dst_newer(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("new")
    dst.write_text("old")

    now = time.time()
    os.utime(dst, (now - 20, now - 20))
    os.utime(src, (now - 10, now - 10))
    assert is_stale(str(src), str(dst)) is True

    os.utime(src, (now - 30, now - 30))
    os.utime(dst, (now - 5, now - 5))
    assert is_stale(str(src), str(dst)) is False


def test_is_stale_list_true_if_any_dst_stale(tmp_path):
    src = tmp_path / "src.txt"
    dst_old = tmp_path / "old.txt"
    dst_missing = tmp_path / "missing.txt"
    src.write_text("x")
    dst_old.write_text("x")

    now = time.time()
    os.utime(dst_old, (now - 20, now - 20))
    os.utime(src, (now - 10, now - 10))

    assert is_stale_list(str(src), [str(dst_old), str(dst_missing)]) is True


def test_combined_checksum_matches_expected(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"123")
    b.write_bytes(b"456")

    got = combined_checksum([str(a), str(b)])

    h = hashlib.sha256()
    h.update(b"123")
    h.update(b"456")
    assert got == h.hexdigest()


def test_assert_file_exists(tmp_path):
    present = tmp_path / "present.txt"
    present.write_text("ok")
    assert_file_exists(str(present))

    with pytest.raises(AssertionError):
        assert_file_exists(str(tmp_path / "missing.txt"))
