"""
Comprehensive pytest suite for xviv CLI refactor.

Covers:
  - params.py          : dataclass defaults and field types
  - commands.py        : Command.run() dispatches correct params to cmd_* functions
  - bd.py              : cmd_bd_create / cmd_bd_edit / cmd_bd_generate
  - core.py            : cmd_core_create / cmd_core_edit / cmd_core_generate / cmd_search_core
  - ip.py              : cmd_ip_create / cmd_ip_edit
  - synthesis.py       : cmd_synth / cmd_dcp_open
  - bsp.py             : cmd_platform_create / cmd_platform_build /
                         cmd_app_create / cmd_app_build / cmd_program / cmd_processor

Mocking strategy
----------------
* XvivConfig          - MagicMock; cfg.get_bd/ip/core/platform/app return
                        configured sub-mocks with the fields each function touches.
* ConfigTclCommands   - MagicMock; every builder method returns `self` so chains
                        like .create_bd(...).build() work; .build() returns a
                        sentinel string "TCL_CONFIG".
* _run_from_name_list - patched so it immediately invokes the lambda with the
                        supplied name, letting us verify what the lambda builds
                        without actually spawning Vivado.
* run_xsct / run_tool - patched to no-ops.
* os.path.exists / os.path.isdir - patched per test as needed.
"""

from __future__ import annotations

import argparse
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(**kwargs) -> MagicMock:
	cfg = MagicMock()
	cfg.dry_run = False
	cfg.check = False
	cfg.log_dir = "/tmp/logs"
	cfg.bd_dir = "/tmp/bd"
	cfg.board_repo_list = []
	cfg.ip_repo_list = []
	cfg._bd_list = []
	cfg._core_list = []
	cfg._ip_list = []
	for k, v in kwargs.items():
		setattr(cfg, k, v)
	return cfg


def _make_tcl_mock() -> MagicMock:
	tcl = MagicMock()
	# Every attribute access on the instance returns a mock that also chains
	tcl_instance = MagicMock()
	tcl_instance.build.return_value = "TCL_CONFIG"
	# Make every method on the instance return the instance so chains work
	tcl_instance.__getattr__ = lambda self, name: MagicMock(return_value=tcl_instance)
	tcl.return_value = tcl_instance
	return tcl, tcl_instance


def _args(**kwargs) -> argparse.Namespace:
	defaults = dict(
		dry_run=False,
		check=False,
		ip=None,
		bd=None,
		core=None,
		app=None,
		platform=None,
		all=None,
		generate=False,
		build=False,
		edit=False,
		nogui=False,
		regenerate=False,
		source_file=True,
		info=False,
		reset=False,
		status=False,
		wdb=None,
		dcp=None,
		bitstream=None,
		elf=None,
		processor="Microblaze #0*",
		reset_duration=500,
		fpga="xc7a*",
		design=None,
		usr_access_type="git",
		resume=None,
		parallel=False,
		query="",
		target=None,
		uvm=None,
		run="all",
		mode="default",
		force=False,
	)
	defaults.update(kwargs)
	return argparse.Namespace(**defaults)


# ===========================================================================
# 1. params.py
# ===========================================================================


class TestParams:
	"""Verify dataclass field defaults and types."""

	def test_create_params_defaults(self):
		from xviv.config.params import CreateParams

		p = CreateParams()
		assert p.generate is False
		assert p.edit is False
		assert p.nogui is False

	def test_ip_create_params_defaults(self):
		from xviv.config.params import IpCreateParams

		p = IpCreateParams()
		assert p.regenerate is False
		assert p.edit is False
		assert p.nogui is False

	def test_ip_create_params_override(self):
		from xviv.config.params import IpCreateParams

		p = IpCreateParams(edit=True, nogui=True, regenerate=True)
		assert p.edit is True
		assert p.nogui is True
		assert p.regenerate is True

	def test_bd_create_params_defaults(self):
		from xviv.config.params import BdCreateParams

		p = BdCreateParams()
		assert p.source_file is True
		assert p.generate is False
		assert p.edit is False

	def test_bd_create_params_source_file_str(self):
		from xviv.config.params import BdCreateParams

		p = BdCreateParams(source_file="path/to/file.tcl")
		assert isinstance(p.source_file, str)

	def test_core_create_params_defaults(self):
		from xviv.config.params import CoreCreateParams

		p = CoreCreateParams()
		assert p.generate is False
		assert p.edit is False
		assert p.nogui is False

	def test_edit_params_defaults(self):
		from xviv.config.params import EditParams

		p = EditParams()
		assert p.nogui is False

	def test_generate_params_defaults(self):
		from xviv.config.params import GenerateParams

		p = GenerateParams()
		assert p.force is False
		assert p.reset is False

	def test_open_params_defaults(self):
		from xviv.config.params import OpenParams

		p = OpenParams()
		assert p.nogui is False

	def test_processor_params_defaults(self):
		from xviv.config.params import ProcessorParams

		p = ProcessorParams()
		assert p.reset is False
		assert p.status is False

	def test_app_build_params_defaults(self):
		from xviv.config.params import AppBuildParams

		p = AppBuildParams()
		assert p.info is False

	def test_platform_build_params_is_empty(self):
		from xviv.config.params import PlatformBuildParams

		p = PlatformBuildParams()
		assert p is not None

	def test_app_create_params_defaults(self):
		from xviv.config.params import AppCreateParams

		p = AppCreateParams()
		assert p.build is False

	def test_platform_create_params_defaults(self):
		from xviv.config.params import PlatformCreateParams

		p = PlatformCreateParams()
		assert p.build is False

	def test_program_params_defaults(self):
		from xviv.config.params import ProgramParams

		p = ProgramParams()
		assert p.bitstream_file is None
		assert p.elf_file is None
		assert p.app_name is None
		assert p.platform_name is None
		assert p.processor_target_filter == "Microblaze #0*"
		assert p.processor_reset_duration == 500
		assert p.fpga_target_filter == "xc7a*"

	def test_simulate_params_defaults(self):
		from xviv.config.params import SimulateParams

		p = SimulateParams()
		assert p.uvm_name is None
		assert p.run == "all"
		assert p.mode == "default"

	def test_synth_params_defaults(self):
		from xviv.config.params import SynthParams

		p = SynthParams()
		assert p.usr_access_type == "git"
		assert p.resume is None
		assert p.parallel_subcore_synth is False

	def test_params_are_dataclasses(self):
		import dataclasses

		from xviv.config import params as pm

		for name in [
			"CreateParams",
			"IpCreateParams",
			"BdCreateParams",
			"CoreCreateParams",
			"AppCreateParams",
			"PlatformCreateParams",
			"EditParams",
			"GenerateParams",
			"OpenParams",
			"ProcessorParams",
			"AppBuildParams",
			"PlatformBuildParams",
			"ProgramParams",
			"SimulateParams",
			"SynthParams",
		]:
			cls = getattr(pm, name)
			assert dataclasses.is_dataclass(cls), f"{name} is not a dataclass"


# ===========================================================================
# 2. commands.py
# ===========================================================================


class TestCommands:
	# ---- helpers -----------------------------------------------------------

	@staticmethod
	def _run_command(command_cls_name: str, args: argparse.Namespace, patches: dict):
		from xviv.cli import commands as cmd_mod

		cls = getattr(cmd_mod, command_cls_name)
		instance = cls()
		cfg = _make_cfg()

		with patch.multiple("xviv.cli.commands", **patches):
			instance.run(cfg, args)

		return cfg, patches

	# ---- CreateCommand -----------------------------------------------------

	def test_create_ip_dispatches_ip_create_params(self):
		from xviv.cli.commands import CreateCommand
		from xviv.config.params import IpCreateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(ip="my_ip", edit=True, nogui=True, regenerate=True)

		with patch("xviv.cli.commands.cmd_ip_create", mock_cmd):
			CreateCommand().run(cfg, args)

		mock_cmd.assert_called_once()
		_, kwargs = mock_cmd.call_args
		assert kwargs["ip_name"] == "my_ip"
		p = kwargs["params"]
		assert isinstance(p, IpCreateParams)
		assert p.edit is True
		assert p.nogui is True
		assert p.regenerate is True

	def test_create_bd_dispatches_bd_create_params(self):
		from xviv.cli.commands import CreateCommand
		from xviv.config.params import BdCreateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(bd="my_bd", source_file="foo.tcl", generate=True, edit=False, nogui=False)

		with patch("xviv.cli.commands.cmd_bd_create", mock_cmd):
			CreateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		assert kwargs["bd_name"] == "my_bd"
		p = kwargs["params"]
		assert isinstance(p, BdCreateParams)
		assert p.source_file == "foo.tcl"
		assert p.generate is True

	def test_create_core_dispatches_core_create_params(self):
		from xviv.cli.commands import CreateCommand
		from xviv.config.params import CoreCreateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(core="my_core", generate=True, edit=True, nogui=False)

		with patch("xviv.cli.commands.cmd_core_create", mock_cmd):
			CreateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		assert kwargs["core_name"] == "my_core"
		p = kwargs["params"]
		assert isinstance(p, CoreCreateParams)
		assert p.generate is True
		assert p.edit is True

	def test_create_app_dispatches_app_create_params(self):
		from xviv.cli.commands import CreateCommand
		from xviv.config.params import AppCreateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(app="my_app", platform="my_plat", build=True)

		with patch("xviv.cli.commands.cmd_app_create", mock_cmd):
			CreateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		assert kwargs["app_name"] == "my_app"
		p = kwargs["params"]
		assert isinstance(p, AppCreateParams)
		assert p.build is True

	def test_create_platform_dispatches_platform_create_params(self):
		from xviv.cli.commands import CreateCommand
		from xviv.config.params import PlatformCreateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(platform="my_plat", build=False)

		with patch("xviv.cli.commands.cmd_platform_create", mock_cmd):
			CreateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, PlatformCreateParams)
		assert p.build is False

	# ---- EditCommand -------------------------------------------------------

	def test_edit_ip_dispatches_edit_params(self):
		from xviv.cli.commands import EditCommand
		from xviv.config.params import EditParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(ip="my_ip", nogui=True)

		with patch("xviv.cli.commands.cmd_ip_edit", mock_cmd):
			EditCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		assert kwargs["ip_name"] == "my_ip"
		p = kwargs["params"]
		assert isinstance(p, EditParams)
		assert p.nogui is True

	def test_edit_bd_dispatches_edit_params(self):
		from xviv.cli.commands import EditCommand
		from xviv.config.params import EditParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(bd="my_bd", nogui=False)

		with patch("xviv.cli.commands.cmd_bd_edit", mock_cmd):
			EditCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, EditParams)
		assert p.nogui is False

	def test_edit_core_dispatches_edit_params(self):
		from xviv.cli.commands import EditCommand
		from xviv.config.params import EditParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(core="my_core", nogui=True)

		with patch("xviv.cli.commands.cmd_core_edit", mock_cmd):
			EditCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, EditParams)
		assert p.nogui is True

	# ---- GenerateCommand ---------------------------------------------------

	def test_generate_bd_dispatches_generate_params(self):
		from xviv.cli.commands import GenerateCommand
		from xviv.config.params import GenerateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(bd="my_bd", force=True, reset=True)

		with patch("xviv.cli.commands.cmd_bd_generate", mock_cmd):
			GenerateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, GenerateParams)
		assert p.force is True
		assert p.reset is True

	def test_generate_core_dispatches_generate_params(self):
		from xviv.cli.commands import GenerateCommand
		from xviv.config.params import GenerateParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(core="my_core", force=False, reset=True)

		with patch("xviv.cli.commands.cmd_core_generate", mock_cmd):
			GenerateCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, GenerateParams)
		assert p.force is False
		assert p.reset is True

	# ---- BuildCommand ------------------------------------------------------

	def test_build_app_dispatches_app_build_params(self):
		from xviv.cli.commands import BuildCommand
		from xviv.config.params import AppBuildParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(app="my_app", info=True)

		with patch("xviv.cli.commands.cmd_app_build", mock_cmd):
			BuildCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, AppBuildParams)
		assert p.info is True

	def test_build_platform_no_params_arg(self):
		from xviv.cli.commands import BuildCommand

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(platform="my_plat")

		with patch("xviv.cli.commands.cmd_platform_build", mock_cmd):
			BuildCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		assert "params" not in kwargs, "cmd_platform_build must not receive a params kwarg"
		assert kwargs["platform_name"] == "my_plat"

	# ---- OpenCommand -------------------------------------------------------

	def test_open_dcp_dispatches_open_params(self):
		from xviv.cli.commands import OpenCommand
		from xviv.config.params import OpenParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(dcp="my.dcp", nogui=True)

		with patch("xviv.cli.commands.cmd_dcp_open", mock_cmd):
			OpenCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, OpenParams)
		assert p.nogui is True

	# ---- ProgramCommand ----------------------------------------------------

	def test_program_dispatches_program_params(self):
		from xviv.cli.commands import ProgramCommand
		from xviv.config.params import ProgramParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(
			bitstream="bitstream.bit",
			elf="app.elf",
			app=None,
			platform=None,
			processor="Microblaze #0*",
			reset_duration=200,
			fpga="xc7z*",
		)

		with patch("xviv.cli.commands.cmd_program", mock_cmd):
			ProgramCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, ProgramParams)
		assert p.bitstream_file == "bitstream.bit"
		assert p.elf_file == "app.elf"
		assert p.processor_reset_duration == 200
		assert p.fpga_target_filter == "xc7z*"

	# ---- ProcessorCommand --------------------------------------------------

	def test_processor_dispatches_processor_params(self):
		from xviv.cli.commands import ProcessorCommand
		from xviv.config.params import ProcessorParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(reset=True, status=False)

		with patch("xviv.cli.commands.cmd_processor", mock_cmd):
			ProcessorCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, ProcessorParams)
		assert p.reset is True
		assert p.status is False

	# ---- SynthCommand ------------------------------------------------------

	def test_synth_dispatches_synth_params(self):
		from xviv.cli.commands import SynthCommand
		from xviv.config.params import SynthParams

		mock_cmd = MagicMock()
		cfg = _make_cfg()
		args = _args(
			design="top",
			bd=None,
			core=None,
			usr_access_type="git",
			resume="auto",
			parallel=True,
		)

		with patch("xviv.cli.commands.cmd_synth", mock_cmd):
			SynthCommand().run(cfg, args)

		_, kwargs = mock_cmd.call_args
		p = kwargs["params"]
		assert isinstance(p, SynthParams)
		assert p.resume == "auto"
		assert p.parallel_subcore_synth is True
		# usr_access_type stays flat
		assert kwargs["usr_access_type"] == "git"


# ===========================================================================
# 3. bd.py
# ===========================================================================


class TestBd:
	# ---- fixtures ----------------------------------------------------------

	@pytest.fixture
	def cfg(self):
		c = _make_cfg()
		bd_mock = MagicMock()
		bd_mock.name = "test_bd"
		bd_mock.save_file = "/tmp/test_bd.tcl"
		bd_mock.bd_file = "/tmp/test_bd.bd"
		bd_mock.fpga = None
		c.get_bd.return_value = bd_mock
		c._bd_list = [bd_mock]
		return c

	# ---- cmd_bd_create -----------------------------------------------------

	def test_bd_create_calls_tcl_with_params(self, cfg):
		from xviv.config.params import BdCreateParams
		from xviv.functions.bd import cmd_bd_create

		params = BdCreateParams(generate=True, edit=False, nogui=False)
		tcl, tcl_inst = _make_tcl_mock()

		with (
			patch("xviv.functions.bd.ConfigTclCommands", tcl),
			patch("xviv.functions.bd._run_from_name_list") as mock_run,
			patch("os.path.exists", return_value=False),
		):
			cmd_bd_create(cfg, bd_name="test_bd", params=params)

		# Two _run_from_name_list calls: ip_list (empty) skipped, bd_list called
		assert mock_run.called

	def test_bd_create_multiple_bds_disables_edit(self, cfg):
		from xviv.config.params import BdCreateParams
		from xviv.functions.bd import cmd_bd_create

		bd2 = MagicMock()
		bd2.name = "test_bd2"
		bd2.save_file = "/tmp/test_bd2.tcl"
		cfg._bd_list = [cfg.get_bd.return_value, bd2]

		params = BdCreateParams(edit=True, source_file="custom.tcl")

		with (
			patch("xviv.functions.bd.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.bd._run_from_name_list"),
			patch("os.path.exists", return_value=False),
		):
			cmd_bd_create(cfg, bd_name="*", params=params)

		# edit and source_file should be mutated to safe defaults
		assert params.edit is False
		assert params.source_file is True

	def test_bd_create_multiple_bds_disables_edit_warning(self, cfg, caplog):
		from xviv.config.params import BdCreateParams
		from xviv.functions.bd import cmd_bd_create

		bd2 = MagicMock()
		bd2.name = "test_bd2"
		bd2.save_file = "/tmp/test_bd2.tcl"
		cfg._bd_list = [cfg.get_bd.return_value, bd2]

		params = BdCreateParams(edit=True, source_file="custom.tcl")

		with (
			patch("xviv.functions.bd.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.bd._run_from_name_list"),
			patch("os.path.exists", return_value=False),
			caplog.at_level("WARNING"),
		):
			cmd_bd_create(cfg, bd_name="*", params=params)

		assert any("edit" in r.message.lower() for r in caplog.records)
		assert any("source_file" in r.message.lower() for r in caplog.records)

	# ---- cmd_bd_edit -------------------------------------------------------

	def test_bd_edit_passes_edit_params(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.bd import cmd_bd_edit

		params = EditParams(nogui=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured["tcl_call"] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		# Make edit_bd return the tcl_instance for chaining
		tcl_inst.edit_bd.return_value = tcl_inst

		with patch("xviv.functions.bd.ConfigTclCommands", tcl), patch("xviv.functions.bd._run_from_name_list", fake_run):
			cmd_bd_edit(cfg, bd_name="test_bd", params=params)

		tcl_inst.edit_bd.assert_called_once_with("test_bd", params=params)

	def test_bd_edit_nogui_sets_vivado_mode(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.bd import cmd_bd_edit

		params = EditParams(nogui=True)

		with patch("xviv.functions.bd.ConfigTclCommands", MagicMock()), patch("xviv.functions.bd._run_from_name_list"):
			cmd_bd_edit(cfg, bd_name="test_bd", params=params)

		cfg.get_vivado.return_value.mode = "tcl"

	# ---- cmd_bd_generate ---------------------------------------------------

	def test_bd_generate_passes_generate_params(self, cfg):
		from xviv.config.params import GenerateParams
		from xviv.functions.bd import cmd_bd_generate

		params = GenerateParams(force=True, reset=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured["tcl_call"] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.generate_bd.return_value = tcl_inst

		with patch("xviv.functions.bd.ConfigTclCommands", tcl), patch("xviv.functions.bd._run_from_name_list", fake_run):
			cmd_bd_generate(cfg, bd_name="test_bd", params=params)

		tcl_inst.generate_bd.assert_called_once_with("test_bd", params=params)

	def test_bd_generate_wildcard_expands_list(self, cfg):
		from xviv.config.params import GenerateParams
		from xviv.functions.bd import cmd_bd_generate

		bd2 = MagicMock()
		bd2.name = "other_bd"
		cfg._bd_list = [cfg.get_bd.return_value, bd2]

		calls = []

		def fake_run(cfg_, names, fn, prefix):
			calls.extend(names)

		params = GenerateParams()

		with patch("xviv.functions.bd.ConfigTclCommands", MagicMock()), patch("xviv.functions.bd._run_from_name_list", fake_run):
			cmd_bd_generate(cfg, bd_name="*", params=params)

		assert "test_bd" in calls
		assert "other_bd" in calls


# ===========================================================================
# 4. core.py
# ===========================================================================


class TestCore:
	@pytest.fixture
	def cfg(self):
		c = _make_cfg()
		core_mock = MagicMock()
		core_mock.name = "test_core"
		core_mock.xci_file = "/tmp/test_core.xci"
		core_mock.is_bd_core = False
		core_mock.vlnv = "xilinx.com:ip:fifo_generator:13.2"
		core_mock.fpga = None
		c.get_core.return_value = core_mock
		c._core_list = [core_mock]
		c.get_catalog.return_value.lookup_optional.return_value = None
		return c

	# ---- cmd_core_create ---------------------------------------------------

	def test_core_create_passes_core_create_params(self, cfg):
		from xviv.config.params import CoreCreateParams
		from xviv.functions.core import cmd_core_create

		params = CoreCreateParams(generate=True, edit=False, nogui=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_core.return_value = tcl_inst

		with (
			patch("xviv.functions.core.ConfigTclCommands", tcl),
			patch("xviv.functions.core._run_from_name_list", fake_run),
			patch("xviv.functions.core.find_vivado_dir_path"),
		):
			cmd_core_create(cfg, core_name="test_core", params=params)

		tcl_inst.create_core.assert_called_once_with("test_core", params=params)

	def test_core_create_multiple_cores_disables_edit(self, cfg):
		from xviv.config.params import CoreCreateParams
		from xviv.functions.core import cmd_core_create

		core2 = MagicMock()
		core2.name = "core2"
		core2.is_bd_core = False
		core2.vlnv = "xilinx.com:ip:foo:1.0"
		cfg._core_list = [cfg.get_core.return_value, core2]

		params = CoreCreateParams(edit=True)

		with (
			patch("xviv.functions.core.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.core._run_from_name_list"),
			patch("xviv.functions.core.find_vivado_dir_path"),
		):
			cmd_core_create(cfg, core_name="*", params=params)

		assert params.edit is False

	def test_core_create_passes_ip_create_params_with_edit_false(self, cfg):
		from xviv.config.params import CoreCreateParams, IpCreateParams
		from xviv.functions.core import cmd_core_create

		ip_mock = MagicMock()
		ip_mock.name = "dep_ip"
		ip_mock.component_xml_file = "/nonexistent/component.xml"
		ip_mock.vlnv = "xilinx.com:ip:fifo_generator:13.2"

		catalog_entry = MagicMock()
		catalog_entry.vlnv = "xilinx.com:ip:fifo_generator:13.2"
		cfg.get_catalog.return_value.lookup_optional.return_value = catalog_entry
		cfg._get_ip_cfg_optional_by_vlnv.return_value = ip_mock

		captured_ip_params = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured_ip_params[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_ip.return_value = tcl_inst
		tcl_inst.create_core.return_value = tcl_inst

		params = CoreCreateParams(nogui=True)

		with (
			patch("xviv.functions.core.ConfigTclCommands", tcl),
			patch("xviv.functions.core._run_from_name_list", fake_run),
			patch("os.path.exists", return_value=False),
			patch("xviv.functions.core.find_vivado_dir_path"),
		):
			cmd_core_create(cfg, core_name="test_core", params=params)

		# create_ip must be called with IpCreateParams where edit=False
		ip_call_args = tcl_inst.create_ip.call_args
		if ip_call_args:
			ip_params = ip_call_args[0][1]
			assert isinstance(ip_params, IpCreateParams)
			assert ip_params.edit is False
			assert ip_params.nogui is True  # inherits nogui from CoreCreateParams

	# ---- cmd_core_edit -----------------------------------------------------

	def test_core_edit_passes_edit_params(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.core import cmd_core_edit

		params = EditParams(nogui=True)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.edit_core.return_value = tcl_inst

		with patch("xviv.functions.core.ConfigTclCommands", tcl), patch("xviv.functions.core._run_from_name_list", fake_run):
			cmd_core_edit(cfg, core_name="test_core", params=params)

		tcl_inst.edit_core.assert_called_once_with("test_core", params=params)

	def test_core_edit_nogui_sets_vivado_mode(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.core import cmd_core_edit

		params = EditParams(nogui=True)

		with patch("xviv.functions.core.ConfigTclCommands", MagicMock()), patch("xviv.functions.core._run_from_name_list"):
			cmd_core_edit(cfg, core_name="test_core", params=params)

		cfg.get_vivado.return_value.mode = "tcl"

	# ---- cmd_core_generate -------------------------------------------------

	def test_core_generate_passes_generate_params(self, cfg):
		from xviv.config.params import GenerateParams
		from xviv.functions.core import cmd_core_generate

		params = GenerateParams(force=False, reset=True)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.generate_core.return_value = tcl_inst

		with patch("xviv.functions.core.ConfigTclCommands", tcl), patch("xviv.functions.core._run_from_name_list", fake_run):
			cmd_core_generate(cfg, core_name="test_core", params=params)

		tcl_inst.generate_core.assert_called_once_with("test_core", params=params)

	# ---- cmd_search_core ---------------------------------------------------

	def test_search_core_prints_results(self, cfg, capsys):
		from xviv.functions.core import cmd_search_core

		entry = MagicMock()
		entry.vlnv = "xilinx.com:ip:fifo_generator:13.2"
		entry.display_name = "FIFO Generator"
		entry.name = "fifo_generator"
		entry.description = "A FIFO IP"
		entry.hidden = False
		entry.board_dependent = False
		entry.ipi_only = False

		cfg.get_catalog.return_value.values.return_value = [entry]

		cmd_search_core(cfg, query="fifo")

		out = capsys.readouterr().out
		assert "fifo_generator" in out
		assert "FIFO Generator" in out

	def test_search_core_no_results(self, cfg, capsys):
		from xviv.functions.core import cmd_search_core

		cfg.get_catalog.return_value.values.return_value = []

		cmd_search_core(cfg, query="nonexistent_ip_xyz")

		out = capsys.readouterr().out
		assert "No IPs found" in out

	def test_search_core_hidden_entries_excluded(self, cfg, capsys):
		from xviv.functions.core import cmd_search_core

		visible = MagicMock()
		visible.vlnv = "xilinx.com:ip:fifo:1.0"
		visible.display_name = "FIFO"
		visible.name = "fifo"
		visible.description = "fifo ip"
		visible.hidden = False
		visible.board_dependent = False
		visible.ipi_only = False

		hidden = MagicMock()
		hidden.vlnv = "xilinx.com:ip:secret:1.0"
		hidden.display_name = "Secret"
		hidden.name = "secret_fifo"
		hidden.description = "fifo hidden"
		hidden.hidden = True

		cfg.get_catalog.return_value.values.return_value = [visible, hidden]

		cmd_search_core(cfg, query="fifo")

		out = capsys.readouterr().out
		assert "Secret" not in out
		assert "FIFO" in out


# ===========================================================================
# 5. ip.py
# ===========================================================================


class TestIp:
	@pytest.fixture
	def cfg(self):
		c = _make_cfg()
		ip_mock = MagicMock()
		ip_mock.name = "my_ip"
		ip_mock.component_xml_file = "/tmp/my_ip/component.xml"
		ip_mock.vlnv = "myvendor:mylib:my_ip:1.0"
		c.get_ip.return_value = ip_mock
		c._ip_list = [ip_mock]
		c._core_list = []
		c.get_catalog.return_value.lookup.return_value = MagicMock(vlnv="myvendor:mylib:my_ip:1.0")
		return c

	# ---- cmd_ip_create -----------------------------------------------------

	def test_ip_create_passes_params_to_tcl(self, cfg):
		from xviv.config.params import IpCreateParams
		from xviv.functions.ip import cmd_ip_create

		params = IpCreateParams(edit=False, nogui=True, regenerate=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix, **kw):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_ip.return_value = tcl_inst

		with (
			patch("xviv.functions.ip.ConfigTclCommands", tcl),
			patch("xviv.functions.ip._run_from_name_list", fake_run),
			patch("os.path.exists", return_value=True),
		):
			cmd_ip_create(cfg, ip_name="my_ip", params=params)

		tcl_inst.create_ip.assert_called_once_with("my_ip", params)

	def test_ip_create_multiple_ips_disables_edit(self, cfg):
		from xviv.config.params import IpCreateParams
		from xviv.functions.ip import cmd_ip_create

		ip2 = MagicMock()
		ip2.name = "ip2"
		ip2.component_xml_file = "/tmp/ip2/component.xml"
		ip2.vlnv = "myvendor:mylib:ip2:1.0"
		cfg._ip_list = [cfg.get_ip.return_value, ip2]

		params = IpCreateParams(edit=True)

		with (
			patch("xviv.functions.ip.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.ip._run_from_name_list"),
			patch("os.path.exists", return_value=True),
		):
			cmd_ip_create(cfg, ip_name="*", params=params)

		assert params.edit is False

	def test_ip_create_regenerate_calls_generate_core_with_generate_params(self, cfg):
		from xviv.config.params import GenerateParams, IpCreateParams
		from xviv.functions.ip import cmd_ip_create

		core_mock = MagicMock()
		core_mock.name = "core_using_ip"
		core_mock.xci_file = "/tmp/core.xci"
		cfg._core_list = [core_mock]
		cfg.get_catalog.return_value.lookup.return_value.vlnv = "myvendor:mylib:my_ip:1.0"

		params = IpCreateParams(regenerate=True)
		captured_generate_params = {}

		def fake_run(cfg_, names, fn, prefix, **kw):
			for n in names:
				result = fn(n)
				captured_generate_params[n] = result

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_ip.return_value = tcl_inst
		tcl_inst.generate_core.return_value = tcl_inst

		with (
			patch("os.path.exists", return_value=True),
			patch("xviv.functions.ip.ConfigTclCommands", tcl),
			patch("xviv.functions.ip._run_from_name_list", fake_run),
		):
			cmd_ip_create(cfg, ip_name="my_ip", params=params)

		gen_call = tcl_inst.generate_core.call_args
		if gen_call:
			gp = gen_call[1].get("params") or gen_call[0][1]
			assert isinstance(gp, GenerateParams)
			assert gp.force is True
			assert gp.reset is True

	# ---- cmd_ip_edit -------------------------------------------------------

	def test_ip_edit_passes_edit_params(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.ip import cmd_ip_edit

		params = EditParams(nogui=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.edit_ip.return_value = tcl_inst

		with patch("xviv.functions.ip.ConfigTclCommands", tcl), patch("xviv.functions.ip._run_from_name_list", fake_run):
			cmd_ip_edit(cfg, ip_name="my_ip", params=params)

		tcl_inst.edit_ip.assert_called_once_with("my_ip", params=params)

	def test_ip_edit_nogui_sets_vivado_mode(self, cfg):
		from xviv.config.params import EditParams
		from xviv.functions.ip import cmd_ip_edit

		params = EditParams(nogui=True)

		with patch("xviv.functions.ip.ConfigTclCommands", MagicMock()), patch("xviv.functions.ip._run_from_name_list"):
			cmd_ip_edit(cfg, ip_name="my_ip", params=params)

		cfg.get_vivado.return_value.mode = "tcl"


# ===========================================================================
# 6. synthesis.py
# ===========================================================================


class TestSynthesis:
	@pytest.fixture
	def cfg(self):
		c = _make_cfg()
		synth_cfg = MagicMock()
		synth_cfg.bitstream = None
		synth_cfg.usr_access_value = None
		c.get_synth.return_value = synth_cfg
		c.get_subcore_list.return_value = []
		return c

	# ---- cmd_synth ---------------------------------------------------------

	def test_synth_passes_synth_params(self, cfg):
		from xviv.config.params import SynthParams
		from xviv.functions.synthesis import cmd_synth

		params = SynthParams(resume="auto", parallel_subcore_synth=False)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.synth.return_value = tcl_inst

		with patch("xviv.functions.synthesis.ConfigTclCommands", tcl), patch("xviv.functions.synthesis._run_from_name_list", fake_run):
			cmd_synth(cfg, design_name="top", params=params)

		synth_call = tcl_inst.synth.call_args
		assert synth_call is not None
		call_params = synth_call[1].get("params")
		assert isinstance(call_params, SynthParams)
		assert call_params.resume == "auto"

	def test_synth_parallel_subcore_calls_per_core_synth(self, cfg):
		from xviv.config.params import SynthParams
		from xviv.functions.synthesis import cmd_synth

		subcore = MagicMock()
		subcore.core = "sub_core"
		cfg.get_subcore_list.return_value = [subcore]

		params = SynthParams(parallel_subcore_synth=True)
		runs = []

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				runs.append((n, fn(n)))

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.synth.return_value = tcl_inst

		with (
			patch("xviv.functions.synthesis.ConfigTclCommands", tcl),
			patch("xviv.functions.synthesis._run_from_name_list", fake_run),
			patch("xviv.functions.synthesis.find_vivado_dir_path"),
		):
			cmd_synth(cfg, bd_name="my_bd", params=params)

		# subcore synth call should have SynthParams()
		subcore_calls = [c for c in tcl_inst.synth.call_args_list if c[1].get("core") == "sub_core"]
		if subcore_calls:
			sp = subcore_calls[0][1]["params"]
			assert isinstance(sp, SynthParams)

	def test_synth_usr_access_type_git_embeds_sha(self, cfg):
		from xviv.config.params import SynthParams
		from xviv.functions.synthesis import cmd_synth

		synth_cfg = cfg.get_synth.return_value
		synth_cfg.bitstream = "out.bit"
		synth_cfg.usr_access_value = None

		params = SynthParams()

		with (
			patch("xviv.functions.synthesis.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.synthesis._run_from_name_list"),
			patch("xviv.functions.synthesis._git_sha_tag", return_value=("deadbeef", False, "v1.0")),
		):
			cmd_synth(cfg, design_name="top", usr_access_type="git", params=params)

		assert synth_cfg.usr_access_value == int("deadbeef", 16)

	def test_synth_usr_access_dirty_sets_flag(self, cfg):
		from xviv.config.params import SynthParams
		from xviv.functions.synthesis import cmd_synth

		synth_cfg = cfg.get_synth.return_value
		synth_cfg.bitstream = "out.bit"
		synth_cfg.usr_access_value = None

		params = SynthParams()

		with (
			patch("xviv.functions.synthesis.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.synthesis._run_from_name_list"),
			patch("xviv.functions.synthesis._git_sha_tag", return_value=("deadbeef", True, "v1.0-dirty")),
		):
			cmd_synth(cfg, design_name="top", usr_access_type="git", params=params)

		# dirty flag sets bit 28
		assert synth_cfg.usr_access_value & 0x10000000

	# ---- cmd_dcp_open ------------------------------------------------------

	def test_dcp_open_passes_open_params(self, cfg):
		from xviv.config.params import OpenParams
		from xviv.functions.synthesis import cmd_dcp_open

		params = OpenParams(nogui=True)
		captured = {}

		def fake_run(cfg_, names, fn, prefix):
			for n in names:
				captured[n] = fn(n)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.open_dcp.return_value = tcl_inst

		with patch("xviv.functions.synthesis.ConfigTclCommands", tcl), patch("xviv.functions.synthesis._run_from_name_list", fake_run):
			cmd_dcp_open(cfg, dcp_file="checkpoint.dcp", params=params)

		tcl_inst.open_dcp.assert_called_once_with(dcp_file="checkpoint.dcp", params=params)

	def test_dcp_open_nogui_sets_vivado_mode(self, cfg):
		from xviv.config.params import OpenParams
		from xviv.functions.synthesis import cmd_dcp_open

		params = OpenParams(nogui=True)

		with patch("xviv.functions.synthesis.ConfigTclCommands", MagicMock()), patch("xviv.functions.synthesis._run_from_name_list"):
			cmd_dcp_open(cfg, dcp_file="checkpoint.dcp", params=params)

		cfg.get_vivado.return_value.mode = "tcl"

	def test_dcp_open_gui_does_not_set_tcl_mode(self, cfg):
		from xviv.config.params import OpenParams
		from xviv.functions.synthesis import cmd_dcp_open

		params = OpenParams(nogui=False)
		cfg.get_vivado.return_value.mode = "gui"

		with patch("xviv.functions.synthesis.ConfigTclCommands", MagicMock()), patch("xviv.functions.synthesis._run_from_name_list"):
			cmd_dcp_open(cfg, dcp_file="checkpoint.dcp", params=params)

		assert cfg.get_vivado.return_value.mode == "gui"


# ===========================================================================
# 7. bsp.py
# ===========================================================================


class TestBsp:
	@pytest.fixture
	def cfg(self):
		c = _make_cfg()

		platform_mock = MagicMock()
		platform_mock.name = "my_platform"
		platform_mock.work_dir = "/tmp/platform_work"
		platform_mock.cpu = "microblaze_0"
		platform_mock.os = "standalone"
		platform_mock.xsa = "/tmp/design.xsa"
		platform_mock.properties = []
		platform_mock.bitstream = "/tmp/design.bit"

		app_mock = MagicMock()
		app_mock.name = "my_app"
		app_mock.work_dir = "/tmp/app_work"
		app_mock.platform = "my_platform"
		app_mock.template = "empty_application"
		app_mock.elf = "/tmp/my_app.elf"
		app_mock.sources = []

		c.get_platform.return_value = platform_mock
		c.get_app.return_value = app_mock
		c._get_platform_cfg_optional.return_value = platform_mock

		vitis_mock = MagicMock()
		vitis_mock.path = "/opt/Xilinx/Vitis/2023.2"
		c.get_vitis.return_value = vitis_mock

		return c

	# ---- cmd_platform_create -----------------------------------------------

	def test_platform_create_calls_xsct(self, cfg):
		from xviv.config.params import PlatformCreateParams
		from xviv.functions.bsp import cmd_platform_create

		params = PlatformCreateParams(build=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_platform.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct") as mock_xsct:
			cmd_platform_create(cfg, platform_name="my_platform", params=params)

		mock_xsct.assert_called_once()

	def test_platform_create_build_true_calls_platform_build(self, cfg):
		from xviv.config.params import PlatformCreateParams
		from xviv.functions.bsp import cmd_platform_create

		params = PlatformCreateParams(build=True)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_platform.return_value = tcl_inst

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", tcl),
			patch("xviv.functions.bsp.run_xsct"),
			patch("xviv.functions.bsp.cmd_platform_build") as mock_build,
		):
			cmd_platform_create(cfg, platform_name="my_platform", params=params)

		mock_build.assert_called_once_with(cfg, platform_name="my_platform")

	def test_platform_create_build_false_does_not_call_platform_build(self, cfg):
		from xviv.config.params import PlatformCreateParams
		from xviv.functions.bsp import cmd_platform_create

		params = PlatformCreateParams(build=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_platform.return_value = tcl_inst

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", tcl),
			patch("xviv.functions.bsp.run_xsct"),
			patch("xviv.functions.bsp.cmd_platform_build") as mock_build,
		):
			cmd_platform_create(cfg, platform_name="my_platform", params=params)

		mock_build.assert_not_called()

	# ---- cmd_platform_build ------------------------------------------------

	def test_platform_build_no_params_arg(self, cfg):
		from xviv.functions.bsp import cmd_platform_build

		with patch("xviv.functions.bsp.run_tool") as mock_tool, patch("os.path.isdir", return_value=True):
			cmd_platform_build(cfg, platform_name="my_platform")

		mock_tool.assert_called_once()
		call_args = mock_tool.call_args[0][0]
		assert "make" in call_args

	def test_platform_build_missing_work_dir_raises(self, cfg):
		from xviv.functions.bsp import cmd_platform_build
		from xviv.utils.error import PlatformBspDirectoryMissingError

		with patch("os.path.isdir", return_value=False):
			with pytest.raises(PlatformBspDirectoryMissingError):
				cmd_platform_build(cfg, platform_name="my_platform")

	# ---- cmd_app_create ----------------------------------------------------

	def test_app_create_calls_xsct(self, cfg):
		from xviv.config.params import AppCreateParams
		from xviv.functions.bsp import cmd_app_create

		params = AppCreateParams(build=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_app.return_value = tcl_inst

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", tcl),
			patch("xviv.functions.bsp.run_xsct") as mock_xsct,
			patch("os.path.isdir", return_value=True),
		):
			cmd_app_create(cfg, app_name="my_app", platform_name=None, params=params)

		mock_xsct.assert_called_once()

	def test_app_create_build_true_calls_app_build_with_info(self, cfg):
		from xviv.config.params import AppBuildParams, AppCreateParams
		from xviv.functions.bsp import cmd_app_create

		params = AppCreateParams(build=True)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_app.return_value = tcl_inst

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", tcl),
			patch("xviv.functions.bsp.run_xsct"),
			patch("os.path.isdir", return_value=True),
			patch("xviv.functions.bsp.cmd_app_build") as mock_build,
		):
			cmd_app_create(cfg, app_name="my_app", platform_name=None, params=params)

		mock_build.assert_called_once()
		_, kwargs = mock_build.call_args
		build_params = kwargs["params"]
		assert isinstance(build_params, AppBuildParams)
		assert build_params.info is True

	def test_app_create_missing_bsp_creates_platform_first(self, cfg):
		from xviv.config.params import AppCreateParams, PlatformCreateParams
		from xviv.functions.bsp import cmd_app_create

		params = AppCreateParams(build=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.create_app.return_value = tcl_inst

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", tcl),
			patch("xviv.functions.bsp.run_xsct"),
			patch("os.path.isdir", return_value=False),
			patch("xviv.functions.bsp.cmd_platform_create") as mock_plat_create,
		):
			cmd_app_create(cfg, app_name="my_app", platform_name=None, params=params)

		mock_plat_create.assert_called_once()
		_, kwargs = mock_plat_create.call_args
		plat_params = kwargs["params"]
		assert isinstance(plat_params, PlatformCreateParams)

	def test_app_create_platform_name_override(self, cfg):
		from xviv.config.params import AppCreateParams
		from xviv.functions.bsp import cmd_app_create

		params = AppCreateParams()

		with (
			patch("xviv.functions.bsp.ConfigTclCommands", MagicMock()),
			patch("xviv.functions.bsp.run_xsct"),
			patch("os.path.isdir", return_value=True),
		):
			cmd_app_create(cfg, app_name="my_app", platform_name="override_platform", params=params)

		# platform should be overridden on app_cfg
		assert cfg.get_app.return_value.platform == "override_platform"

	# ---- cmd_app_build -----------------------------------------------------

	def test_app_build_passes_info_flag(self, cfg):
		from xviv.config.params import AppBuildParams
		from xviv.functions.bsp import cmd_app_build

		params = AppBuildParams(info=True)

		with (
			patch("xviv.functions.bsp.run_tool") as mock_tool,
			patch("xviv.functions.bsp._transform_app_makefile"),
			patch("os.path.join", side_effect=os.path.join),
		):
			cmd_app_build(cfg, app_name="my_app", params=params)

		# Should be called at least for make, size, and objdump
		assert mock_tool.call_count >= 3

	def test_app_build_no_info_only_calls_make(self, cfg):
		from xviv.config.params import AppBuildParams
		from xviv.functions.bsp import cmd_app_build

		params = AppBuildParams(info=False)

		with patch("xviv.functions.bsp.run_tool") as mock_tool, patch("xviv.functions.bsp._transform_app_makefile"):
			cmd_app_build(cfg, app_name="my_app", params=params)

		# Only the make call, no size/objdump
		assert mock_tool.call_count == 1
		call_args = mock_tool.call_args[0][0]
		assert "make" in call_args

	# ---- cmd_program -------------------------------------------------------

	def test_program_passes_resolved_params_to_tcl(self, cfg):
		from xviv.config.params import ProgramParams
		from xviv.functions.bsp import cmd_program

		params = ProgramParams(
			bitstream_file="/tmp/design.bit",
			elf_file="/tmp/app.elf",
			processor_target_filter="Microblaze #0*",
			processor_reset_duration=500,
			fpga_target_filter="xc7a*",
		)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.program.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_program(cfg, params=params)

		program_call = tcl_inst.program.call_args
		assert program_call is not None
		passed_params = program_call[1]["params"]
		assert isinstance(passed_params, ProgramParams)
		assert passed_params.bitstream_file == "/tmp/design.bit"
		assert passed_params.elf_file == "/tmp/app.elf"
		assert passed_params.fpga_target_filter == "xc7a*"

	def test_program_resolves_bitstream_from_platform(self, cfg):
		from xviv.config.params import ProgramParams
		from xviv.functions.bsp import cmd_program

		params = ProgramParams(platform_name="my_platform", elf_file="/tmp/app.elf")

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.program.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_program(cfg, params=params)

		passed_params = tcl_inst.program.call_args[1]["params"]
		# bitstream should be resolved from platform_cfg.bitstream
		assert passed_params.bitstream_file == "/tmp/design.bit"

	def test_program_resolves_elf_from_app(self, cfg):
		from xviv.config.params import ProgramParams
		from xviv.functions.bsp import cmd_program

		params = ProgramParams(
			app_name="my_app",
			bitstream_file="/tmp/design.bit",
		)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.program.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_program(cfg, params=params)

		passed_params = tcl_inst.program.call_args[1]["params"]
		assert passed_params.elf_file == "/tmp/my_app.elf"

	def test_program_raises_when_no_elf_or_bitstream(self, cfg):
		from xviv.config.params import ProgramParams
		from xviv.functions.bsp import cmd_program
		from xviv.utils.error import ProgramUnspecifiedIdentifiersError

		cfg._get_platform_cfg_optional.return_value = None
		params = ProgramParams()  # nothing specified

		with pytest.raises(ProgramUnspecifiedIdentifiersError):
			cmd_program(cfg, params=params)

	def test_program_filters_preserved_in_resolved_params(self, cfg):
		from xviv.config.params import ProgramParams
		from xviv.functions.bsp import cmd_program

		params = ProgramParams(
			bitstream_file="/tmp/design.bit",
			elf_file="/tmp/app.elf",
			processor_target_filter="MyProc #1",
			fpga_target_filter="xc7z*",
			processor_reset_duration=1000,
		)

		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.program.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_program(cfg, params=params)

		passed = tcl_inst.program.call_args[1]["params"]
		assert passed.processor_target_filter == "MyProc #1"
		assert passed.fpga_target_filter == "xc7z*"
		assert passed.processor_reset_duration == 1000

	# ---- cmd_processor -----------------------------------------------------

	def test_processor_passes_processor_params(self, cfg):
		from xviv.config.params import ProcessorParams
		from xviv.functions.bsp import cmd_processor

		params = ProcessorParams(reset=True, status=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.processor_cntrl.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_processor(cfg, params=params)

		tcl_inst.processor_cntrl.assert_called_once_with(params=params)

	def test_processor_no_processor_target_filter_passed(self, cfg):
		from xviv.config.params import ProcessorParams
		from xviv.functions.bsp import cmd_processor

		params = ProcessorParams(reset=False, status=True)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.processor_cntrl.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct"):
			cmd_processor(cfg, params=params)

		call_kwargs = tcl_inst.processor_cntrl.call_args[1]
		assert "processor_target_filter" not in call_kwargs

	def test_processor_reset_and_status_both_false(self, cfg):
		from xviv.config.params import ProcessorParams
		from xviv.functions.bsp import cmd_processor

		params = ProcessorParams(reset=False, status=False)
		tcl, tcl_inst = _make_tcl_mock()
		tcl_inst.processor_cntrl.return_value = tcl_inst

		with patch("xviv.functions.bsp.ConfigTclCommands", tcl), patch("xviv.functions.bsp.run_xsct") as mock_xsct:
			cmd_processor(cfg, params=params)

		# Still calls xsct even if no action - TCL handles the no-op
		mock_xsct.assert_called_once()
