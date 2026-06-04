"""Tests for XvivConfig._resolve_sources, _resolve_fpga, and related helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from xviv.config.project import XvivConfig
from xviv.utils.error import (
	FpgaResolveError,
	SourceSpecMissingKeyError,
	SourceSpecUnknownStageError,
)


@pytest.fixture(autouse=True)
def _no_pyslang(monkeypatch):
	monkeypatch.setattr("xviv.generator.wrapper.SystemVerilogWrapper", MagicMock())


def _cfg(tmp_path):
	pf = tmp_path / "project.toml"
	pf.write_text("")
	cfg = XvivConfig(str(pf))
	cfg.add_fpga_cfg("artix", fpga_part="xc7a100tcsg324-1")
	return cfg


@pytest.mark.unit
class TestResolveSources:
	def test_string_source_returns_source_file(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("module top; endmodule")
		result = cfg._resolve_sources([str(f)])
		assert len(result) == 1
		assert result[0].file == str(f)

	def test_string_source_default_stages(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		result = cfg._resolve_sources([str(f)])
		sf = result[0]
		assert sf.used_in_synth is True
		assert sf.used_in_impl is True
		assert sf.used_in_sim is True
		assert sf.used_in_ooc is True

	def test_dict_source_with_used_in(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		result = cfg._resolve_sources([{"file": str(f), "used_in": ["synth"]}])
		assert len(result) == 1
		assert result[0].used_in_synth is True
		assert result[0].used_in_sim is False

	def test_unknown_stage_raises_with_name(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		with pytest.raises(SourceSpecUnknownStageError) as exc_info:
			cfg._resolve_sources([{"file": str(f), "used_in": ["badstage"]}])
		assert "badstage" in str(exc_info.value)

	def test_missing_used_in_key_raises_with_key(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		with pytest.raises(SourceSpecMissingKeyError) as exc_info:
			cfg._resolve_sources([{"file": str(f)}])
		assert "used_in" in str(exc_info.value)

	def test_missing_files_key_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises(SourceSpecMissingKeyError) as exc_info:
			cfg._resolve_sources([{"used_in": ["synth"]}])
		assert "file" in str(exc_info.value).lower()

	def test_glob_no_match_returns_empty(self, tmp_path):
		cfg = _cfg(tmp_path)
		result = cfg._resolve_sources(["*.sv"])
		assert result == []

	def test_used_in_ooc_false_excludes_ooc(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		result = cfg._resolve_sources([str(f)], used_in_ooc=False)
		assert result[0].used_in_ooc is False
		assert result[0].used_in_synth is True

	def test_used_in_sim_false_excludes_sim(self, tmp_path):
		cfg = _cfg(tmp_path)
		f = tmp_path / "top.sv"
		f.write_text("")
		result = cfg._resolve_sources([str(f)], used_in_sim=False)
		assert result[0].used_in_sim is False

	def test_dict_with_files_list(self, tmp_path):
		cfg = _cfg(tmp_path)
		f1 = tmp_path / "a.sv"
		f2 = tmp_path / "b.sv"
		f1.write_text("")
		f2.write_text("")
		result = cfg._resolve_sources([{"files": [str(f1), str(f2)], "used_in": ["synth"]}])
		assert len(result) == 2


@pytest.mark.unit
class TestResolveFpga:
	def test_none_returns_default_fpga_name(self, tmp_path):
		cfg = _cfg(tmp_path)
		resolved = cfg._resolve_fpga(None)
		assert resolved == "artix"

	def test_explicit_name_returns_that_name(self, tmp_path):
		cfg = _cfg(tmp_path)
		resolved = cfg._resolve_fpga("artix")
		assert resolved == "artix"

	def test_nonexistent_fpga_raises(self, tmp_path):
		cfg = _cfg(tmp_path)
		with pytest.raises(FpgaResolveError):
			cfg._resolve_fpga("nonexistent_fpga")
