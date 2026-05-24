from __future__ import annotations

import os
import re
import time
from unittest.mock import MagicMock, patch

import pytest

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils import error

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
	config_file = tmp_path / "project.toml"
	config_file.touch()
	c = XvivConfig(str(config_file), work_dir=str(tmp_path / "build"))
	c.add_fpga_cfg("xczu9", fpga_part="xczu9eg-ffvb1156-2-e")
	return c


@pytest.fixture
def cmd(cfg):
	return ConfigTclCommands(cfg)


@pytest.fixture
def vivado_mock():
	m = MagicMock()
	m.max_threads = 4
	return m


def _prime_project(cmd, cfg, vivado_mock):
	with patch.object(cfg, "get_vivado", return_value=vivado_mock):
		cmd._require_project()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_cmd(result: str, command: str) -> bool:
	return re.search(rf"^\s*{re.escape(command)}\b", result, re.MULTILINE) is not None


def _lacks_cmd(result: str, command: str) -> bool:
	return not _has_cmd(result, command)


# ---------------------------------------------------------------------------
# _require_project (existing)
# ---------------------------------------------------------------------------


class TestRequireProject:
	def test_already_exists(self, cmd, cfg, vivado_mock):
		_prime_project(cmd, cfg, vivado_mock)
		with pytest.raises(error.InMemoryProjectAlreadyExistsError):
			cmd._require_project()

	def test_exists_ok_returns_false(self, cmd, cfg, vivado_mock):
		_prime_project(cmd, cfg, vivado_mock)
		assert cmd._require_project(exists_ok=True) is False


# ---------------------------------------------------------------------------
# _processor_status (existing)
# ---------------------------------------------------------------------------


class TestProcessorStatus:
	def test_filter_unspecified(self, cmd):
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd._processor_status()


# ---------------------------------------------------------------------------
# program (existing)
# ---------------------------------------------------------------------------


class TestProgram:
	def test_fpga_filter_unspecified(self, cmd):
		with pytest.raises(error.FpgaTargetFilterUnspecifiedError):
			cmd.program(bitstream_file="/any/path.bit")

	def test_bitstream_not_found(self, cmd):
		with pytest.raises(error.InvalidPathError):
			cmd.program(bitstream_file="/nonexistent/top.bit", fpga_target_filter="fpga*")

	def test_elf_not_found(self, cmd):
		with pytest.raises(error.InvalidPathError):
			cmd.program(elf_file="/nonexistent/app.elf")

	def test_reset_duration_unspecified(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		elf = tmp_path / "app.elf"
		elf.touch()
		with pytest.raises(error.ResetDurationUnspecifiedError):
			cmd.program(
				bitstream_file=str(bitstream),
				fpga_target_filter="fpga*",
				elf_file=str(elf),
			)

	def test_processor_filter_unspecified(self, cmd, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd.program(elf_file=str(elf))


# ---------------------------------------------------------------------------
# processor_cntrl (existing)
# ---------------------------------------------------------------------------


class TestProcessorCntrl:
	def test_filter_unspecified_on_reset(self, cmd):
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd.processor_cntrl(reset=True, status=False)


# ---------------------------------------------------------------------------
# create_core (existing)
# ---------------------------------------------------------------------------


class TestCreateCore:
	def test_vlnv_not_in_catalog(self, cfg, cmd):
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0")
		with patch.object(cfg, "get_catalog") as mock_catalog:
			mock_catalog.return_value.lookup_optional.return_value = None
			with pytest.raises(error.CoreVlnvNotInCatalogError) as exc_info:
				cmd.create_core("my_core")
		assert exc_info.value.name == "my_core"
		assert exc_info.value.vlnv == "a:b:my_core:1.0"


# ---------------------------------------------------------------------------
# synth - validation (existing)
# ---------------------------------------------------------------------------


class TestSynthValidation:
	def test_no_identifier(self, cmd):
		with pytest.raises(error.SynthNoIdentifierError):
			cmd.synth()

	def test_bitstream_requires_route(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design", run_route=False, bitstream=True)
		with pytest.raises(error.SynthBitstreamRequiresRouteError):
			cmd.synth(design="my_design")

	def test_xsa_requires_route(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design", run_route=False, bitstream=False, hw_platform=True)
		with pytest.raises(error.SynthXsaRequiresRouteError):
			cmd.synth(design="my_design")

	def test_resume_invalid(self, cfg, cmd):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design")
		with pytest.raises(error.SynthResumeInvalidError) as exc_info:
			cmd.synth(design="my_design", resume="badstage")
		assert exc_info.value.stage == "badstage"


# ---------------------------------------------------------------------------
# synth - resume DCP missing (existing)
# ---------------------------------------------------------------------------


class TestSynthResumeDcp:
	@pytest.fixture(autouse=True)
	def _setup(self, cfg):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(design="my_design")

	def test_resume_route_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="route")
		assert exc_info.value.stage == "route"

	def test_resume_place_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="place")
		assert exc_info.value.stage == "place"

	def test_resume_synth_dcp_missing(self, cmd, cfg):
		with pytest.raises(error.SynthResumeDcpMissingError) as exc_info:
			cmd.synth(design="my_design", resume="synth")
		assert exc_info.value.stage == "synth"


# ---------------------------------------------------------------------------
# synth - OOC stub missing (existing)
# ---------------------------------------------------------------------------


class TestSynthOocStub:
	def test_stub_missing(self, cfg, vivado_mock):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(
			design="my_design",
			out_of_context_subcores=True,
			bitstream=False,
			hw_platform=False,
		)
		cfg.add_core_cfg("sub_core", vlnv="a:b:sub_core:1.0")
		cfg.add_subcore_cfg(core="sub_core", inst_hier_path="/top/u_sub", design="my_design")
		cfg.add_synth_cfg(
			core="sub_core",
			run_place=False,
			place_dcp=False,
			run_route=False,
			route_dcp=False,
			run_phys_opt=False,
			run_opt=False,
		)

		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			with pytest.raises(error.OocStubMissingError) as exc_info:
				cmd.synth(design="my_design")

		assert exc_info.value.core == "sub_core"


# ===========================================================================
# ConfigTclBuilder - build / clear
# ===========================================================================


class TestBuild:
	def test_returns_none_when_no_lines_pushed(self, cmd):
		assert cmd.build() is None

	def test_returns_string_after_push(self, cmd):
		cmd._push("puts hello")
		result = cmd.build()
		assert result is not None
		assert "puts hello" in result

	def test_clear_resets_output_to_none(self, cmd):
		cmd._push("something")
		cmd._clear()
		assert cmd.build() is None

	def test_multiple_pushes_all_appear_in_output(self, cmd):
		cmd._push("line_one")
		cmd._push("line_two")
		result = cmd.build()
		assert "line_one" in result
		assert "line_two" in result


# ===========================================================================
# ConfigTclBuilder - TCL primitive output
# ===========================================================================


class TestTclPrimitives:
	def test_set_generates_correct_tcl(self, cmd):
		cmd._set("my_var", "42")
		assert "set my_var 42" in cmd.build()

	def test_if_generates_braced_block(self, cmd):
		cmd._if("$x > 0", lambda c: c._push("puts yes"))
		result = cmd.build()
		assert "if {$x > 0}" in result
		assert "puts yes" in result

	def test_proc_generates_named_proc(self, cmd):
		cmd._proc("my_proc", "args", lambda c: c._push("return 0"))
		result = cmd.build()
		assert "proc my_proc" in result
		assert "return 0" in result

	def test_foreach_generates_loop(self, cmd):
		cmd._foreach(
			"item",
			iter_lambda=lambda c: c._push("get_items"),
			body_func=lambda c: c._push("puts $item"),
		)
		result = cmd.build()
		assert "foreach item" in result
		assert "puts $item" in result

	def test_set_exec_wraps_in_brackets(self, cmd):
		cmd._set_exec("result", lambda c: c._push("some_command"))
		assert "set result [" in cmd.build()

	def test_catch_generates_catch_block(self, cmd):
		cmd.catch(lambda c: c._push("risky_call"))
		assert "catch {" in cmd.build()


# ===========================================================================
# open_dcp
# ===========================================================================


class TestOpenDcp:
	def test_raises_if_dcp_file_missing(self, cmd):
		with pytest.raises(AssertionError):
			cmd.open_dcp("/nonexistent/design.dcp")

	def test_output_contains_open_checkpoint(self, cmd, tmp_path):
		dcp = tmp_path / "design.dcp"
		dcp.touch()
		cmd.open_dcp(str(dcp), nogui=True)
		assert _has_cmd(cmd.build(), "open_checkpoint")

	def test_dcp_path_is_absolute_in_output(self, cmd, tmp_path):
		dcp = tmp_path / "design.dcp"
		dcp.touch()
		cmd.open_dcp(str(dcp), nogui=True)
		assert str(dcp.resolve()) in cmd.build()

	def test_start_gui_included_by_default(self, cmd, tmp_path):
		# NOTE: test name intentionally does NOT contain "start_gui" to avoid
		# path contamination; the _has_cmd helper anchors to line-start so
		# path fragments inside quoted strings never match.
		dcp = tmp_path / "design.dcp"
		dcp.touch()
		cmd.open_dcp(str(dcp))
		# start_gui must appear as a standalone TCL command, not just in a path.
		assert _has_cmd(cmd.build(), "start_gui")

	def test_nogui_omits_start_gui(self, cmd, tmp_path):
		# Renamed from test_nogui_excludes_start_gui to avoid embedding
		# "start_gui" in the pytest tmp_path directory name.
		dcp = tmp_path / "design.dcp"
		dcp.touch()
		cmd.open_dcp(str(dcp), nogui=True)
		assert _lacks_cmd(cmd.build(), "start_gui")


# ===========================================================================
# create_platform
# ===========================================================================


class TestCreatePlatform:
	def _add_platform(self, cfg, xsa_path, bitstream_path):
		cfg.add_platform_cfg(
			"my_platform",
			xsa=str(xsa_path),
			bitstream=str(bitstream_path),
		)

	def test_raises_if_xsa_missing(self, cfg, cmd):
		self._add_platform(cfg, "/nonexistent/design.xsa", "/fake/bit")
		with pytest.raises(AssertionError):
			cmd.create_platform("my_platform")

	def test_output_contains_hsi_open_hw_design(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform(cfg, xsa, tmp_path / "design.bit")
		cmd.create_platform("my_platform")
		assert "hsi::open_hw_design" in cmd.build()

	def test_output_contains_hsi_create_sw_design(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform(cfg, xsa, tmp_path / "design.bit")
		cmd.create_platform("my_platform")
		assert "hsi::create_sw_design" in cmd.build()

	def test_output_contains_hsi_generate_bsp(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform(cfg, xsa, tmp_path / "design.bit")
		cmd.create_platform("my_platform")
		assert "hsi::generate_bsp" in cmd.build()

	def test_output_contains_hsi_close_hw_design(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform(cfg, xsa, tmp_path / "design.bit")
		cmd.create_platform("my_platform")
		assert "hsi::close_hw_design" in cmd.build()

	def test_output_includes_platform_dir(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform(cfg, xsa, tmp_path / "design.bit")
		platform_cfg = cfg.get_platform("my_platform")
		cmd.create_platform("my_platform")
		assert platform_cfg.dir in cmd.build()


# ===========================================================================
# create_app
# ===========================================================================


class TestCreateApp:
	def _add_platform_and_app(self, cfg, xsa_path, bitstream_path):
		cfg.add_platform_cfg(
			"my_platform",
			xsa=str(xsa_path),
			bitstream=str(bitstream_path),
		)
		cfg.add_app_cfg("my_app", platform="my_platform", template="hello_world")

	def test_raises_if_xsa_missing(self, cfg, cmd):
		self._add_platform_and_app(cfg, "/nonexistent/design.xsa", "/fake/bit")
		with pytest.raises(AssertionError):
			cmd.create_app("my_app")

	def test_output_contains_hsi_generate_app(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform_and_app(cfg, xsa, tmp_path / "design.bit")
		cmd.create_app("my_app")
		assert "hsi::generate_app" in cmd.build()

	def test_output_contains_template_name(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform_and_app(cfg, xsa, tmp_path / "design.bit")
		cmd.create_app("my_app")
		assert "hello_world" in cmd.build()

	def test_output_contains_hsi_close_hw_design(self, cfg, cmd, tmp_path):
		xsa = tmp_path / "design.xsa"
		xsa.touch()
		self._add_platform_and_app(cfg, xsa, tmp_path / "design.bit")
		cmd.create_app("my_app")
		assert "hsi::close_hw_design" in cmd.build()


# ===========================================================================
# edit_bd
# ===========================================================================


class TestEditBd:
	def test_raises_if_bd_file_missing(self, cfg, cmd):
		cfg.add_bd_cfg("my_bd", bd_file="/nonexistent/my_bd.bd")
		with pytest.raises(AssertionError):
			cmd.edit_bd("my_bd")

	def test_output_contains_read_bd_and_open(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_bd("my_bd", nogui=True)
		result = cmd.build()
		assert "read_bd" in result
		assert "open_bd_design" in result

	def test_nogui_omits_start_gui(self, cfg, cmd, tmp_path, vivado_mock):
		# Renamed from test_nogui_excludes_start_gui to keep "start_gui" out
		# of the pytest tmp_path directory name.
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_bd("my_bd", nogui=True)
		assert _lacks_cmd(cmd.build(), "start_gui")

	def test_default_opens_gui(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_bd("my_bd")
		assert _has_cmd(cmd.build(), "start_gui")

	def test_output_includes_write_bd_tcl(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_bd("my_bd", nogui=True)
		assert "write_bd_tcl" in cmd.build()


# ===========================================================================
# create_bd
# ===========================================================================


class TestCreateBd:
	def test_opens_gui_when_save_file_absent(self, cfg, cmd, tmp_path, vivado_mock):
		# auto-resolved save_file path will not exist
		cfg.add_bd_cfg("my_bd")
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.create_bd("my_bd")
		assert _has_cmd(cmd.build(), "start_gui")

	def test_output_contains_create_bd_design(self, cfg, cmd, tmp_path, vivado_mock):
		cfg.add_bd_cfg("my_bd")
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.create_bd("my_bd")
		assert _has_cmd(cmd.build(), "create_bd_design")

	def test_output_contains_create_project(self, cfg, cmd, tmp_path, vivado_mock):
		cfg.add_bd_cfg("my_bd")
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.create_bd("my_bd")
		assert _has_cmd(cmd.build(), "create_project")


# ===========================================================================
# generate_bd
# ===========================================================================


class TestGenerateBd:
	def test_raises_if_bd_file_missing(self, cfg, cmd):
		cfg.add_bd_cfg("my_bd", bd_file="/nonexistent/my_bd.bd")
		with pytest.raises(AssertionError):
			cmd.generate_bd("my_bd")

	def test_clears_when_wrapper_is_up_to_date_and_force_false(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		wrapper_file = tmp_path / "my_bd_wrapper.v"
		wrapper_file.touch()
		# Make wrapper newer than bd_file so is_stale() returns False
		future = time.time() + 100
		os.utime(str(wrapper_file), (future, future))
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file), bd_wrapper_file=str(wrapper_file))
		cmd.generate_bd("my_bd", force=False)
		assert cmd.build() is None

	def test_regenerates_when_bd_is_newer_than_wrapper(self, cfg, cmd, tmp_path, vivado_mock):
		wrapper_file = tmp_path / "my_bd_wrapper.v"
		wrapper_file.touch()
		# Make bd_file newer so it is stale
		future = time.time() + 100
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		os.utime(str(bd_file), (future, future))
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file), bd_wrapper_file=str(wrapper_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_bd("my_bd", force=False)
		assert cmd.build() is not None

	def test_force_true_always_regenerates(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		wrapper_file = tmp_path / "my_bd_wrapper.v"
		wrapper_file.touch()
		future = time.time() + 100
		os.utime(str(wrapper_file), (future, future))
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file), bd_wrapper_file=str(wrapper_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_bd("my_bd", force=True)
		result = cmd.build()
		assert result is not None
		assert "generate_target" in result

	def test_output_contains_generate_target(self, cfg, cmd, tmp_path, vivado_mock):
		bd_file = tmp_path / "my_bd.bd"
		bd_file.touch()
		cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_bd("my_bd", force=True)
		assert "generate_target" in cmd.build()


# ===========================================================================
# edit_core
# ===========================================================================


class TestEditCore:
	def test_raises_if_xci_missing(self, cfg, cmd, vivado_mock):
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file="/nonexistent/my_core.xci")
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			with pytest.raises(AssertionError):
				cmd.edit_core("my_core")

	def test_output_contains_read_ip(self, cfg, cmd, tmp_path, vivado_mock):
		xci = tmp_path / "my_core.xci"
		xci.touch()
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file=str(xci))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_core("my_core", nogui=True)
		assert "read_ip" in cmd.build()

	def test_nogui_skips_gui_and_generate(self, cfg, cmd, tmp_path, vivado_mock):
		xci = tmp_path / "my_core.xci"
		xci.touch()
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file=str(xci))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.edit_core("my_core", nogui=True)
		result = cmd.build()
		assert "start_ip_gui" not in result
		assert "generate_target" not in result


# ===========================================================================
# generate_core
# ===========================================================================


class TestGenerateCore:
	def test_raises_if_xci_missing(self, cfg, cmd, vivado_mock):
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file="/nonexistent/my_core.xci")
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			with pytest.raises(AssertionError):
				cmd.generate_core("my_core")

	def test_output_contains_read_ip(self, cfg, cmd, tmp_path, vivado_mock):
		xci = tmp_path / "my_core.xci"
		xci.touch()
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file=str(xci))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_core("my_core")
		assert "read_ip" in cmd.build()

	def test_output_contains_upgrade_ip(self, cfg, cmd, tmp_path, vivado_mock):
		xci = tmp_path / "my_core.xci"
		xci.touch()
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file=str(xci))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_core("my_core")
		assert "upgrade_ip" in cmd.build()

	def test_output_contains_generate_target(self, cfg, cmd, tmp_path, vivado_mock):
		xci = tmp_path / "my_core.xci"
		xci.touch()
		cfg.add_core_cfg("my_core", vlnv="a:b:my_core:1.0", xci_file=str(xci))
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.generate_core("my_core")
		assert "generate_target" in cmd.build()


# ===========================================================================
# processor_cntrl - TCL output
# ===========================================================================


class TestProcessorCntrlTcl:
	def test_status_true_without_filter_raises(self, cmd):
		# _processor_status() is called without forwarding processor_target_filter
		with pytest.raises(error.ProcessorTargetFilterUnspecifiedError):
			cmd.processor_cntrl(reset=None, status=True)

	def test_connect_and_disconnect_always_present(self, cmd):
		# "connect" is a substring of "disconnect", so a plain `in` check
		# would pass even if only disconnect were present.  Use word boundaries.
		cmd.processor_cntrl(reset=None, status=None)
		result = cmd.build()
		assert re.search(r"\bconnect\b", result)
		assert re.search(r"\bdisconnect\b", result)

	def test_reset_with_filter_includes_rst(self, cmd):
		# "rst" appears inside words such as "first"; \b ensures only the
		# standalone TCL command is matched.
		cmd.processor_cntrl(reset=True, status=None, processor_target_filter="mb*")
		result = cmd.build()
		assert re.search(r"\brst\b", result)
		assert "mb*" in result

	def test_reset_with_filter_includes_con(self, cmd):
		# "con" is a substring of "connect" and "disconnect"; \b prevents
		# matching those occurrences.
		cmd.processor_cntrl(reset=True, status=None, processor_target_filter="mb*")
		assert re.search(r"\bcon\b", cmd.build())


# ===========================================================================
# program - TCL output
# ===========================================================================


class TestProgramTcl:
	def test_output_contains_connect_and_disconnect(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		cmd.program(bitstream_file=str(bitstream), fpga_target_filter="fpga*")
		result = cmd.build()
		# "connect" is a substring of "disconnect"; use \b to match only the
		# standalone connect command.
		assert re.search(r"\bconnect\b", result)
		assert re.search(r"\bdisconnect\b", result)

	def test_bitstream_includes_fpga_command(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		cmd.program(bitstream_file=str(bitstream), fpga_target_filter="fpga*")
		# "fpga" can appear in file-path fragments embedded in the TCL output;
		# \b anchors to the start of the TCL command token.
		assert re.search(r"\bfpga\b", cmd.build())

	def test_bitstream_filter_appears_in_target_selection(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		cmd.program(bitstream_file=str(bitstream), fpga_target_filter="xc7a35t*")
		assert "xc7a35t*" in cmd.build()

	def test_elf_includes_dow_and_con(self, cmd, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		cmd.program(elf_file=str(elf), processor_target_filter="mb*")
		result = cmd.build()
		# "dow" can appear in path fragments ("shadow", etc.); "con" is a
		# substring of "connect"/"disconnect".  Word boundaries fix both.
		assert re.search(r"\bdow\b", result)
		assert re.search(r"\bcon\b", result)

	def test_elf_includes_rst(self, cmd, tmp_path):
		elf = tmp_path / "app.elf"
		elf.touch()
		cmd.program(elf_file=str(elf), processor_target_filter="mb*")
		# "rst" appears inside "first" and other words; \b matches only the
		# standalone TCL rst command.
		assert re.search(r"\brst\b", cmd.build())

	def test_after_delay_emitted_when_reset_duration_set(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		elf = tmp_path / "app.elf"
		elf.touch()
		cmd.program(
			bitstream_file=str(bitstream),
			fpga_target_filter="fpga*",
			elf_file=str(elf),
			processor_target_filter="mb*",
			processor_reset_duration=500,
		)
		assert "after 500" in cmd.build()

	def test_zero_reset_duration_omits_after(self, cmd, tmp_path):
		bitstream = tmp_path / "top.bit"
		bitstream.touch()
		elf = tmp_path / "app.elf"
		elf.touch()
		cmd.program(
			bitstream_file=str(bitstream),
			fpga_target_filter="fpga*",
			elf_file=str(elf),
			processor_target_filter="mb*",
			processor_reset_duration=0,
		)
		assert "after 0" not in cmd.build()


# ===========================================================================
# synth - auto resume stage detection
# ===========================================================================


class TestSynthAutoResume:
	"""All tests share a minimal design with no sources to avoid assert_file_exists."""

	@pytest.fixture(autouse=True)
	def _setup(self, cfg):
		cfg.add_design_cfg("my_design", sources=[])
		cfg.add_synth_cfg(
			design="my_design",
			bitstream=False,
			hw_platform=False,
			synth_dcp=False,
			place_dcp=False,
			route_dcp=False,
		)

	def test_no_dcps_found_starts_from_synth(self, cmd, cfg, vivado_mock):
		# No DCP files exist -> auto detects SYNTH as start stage
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design", resume="auto")
		assert _has_cmd(cmd.build(), "synth_design")

	def test_synth_dcp_skips_synth_design(self, cmd, cfg, tmp_path):
		# Renamed from test_synth_dcp_found_skips_synth_design: the old name
		# embedded "synth_design" in tmp_path, poisoning the not-in assertion.
		synth_cfg = cfg.get_synth(design_name="my_design")
		dcp = tmp_path / "synth.dcp"
		dcp.touch()
		synth_cfg.synth_dcp_file = str(dcp)
		synth_cfg.place_dcp_file = str(tmp_path / "no_place.dcp")  # doesn't exist
		synth_cfg.route_dcp_file = str(tmp_path / "no_route.dcp")  # doesn't exist
		# Auto-resume from checkpoint - _require_project is NOT called
		cmd.synth(design="my_design", resume="auto")
		result = cmd.build()
		assert _has_cmd(result, "open_checkpoint")
		assert _lacks_cmd(result, "synth_design")

	def test_place_dcp_found_skips_synth_and_place(self, cmd, cfg, tmp_path):
		synth_cfg = cfg.get_synth(design_name="my_design")
		dcp = tmp_path / "place.dcp"
		dcp.touch()
		synth_cfg.synth_dcp_file = str(tmp_path / "no_synth.dcp")
		synth_cfg.place_dcp_file = str(dcp)
		synth_cfg.route_dcp_file = str(tmp_path / "no_route.dcp")
		cmd.synth(design="my_design", resume="auto")
		result = cmd.build()
		assert _has_cmd(result, "open_checkpoint")
		assert _lacks_cmd(result, "synth_design")
		assert _lacks_cmd(result, "place_design")

	def test_route_dcp_found_skips_to_write_stage(self, cmd, cfg, tmp_path):
		synth_cfg = cfg.get_synth(design_name="my_design")
		dcp = tmp_path / "route.dcp"
		dcp.touch()
		synth_cfg.synth_dcp_file = str(tmp_path / "no_synth.dcp")
		synth_cfg.place_dcp_file = str(tmp_path / "no_place.dcp")
		synth_cfg.route_dcp_file = str(dcp)
		cmd.synth(design="my_design", resume="auto")
		result = cmd.build()
		assert _has_cmd(result, "open_checkpoint")
		assert _lacks_cmd(result, "route_design")
		assert _lacks_cmd(result, "synth_design")


# ===========================================================================
# synth - TCL output for various configurations
# ===========================================================================


class TestSynthTclOutput:
	"""
	Tests that synth() generates the right TCL commands for various run flags and
	output options.  All tests use a real source file to satisfy assert_file_exists.
	"""

	def _setup_design(self, cfg, tmp_path, **synth_kwargs):
		src = tmp_path / "top.v"
		src.touch()
		cfg.add_design_cfg("my_design", sources=[str(src)])
		defaults = dict(
			design="my_design",
			bitstream=False,
			hw_platform=False,
			synth_dcp=False,
			place_dcp=False,
			route_dcp=False,
		)
		defaults.update(synth_kwargs)
		cfg.add_synth_cfg(**defaults)

	def test_synth_design_emitted_by_default(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_synth_design_command_present_by_default: the old
		# name embedded "synth_design" in tmp_path, giving a false positive.
		self._setup_design(cfg, tmp_path)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _has_cmd(cmd.build(), "synth_design")

	def test_design_top_appears_in_synth_design(self, cfg, tmp_path, vivado_mock):
		self._setup_design(cfg, tmp_path)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert "my_design" in cmd.build()

	def test_run_synth_false_omits_synth(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_run_synth_false_omits_synth_design: the old name
		# embedded "synth_design" in tmp_path, poisoning the not-in assertion.
		self._setup_design(cfg, tmp_path, run_synth=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _lacks_cmd(cmd.build(), "synth_design")

	def test_run_opt_false_omits_opt_design(self, cfg, tmp_path, vivado_mock):
		self._setup_design(cfg, tmp_path, run_opt=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		# "opt_design" is a substring of "phys_opt_design", so a plain `not in`
		# check would fail whenever phys_opt runs.  Use \b to match only the
		# standalone opt_design command.
		assert re.search(r"\bopt_design\b", cmd.build()) is None

	def test_run_place_false_omits_place(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_run_place_false_omits_place_design: the old name
		# embedded "place_design" in tmp_path, poisoning the not-in assertion.
		self._setup_design(cfg, tmp_path, run_place=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _lacks_cmd(cmd.build(), "place_design")

	def test_run_phys_opt_false_omits_phys_opt(self, cfg, tmp_path, vivado_mock):
		self._setup_design(cfg, tmp_path, run_phys_opt=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert "phys_opt_design" not in cmd.build()

	def test_run_route_false_omits_route(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_run_route_false_omits_route_design: the old name
		# embedded "route_design" in tmp_path, poisoning the not-in assertion.
		self._setup_design(cfg, tmp_path, run_route=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _lacks_cmd(cmd.build(), "route_design")

	def test_bitstream_emitted_when_configured(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_write_bitstream_present_when_configured: the old
		# name embedded "write_bitstream" in tmp_path, giving a false positive.
		self._setup_design(cfg, tmp_path, bitstream=True)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _has_cmd(cmd.build(), "write_bitstream")

	def test_bitstream_absent_when_disabled(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_write_bitstream_absent_when_not_configured: the old
		# name embedded "write_bitstream" in tmp_path, poisoning the not-in assertion.
		self._setup_design(cfg, tmp_path, bitstream=False, hw_platform=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _lacks_cmd(cmd.build(), "write_bitstream")

	def test_synth_dcp_produces_checkpoint(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_synth_dcp_emits_write_checkpoint: the old name
		# embedded "write_checkpoint" in tmp_path, giving a false positive.
		self._setup_design(cfg, tmp_path, synth_dcp=True)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _has_cmd(cmd.build(), "write_checkpoint")

	def test_no_checkpoint_when_synth_dcp_false(self, cfg, tmp_path, vivado_mock):
		# With synth_dcp=False, place_dcp=False, route_dcp=False - no write_checkpoint
		self._setup_design(cfg, tmp_path, synth_dcp=False, place_dcp=False, route_dcp=False)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		assert _lacks_cmd(cmd.build(), "write_checkpoint")

	def test_usr_access_sets_design_property(self, cfg, tmp_path, vivado_mock):
		self._setup_design(cfg, tmp_path)
		synth_cfg = cfg.get_synth(design_name="my_design")
		synth_cfg.usr_access_value = 0xDEADBEEF
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		result = cmd.build()
		assert "BITSTREAM.CONFIG.USR_ACCESS" in result
		assert "DEADBEEF" in result.upper()

	def test_design_sources_added(self, cfg, tmp_path, vivado_mock):
		# Renamed from test_add_files_called_for_design_sources: the old name
		# embedded "add_files" in tmp_path, giving a false positive.
		self._setup_design(cfg, tmp_path)
		cmd = ConfigTclCommands(cfg)
		with patch.object(cfg, "get_vivado", return_value=vivado_mock):
			cmd.synth(design="my_design")
		result = cmd.build()
		assert _has_cmd(result, "add_files")
		assert "top.v" in result
