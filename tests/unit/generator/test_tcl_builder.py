"""Tests for xviv.generator.tcl.builder — ConfigTclBuilder primitives."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from xviv.generator.tcl.builder import ConfigTclBuilder


def _builder(tmp_path=None):
	"""Construct a ConfigTclBuilder with a minimal mock config."""
	cfg = MagicMock()
	if tmp_path:
		cfg.work_dir = str(tmp_path)
	return ConfigTclBuilder(cfg)


@pytest.mark.unit
class TestBuild:
	def test_build_returns_none_with_no_pushes(self, tmp_path):
		b = _builder(tmp_path)
		assert b.build() is None

	def test_build_returns_string_after_push(self, tmp_path):
		b = _builder(tmp_path)
		b._set("x", "1")
		result = b.build()
		assert isinstance(result, str)
		assert result.endswith("\n")

	def test_clear_resets_to_none(self, tmp_path):
		b = _builder(tmp_path)
		b._set("x", "1")
		b._clear()
		assert b.build() is None


@pytest.mark.unit
class TestPrimitives:
	def test_set_emits_set_command(self, tmp_path):
		b = _builder(tmp_path)
		b._set("myvar", "myval")
		assert "set myvar myval" in b.build()

	def test_if_emits_if_block(self, tmp_path):
		b = _builder(tmp_path)
		b._if("$x == 1", lambda c: c._set("y", "2"))
		tcl = b.build()
		assert "if {$x == 1}" in tcl
		assert "set y 2" in tcl

	def test_proc_emits_proc_definition(self, tmp_path):
		b = _builder(tmp_path)
		b._proc("my_proc", "arg1 arg2", lambda c: c._set("result", "$arg1"))
		tcl = b.build()
		assert "proc my_proc {arg1 arg2}" in tcl
		assert "set result $arg1" in tcl

	def test_foreach_emits_foreach_loop(self, tmp_path):
		b = _builder(tmp_path)
		b._foreach(
			"item",
			iter_lambda=lambda c: c._set("items", "[list a b c]"),
			body_func=lambda c: c._puts("$item"),
		)
		tcl = b.build()
		assert "foreach item" in tcl

	def test_while_emits_while_loop(self, tmp_path):
		b = _builder(tmp_path)
		b._while("$i < 10", lambda c: c._set("i", "[expr {$i + 1}]"))
		tcl = b.build()
		assert "while {$i < 10}" in tcl

	def test_set_exec_emits_set_with_brackets(self, tmp_path):
		b = _builder(tmp_path)
		b._set_exec("result", lambda c: c._set("x", "1"))
		tcl = b.build()
		assert "set result [" in tcl

	def test_append_emits_append(self, tmp_path):
		b = _builder(tmp_path)
		b._append("mylist", "a", "b")
		assert "append mylist a b" in b.build()

	def test_global_emits_global(self, tmp_path):
		b = _builder(tmp_path)
		b._global("var1", "var2")
		assert "global var1 var2" in b.build()

	def test_puts_emits_puts(self, tmp_path):
		b = _builder(tmp_path)
		b._puts("hello world")
		assert "puts hello world" in b.build()

	def test_puts_with_channel(self, tmp_path):
		b = _builder(tmp_path)
		b._puts("hello", channel="stderr")
		assert "puts stderr hello" in b.build()

	def test_fileevent_emits_fileevent(self, tmp_path):
		b = _builder(tmp_path)
		b._fileevent("$fh", "readable", "my_handler")
		assert "fileevent $fh readable my_handler" in b.build()

	def test_after_emits_after(self, tmp_path):
		b = _builder(tmp_path)
		b._after(1000)
		assert "after 1000" in b.build()


@pytest.mark.unit
class TestIndentation:
	def test_nested_if_inside_proc_indented(self, tmp_path):
		b = _builder(tmp_path)
		b._proc("outer", "", lambda c: c._if("$x", lambda ic: ic._set("y", "1")))
		tcl = b.build()
		lines = tcl.splitlines()
		# The inner set should be indented more than the if
		if_lines = [i for i in lines if "if {$x}" in i]
		set_lines = [i for i in lines if "set y 1" in i]
		assert if_lines and set_lines
		# set_y line should have more leading tabs
		if_indent = len(if_lines[0]) - len(if_lines[0].lstrip("\t"))
		set_indent = len(set_lines[0]) - len(set_lines[0].lstrip("\t"))
		assert set_indent > if_indent


@pytest.mark.unit
class TestFileMkdir:
	def test_file_mkdir_dirname_emits_file_mkdir(self, tmp_path):
		b = _builder(tmp_path)
		b._file_mkdir_dirname_file("/some/path/file.dcp")
		tcl = b.build()
		assert "file mkdir" in tcl
		# It emits mkdir of the *dirname* (Python-computed), not a TCL dirname call
		assert "/some/path" in tcl
