import os
import stat
from unittest.mock import patch

import pytest

from xviv.utils.fifo import _ensure_fifo, _fifo_send
from xviv.utils.git import _git_sha_tag
from xviv.utils.parallel import run_parallel


def test_git_sha_tag_returns_empty_tuple_on_rev_parse_failure():
    with patch("xviv.utils.git.subprocess.check_output", side_effect=RuntimeError("boom")):
        assert _git_sha_tag() == ("", False, "")


def test_git_sha_tag_marks_clean_repo():
    with patch(
        "xviv.utils.git.subprocess.check_output",
        side_effect=[b"abc1234\n", b""],
    ):
        assert _git_sha_tag() == ("abc1234", False, "abc1234")


def test_git_sha_tag_marks_dirty_repo():
    with patch(
        "xviv.utils.git.subprocess.check_output",
        side_effect=[b"abc1234\n", b" M foo.py\n"],
    ):
        assert _git_sha_tag() == ("abc1234", True, "abc1234_dirty")


def test_run_parallel_executes_all_jobs():
    done = []

    def a():
        done.append("a")

    def b():
        done.append("b")

    run_parallel([(a, "job-a"), (b, "job-b")], max_workers=2)
    assert sorted(done) == ["a", "b"]


def test_run_parallel_prints_stage_messages(capsys):
    run_parallel([(lambda: None, "job-a")], stage=3, max_workers=1)
    assert "[stage 3] job-a done" in capsys.readouterr().out


def test_run_parallel_propagates_job_exception():
    def fail():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        run_parallel([(fail, "bad-job")], max_workers=1)


def test_ensure_fifo_creates_fifo_and_parent_dir(tmp_path):
    fifo_path = tmp_path / "nested" / "ctrl.fifo"
    _ensure_fifo(str(fifo_path))
    mode = os.stat(fifo_path).st_mode
    assert stat.S_ISFIFO(mode)


def test_ensure_fifo_replaces_non_fifo_file(tmp_path):
    path = tmp_path / "ctrl"
    path.write_text("not fifo")
    _ensure_fifo(str(path))
    mode = os.stat(path).st_mode
    assert stat.S_ISFIFO(mode)


def test_fifo_send_logs_warning_when_open_fails(caplog):
    with patch("xviv.utils.fifo.os.open", side_effect=OSError("no reader")):
        _fifo_send("/tmp/does-not-matter", "run")
    assert "FIFO send failed" in caplog.text
