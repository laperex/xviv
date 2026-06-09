"""Tests for xviv.parsers.bd_json - get_bd_core_list."""

from __future__ import annotations

import json
import os

import pytest

from xviv.parsers.bd_json import get_bd_core_list

FIXTURES = os.path.join(os.path.dirname(__file__), "../../fixtures/bd")


@pytest.mark.unit
class TestFlatBd:
	def test_flat_bd_returns_two_cores(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		assert len(result) == 2

	def test_flat_bd_tuple_structure(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		xci_name, xci_file, vlnv, inst_hier_path = result[0]
		assert isinstance(xci_name, str)
		assert isinstance(vlnv, str)
		assert isinstance(inst_hier_path, str)

	def test_flat_bd_xci_file_is_absolute(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		for _, xci_file, _, _ in result:
			if xci_file:
				assert os.path.isabs(xci_file)

	def test_flat_bd_xci_file_joined_to_bd_dir(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		bd_dir = os.path.dirname(bd_file)
		for _, xci_file, _, _ in result:
			if xci_file:
				assert xci_file.startswith(bd_dir)

	def test_flat_bd_vlnv_values(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		vlnvs = {r[2] for r in result}
		assert "user.org:user:ip_rgb_to_hsv:1.0" in vlnvs
		assert "user.org:user:ip_inrange:1.0" in vlnvs

	def test_flat_bd_inst_hier_paths(self):
		bd_file = os.path.join(FIXTURES, "flat.bd.json")
		result = get_bd_core_list(bd_file)
		paths = {r[3] for r in result}
		assert "design_1_i/ip_rgb_to_hsv_0" in paths
		assert "design_1_i/ip_inrange_0" in paths


@pytest.mark.unit
class TestNestedBd:
	def test_nested_returns_only_leaf_nodes(self):
		bd_file = os.path.join(FIXTURES, "nested.bd.json")
		result = get_bd_core_list(bd_file)
		names = [r[0] for r in result]
		# container with 'components' key should NOT appear
		assert "container_hier" not in names

	def test_nested_leaf_is_present(self):
		bd_file = os.path.join(FIXTURES, "nested.bd.json")
		result = get_bd_core_list(bd_file)
		names = [r[0] for r in result]
		assert "leaf_ip_0" in names

	def test_standalone_ip_is_present(self):
		bd_file = os.path.join(FIXTURES, "nested.bd.json")
		result = get_bd_core_list(bd_file)
		names = [r[0] for r in result]
		assert "standalone_ip" in names

	def test_nested_returns_two_leaves(self):
		bd_file = os.path.join(FIXTURES, "nested.bd.json")
		result = get_bd_core_list(bd_file)
		assert len(result) == 2


@pytest.mark.unit
class TestEmptyBd:
	def test_empty_file_returns_empty_list(self, tmp_path):
		bd_file = tmp_path / "empty.bd.json"
		bd_file.write_text("{}")
		result = get_bd_core_list(str(bd_file))
		assert result == []

	def test_blank_content_returns_empty_list(self, tmp_path):
		bd_file = tmp_path / "blank.bd.json"
		bd_file.write_text("   ")
		result = get_bd_core_list(str(bd_file))
		assert result == []


@pytest.mark.unit
class TestXciFilePath:
	def test_null_xci_path_gives_none(self, tmp_path):
		data = {
			"ip_0": {
				"vlnv": "user.org:user:ip:1.0",
				"xci_name": "ip_0",
				"xci_path": None,
				"inst_hier_path": "design/ip_0",
			}
		}
		bd_file = tmp_path / "test.bd.json"
		bd_file.write_text(json.dumps(data))
		result = get_bd_core_list(str(bd_file))
		assert len(result) == 1
		_, xci_file, _, _ = result[0]
		assert xci_file is None

	def test_xci_path_joined_to_bd_directory(self, tmp_path):
		data = {
			"ip_0": {
				"vlnv": "user.org:user:ip:1.0",
				"xci_name": "ip_0",
				"xci_path": "ip/ip_0/ip_0.xci",
				"inst_hier_path": "design/ip_0",
			}
		}
		bd_file = tmp_path / "test.bd.json"
		bd_file.write_text(json.dumps(data))
		result = get_bd_core_list(str(bd_file))
		_, xci_file, _, _ = result[0]
		assert xci_file is not None
		assert str(tmp_path) in xci_file
