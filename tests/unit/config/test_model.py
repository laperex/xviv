"""Tests for xviv.config.model — SourceFile, derived properties, Lockable serialization."""

from __future__ import annotations

import os

import pytest

from xviv.config.model import SourceFile, lock_serialize


@pytest.mark.unit
class TestSourceFile:
	def test_from_stages_sets_file_and_used_in(self, tmp_path):
		f = tmp_path / "top.sv"
		f.write_text("module top; endmodule")
		sf = SourceFile.from_stages(str(f), ["synth", "impl"])
		assert sf.file == str(f)
		assert sf.used_in == frozenset({"synth", "impl"})

	def test_post_init_makes_path_absolute(self, tmp_path):
		f = tmp_path / "mod.sv"
		f.write_text("")
		sf = SourceFile(file=str(f), used_in=frozenset({"synth"}))
		assert os.path.isabs(sf.file)

	def test_used_in_synth_property(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("")
		sf = SourceFile.from_stages(str(f), ["synth"])
		assert sf.used_in_synth is True
		assert sf.used_in_impl is False

	def test_used_in_impl_property(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("")
		sf = SourceFile.from_stages(str(f), ["impl"])
		assert sf.used_in_impl is True
		assert sf.used_in_synth is False

	def test_used_in_sim_property(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("")
		sf = SourceFile.from_stages(str(f), ["sim"])
		assert sf.used_in_sim is True

	def test_used_in_ooc_property(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("")
		sf = SourceFile.from_stages(str(f), ["ooc"])
		assert sf.used_in_ooc is True

	def test_uses_method(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("")
		sf = SourceFile.from_stages(str(f), ["synth", "sim"])
		assert sf.uses("synth") is True
		assert sf.uses("impl") is False
		assert sf.uses("sim") is True

	def test_hash_populated_for_existing_file(self, tmp_path):
		f = tmp_path / "f.sv"
		f.write_text("content")
		sf = SourceFile(file=str(f), used_in=frozenset({"synth"}))
		assert sf.hash != ""
		assert len(sf.hash) == 128

	def test_hash_empty_for_missing_file(self, tmp_path):
		sf = SourceFile(file=str(tmp_path / "missing.sv"), used_in=frozenset({"synth"}))
		assert sf.hash == ""


@pytest.mark.unit
class TestIpConfigDerived:
	def _make_ip(self, name="my_ip", version="1.0", repo="/tmp/repo"):
		from xviv.config.model import IpConfig

		return IpConfig(
			vendor="user.org",
			library="user",
			version=version,
			vlnv=f"user.org:user:{name}:{version}",
			repo=repo,
			name=name,
			top=name,
			fpga="artix",
			sources=[],
		)

	def test_vid_property(self):
		ip = self._make_ip(name="ip_rgb", version="2.0")
		assert ip.vid == "ip_rgb_2_0"

	def test_vid_replaces_dots(self):
		ip = self._make_ip(name="myip", version="1.2.3")
		assert "." not in ip.vid
		assert "1_2_3" in ip.vid

	def test_component_xml_file_under_repo_vid(self):
		ip = self._make_ip(name="my_ip", version="1.0", repo="/repos/ip")
		xml = ip.component_xml_file
		assert os.path.isabs(xml)
		assert "my_ip_1_0" in xml
		assert xml.endswith("component.xml")


@pytest.mark.unit
class TestCoreConfigDerived:
	def _make_core(self, xci_file: str):
		from xviv.config.model import CoreConfig

		return CoreConfig(name="my_core", vlnv="user.org:user:my_core:1.0", xci_file=xci_file, fpga="artix")

	def test_is_bd_core_false_when_not_in_bd_structure(self, tmp_path):
		xci = str(tmp_path / "cores" / "my_core" / "my_core.xci")
		core = self._make_core(xci)
		assert core.is_bd_core is False

	def test_is_bd_core_true_when_under_bd_ip_dir_with_bd_sibling(self, tmp_path):
		# Structure: <bd_dir>/<bd_name>/ip/<core_name>/<core_name>.xci
		# with <bd_dir>/<bd_name>/<bd_name>.bd sibling
		bd_dir = tmp_path / "bd_designs" / "my_design"
		ip_dir = bd_dir / "ip" / "my_core"
		ip_dir.mkdir(parents=True)
		bd_file = bd_dir / "my_design.bd"
		bd_file.write_text("{}")
		xci = str(ip_dir / "my_core.xci")
		core = self._make_core(xci)
		assert core.is_bd_core is True


@pytest.mark.unit
class TestLockSerialize:
	def test_relpath_field_becomes_relative(self, tmp_path):
		from xviv.config.model import ProjectConfig

		cfg = ProjectConfig(
			work_dir=str(tmp_path / "build"),
			log_file=str(tmp_path / "build" / "xviv.log"),
			board_repo=[],
			ip_repo=[],
		)
		d = lock_serialize(cfg, str(tmp_path))
		assert not os.path.isabs(d["work_dir"])
		assert d["work_dir"].startswith("./")

	def test_sources_field_serialized_as_dicts(self, tmp_path):
		f = tmp_path / "top.sv"
		f.write_text("module top; endmodule")
		sf = SourceFile.from_stages(str(f), ["synth", "sim"])

		import dataclasses

		@dataclasses.dataclass
		class FakeConfig:
			sources: list = dataclasses.field(
				default_factory=list,
				metadata={"lock": "sources"},
			)

		obj = FakeConfig(sources=[sf])
		d = lock_serialize(obj, str(tmp_path))
		assert isinstance(d["sources"], list)
		assert len(d["sources"]) == 1
		entry = d["sources"][0]
		assert "file" in entry
		assert "hash" in entry
		assert "used_in" in entry
		assert isinstance(entry["used_in"], list)

	def test_none_values_preserved(self, tmp_path):
		import dataclasses

		@dataclasses.dataclass
		class FakeConfig:
			value: str | None = None

		obj = FakeConfig(value=None)
		d = lock_serialize(obj, str(tmp_path))
		assert d["value"] is None
