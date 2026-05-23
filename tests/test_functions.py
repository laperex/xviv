import os
from unittest.mock import MagicMock, patch

import pytest

from xviv.functions.synthesis import cmd_dcp_open, cmd_synth  # noqa: E402
from xviv.functions.xsct import (  # noqa: E402
	cmd_app_build,
	cmd_app_create,
	cmd_platform_build,
	cmd_platform_create,
	cmd_processor,
	cmd_program,
)
from xviv.utils import error  # noqa: E402

VITIS_MODULE = "xviv.functions.xsct"
SYNTH_MODULE = "xviv.functions.synthesis"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_cfg(*, dry_run: bool = False) -> MagicMock:
	cfg = MagicMock()
	cfg.get_vivado.return_value.dry_run = dry_run
	return cfg


def _make_platform_cfg(*, directory: str = "/build/platform/my_platform") -> MagicMock:
	platform_cfg = MagicMock()
	platform_cfg.name = "my_platform"
	platform_cfg.dir = directory
	platform_cfg.cpu = "microblaze_0"
	platform_cfg.bitstream_file = "/build/synth/my_platform.bit"
	return platform_cfg


def _make_app_cfg(*, directory: str = "/build/app/my_app") -> MagicMock:
	app_cfg = MagicMock()
	app_cfg.name = "my_app"
	app_cfg.dir = directory
	app_cfg.platform = "my_platform"
	app_cfg.elf_file = os.path.join(directory, "executable.elf")
	source = MagicMock()
	source.file = "main.c"
	app_cfg.sources = [source]
	return app_cfg


def _make_synth_cfg(
	*,
	has_bitstream: bool = True,
	out_of_context_subcores: bool = False,
	usr_access_value=None,
) -> MagicMock:
	synth_cfg = MagicMock()
	synth_cfg.bitstream_file = "/build/synth/design.bit" if has_bitstream else None
	synth_cfg.out_of_context_subcores = out_of_context_subcores
	synth_cfg.usr_access_value = usr_access_value
	return synth_cfg


# ===========================================================================
# cmd_platform_create
# ===========================================================================


class TestCmdPlatformCreate:
	def test_validates_platform(self):
		cfg = _make_cfg()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.create_platform.return_value.build.return_value = MagicMock()
			cmd_platform_create(cfg, platform_name="my_platform")
		cfg.validate_platform.assert_called_once_with(platform_name="my_platform")

	def test_builds_tcl_with_correct_platform(self):
		cfg = _make_cfg()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.create_platform.return_value.build.return_value = MagicMock()
			cmd_platform_create(cfg, platform_name="my_platform")
		MockTcl.assert_called_once_with(cfg)
		MockTcl.return_value.create_platform.assert_called_once_with("my_platform")
		MockTcl.return_value.create_platform.return_value.build.assert_called_once()

	def test_runs_xsct_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct") as mock_xsct:
			MockTcl.return_value.create_platform.return_value.build.return_value = mock_config
			cmd_platform_create(cfg, platform_name="my_platform")
		mock_xsct.assert_called_once_with(cfg, config_tcl=mock_config)


# ===========================================================================
# cmd_platform_build
# ===========================================================================


class TestCmdPlatformBuild:
	def test_raises_if_bsp_directory_missing(self):
		cfg = _make_cfg()
		cfg.get_platform.return_value = _make_platform_cfg()
		with patch("os.path.isdir", return_value=False):
			with pytest.raises(error.PlatformBspDirectoryMissingError):
				cmd_platform_build(cfg, "my_platform")

	def test_validates_platform_before_checking_dir(self):
		cfg = _make_cfg()
		platform_cfg = _make_platform_cfg()
		cfg.get_platform.return_value = platform_cfg
		with patch("os.path.isdir", return_value=False):
			with pytest.raises(error.PlatformBspDirectoryMissingError):
				cmd_platform_build(cfg, "my_platform")
		cfg.validate_platform.assert_called_once_with(platform_name="my_platform")

	def test_runs_make_with_correct_cwd(self):
		cfg = _make_cfg(dry_run=False)
		platform_cfg = _make_platform_cfg()
		cfg.get_platform.return_value = platform_cfg
		with (
			patch("os.path.isdir", return_value=True),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={"VITIS": "1"}),
		):
			cmd_platform_build(cfg, "my_platform")
		mock_run.assert_called_once()
		_, kwargs = mock_run.call_args
		assert kwargs["cwd"] == platform_cfg.dir
		assert kwargs["check"] is True

	def test_runs_make_with_parallel_jobs(self):
		cfg = _make_cfg(dry_run=False)
		platform_cfg = _make_platform_cfg()
		cfg.get_platform.return_value = platform_cfg
		with (
			patch("os.path.isdir", return_value=True),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_platform_build(cfg, "my_platform")
		positional_cmd = mock_run.call_args[0][0]
		assert positional_cmd[0] == "make"
		assert any(arg.startswith("-j") for arg in positional_cmd)

	def test_passes_vitis_env_to_make(self):
		cfg = _make_cfg(dry_run=False)
		platform_cfg = _make_platform_cfg()
		cfg.get_platform.return_value = platform_cfg
		env = {"VITIS_PATH": "/opt/vitis"}
		with (
			patch("os.path.isdir", return_value=True),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value=env),
		):
			cmd_platform_build(cfg, "my_platform")
		_, kwargs = mock_run.call_args
		assert kwargs["env"] == env

	def test_skips_make_on_dry_run(self):
		cfg = _make_cfg(dry_run=True)
		cfg.get_platform.return_value = _make_platform_cfg()
		with patch("os.path.isdir", return_value=True), patch("subprocess.run") as mock_run:
			cmd_platform_build(cfg, "my_platform")
		mock_run.assert_not_called()


# ===========================================================================
# cmd_app_create
# ===========================================================================


class TestCmdAppCreate:
	def test_overrides_template_when_provided(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		with (
			patch("os.path.isdir", return_value=True),
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct"),
		):
			MockTcl.return_value.create_app.return_value.build.return_value = MagicMock()
			cmd_app_create(cfg, app_name="my_app", platform_name=None, template="hello_world")
		assert app_cfg.template == "hello_world"

	def test_overrides_platform_when_provided(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		with (
			patch("os.path.isdir", return_value=True),
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct"),
		):
			MockTcl.return_value.create_app.return_value.build.return_value = MagicMock()
			cmd_app_create(cfg, app_name="my_app", platform_name="other_platform")
		assert app_cfg.platform == "other_platform"

	def test_creates_platform_first_when_bsp_dir_missing(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		with (
			patch("os.path.isdir", return_value=False),
			patch(f"{VITIS_MODULE}.cmd_platform_create") as mock_create,
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct"),
		):
			MockTcl.return_value.create_app.return_value.build.return_value = MagicMock()
			cmd_app_create(cfg, app_name="my_app", platform_name=None)
		mock_create.assert_called_once_with(cfg, platform_name=app_cfg.platform)

	def test_skips_platform_create_when_bsp_dir_exists(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		with (
			patch("os.path.isdir", return_value=True),
			patch(f"{VITIS_MODULE}.cmd_platform_create") as mock_create,
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct"),
		):
			MockTcl.return_value.create_app.return_value.build.return_value = MagicMock()
			cmd_app_create(cfg, app_name="my_app", platform_name=None)
		mock_create.assert_not_called()

	def test_validates_app_and_platform(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		with (
			patch("os.path.isdir", return_value=True),
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct"),
		):
			MockTcl.return_value.create_app.return_value.build.return_value = MagicMock()
			cmd_app_create(cfg, app_name="my_app", platform_name=None)
		cfg.validate_app.assert_called_once_with(app_name="my_app", check_elf=False)
		cfg.validate_platform.assert_called_once_with(platform_name=app_cfg.platform)

	def test_runs_xsct_with_built_config(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = _make_platform_cfg()
		mock_config = MagicMock()
		with (
			patch("os.path.isdir", return_value=True),
			patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{VITIS_MODULE}.run_xsct") as mock_xsct,
		):
			MockTcl.return_value.create_app.return_value.build.return_value = mock_config
			cmd_app_create(cfg, app_name="my_app", platform_name=None)
		mock_xsct.assert_called_once_with(cfg, config_tcl=mock_config)


# ===========================================================================
# cmd_app_build
# ===========================================================================


class TestCmdAppBuild:
	def _setup(self, cfg, directory="/build/app/my_app"):
		app_cfg = _make_app_cfg(directory=directory)
		platform_cfg = _make_platform_cfg()
		cfg.get_app.return_value = app_cfg
		cfg.get_platform.return_value = platform_cfg
		return app_cfg, platform_cfg

	def test_transforms_makefile_before_build(self):
		cfg = _make_cfg(dry_run=False)
		app_cfg, _ = self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile") as mock_transform,
			patch("subprocess.run"),
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_app_build(cfg, "my_app", info=None)
		mock_transform.assert_called_once_with(os.path.join(app_cfg.dir, "Makefile"))

	def test_transforms_makefile_even_on_dry_run(self):
		cfg = _make_cfg(dry_run=True)
		app_cfg, _ = self._setup(cfg)
		with patch(f"{VITIS_MODULE}._transform_app_makefile") as mock_transform, patch("subprocess.run"):
			cmd_app_build(cfg, "my_app", info=None)
		mock_transform.assert_called_once()

	def test_runs_make_with_correct_cwd(self):
		cfg = _make_cfg(dry_run=False)
		app_cfg, _ = self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile"),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_app_build(cfg, "my_app", info=None)
		make_call = mock_run.call_args_list[0]
		assert make_call[0][0][0] == "make"
		assert make_call[1]["cwd"] == app_cfg.dir
		assert make_call[1]["check"] is True

	def test_includes_source_files_in_make_cmd(self):
		cfg = _make_cfg(dry_run=False)
		app_cfg, _ = self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile"),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_app_build(cfg, "my_app", info=None)
		make_cmd = mock_run.call_args_list[0][0][0]
		c_sources_arg = next(a for a in make_cmd if a.startswith("c_SOURCES="))
		assert "main.c" in c_sources_arg

	def test_skips_make_on_dry_run(self):
		cfg = _make_cfg(dry_run=True)
		self._setup(cfg)
		with patch(f"{VITIS_MODULE}._transform_app_makefile"), patch("subprocess.run") as mock_run:
			cmd_app_build(cfg, "my_app", info=None)
		mock_run.assert_not_called()

	def test_validates_elf_after_successful_build(self):
		cfg = _make_cfg(dry_run=False)
		self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile"),
			patch("subprocess.run"),
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_app_build(cfg, "my_app", info=None)
		# Last validate_app call must have check_elf=True
		post_build_call = cfg.validate_app.call_args_list[-1]
		assert post_build_call[1].get("check_elf") is True

	def test_prints_elf_info_when_requested(self):
		cfg = _make_cfg(dry_run=False)
		app_cfg, _ = self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile"),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
			patch(f"{VITIS_MODULE}.mb_tool", return_value="mb-size"),
		):
			cmd_app_build(cfg, "my_app", info=True)
		# make call + two info calls (size + objdump)
		assert mock_run.call_count == 3

	def test_no_extra_subprocess_calls_without_info(self):
		cfg = _make_cfg(dry_run=False)
		self._setup(cfg)
		with (
			patch(f"{VITIS_MODULE}._transform_app_makefile"),
			patch("subprocess.run") as mock_run,
			patch(f"{VITIS_MODULE}.get_vitis_env", return_value={}),
		):
			cmd_app_build(cfg, "my_app", info=None)
		assert mock_run.call_count == 1


# ===========================================================================
# cmd_program
# ===========================================================================


class TestCmdProgram:
	def test_raises_if_no_elf_and_no_bitstream(self):
		cfg = _make_cfg()
		cfg._get_platform_cfg_optional.return_value = None
		with pytest.raises(error.ProgramUnspecifiedIdentifiersError):
			cmd_program(cfg, elf_file=None, bitstream_file=None)

	def test_resolves_bitstream_from_platform_config(self):
		cfg = _make_cfg()
		platform_cfg = _make_platform_cfg()
		cfg._get_platform_cfg_optional.return_value = platform_cfg
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(cfg, platform_name="my_platform", elf_file="/app.elf")
		kwargs = MockTcl.return_value.program.call_args[1]
		assert kwargs["bitstream_file"] == platform_cfg.bitstream_file

	def test_resolves_elf_from_app_config(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg._get_platform_cfg_optional.return_value = None
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(cfg, app_name="my_app", bitstream_file="/some.bit")
		kwargs = MockTcl.return_value.program.call_args[1]
		assert kwargs["elf_file"] == app_cfg.elf_file

	def test_explicit_elf_not_overridden_by_app(self):
		cfg = _make_cfg()
		cfg._get_platform_cfg_optional.return_value = None
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(cfg, bitstream_file="/some.bit", elf_file="/explicit.elf")
		kwargs = MockTcl.return_value.program.call_args[1]
		assert kwargs["elf_file"] == "/explicit.elf"

	def test_validates_app_when_app_name_provided(self):
		cfg = _make_cfg()
		app_cfg = _make_app_cfg()
		cfg.get_app.return_value = app_cfg
		cfg._get_platform_cfg_optional.return_value = None
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(cfg, app_name="my_app", bitstream_file="/some.bit")
		cfg.validate_app.assert_called_once_with(app_name="my_app", check_sources=False)

	def test_validates_platform_when_platform_name_provided(self):
		cfg = _make_cfg()
		platform_cfg = _make_platform_cfg()
		cfg._get_platform_cfg_optional.return_value = platform_cfg
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(cfg, platform_name="my_platform", elf_file="/app.elf")
		cfg.validate_platform.assert_called_once_with(platform_name="my_platform")

	def test_passes_filter_args_to_tcl(self):
		cfg = _make_cfg()
		cfg._get_platform_cfg_optional.return_value = None
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.program.return_value.build.return_value = MagicMock()
			cmd_program(
				cfg,
				bitstream_file="/some.bit",
				elf_file="/some.elf",
				processor_target_filter="microblaze*",
				fpga_target_filter="xc7*",
				processor_reset_duration=500,
			)
		kwargs = MockTcl.return_value.program.call_args[1]
		assert kwargs["processor_target_filter"] == "microblaze*"
		assert kwargs["fpga_target_filter"] == "xc7*"
		assert kwargs["processor_reset_duration"] == 500

	def test_runs_xsct_with_built_config(self):
		cfg = _make_cfg()
		cfg._get_platform_cfg_optional.return_value = None
		mock_config = MagicMock()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct") as mock_xsct:
			MockTcl.return_value.program.return_value.build.return_value = mock_config
			cmd_program(cfg, bitstream_file="/some.bit", elf_file="/some.elf")
		mock_xsct.assert_called_once_with(cfg, config_tcl=mock_config)


# ===========================================================================
# cmd_processor
# ===========================================================================


class TestCmdProcessor:
	def test_builds_tcl_with_cfg(self):
		cfg = _make_cfg()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.processor_cntrl.return_value.build.return_value = MagicMock()
			cmd_processor(cfg, reset=True, status=None)
		MockTcl.assert_called_once_with(cfg)

	def test_passes_reset_and_status_to_tcl(self):
		cfg = _make_cfg()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.processor_cntrl.return_value.build.return_value = MagicMock()
			cmd_processor(cfg, reset=True, status=True)
		MockTcl.return_value.processor_cntrl.assert_called_once_with(reset=True, status=True)

	def test_reset_none_status_none(self):
		cfg = _make_cfg()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct"):
			MockTcl.return_value.processor_cntrl.return_value.build.return_value = MagicMock()
			cmd_processor(cfg, reset=None, status=None)
		MockTcl.return_value.processor_cntrl.assert_called_once_with(reset=None, status=None)

	def test_runs_xsct_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with patch(f"{VITIS_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{VITIS_MODULE}.run_xsct") as mock_xsct:
			MockTcl.return_value.processor_cntrl.return_value.build.return_value = mock_config
			cmd_processor(cfg, reset=None, status=True)
		mock_xsct.assert_called_once_with(cfg, config_tcl=mock_config)


# ===========================================================================
# cmd_synth
# ===========================================================================


class TestCmdSynth:
	def test_validates_synth_before_running(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design")
		cfg.validate_synth.assert_called_once_with(bd=None, design="my_design", core=None)

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		mock_config = MagicMock()
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado") as mock_run,
		):
			MockTcl.return_value.synth.return_value.build.return_value = mock_config
			cmd_synth(cfg, design_name="my_design")
		mock_run.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_passes_resume_to_synth_tcl(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design", resume="auto")
		MockTcl.return_value.synth.assert_called_once_with(design="my_design", bd=None, core=None, resume="auto")

	def test_sets_usr_access_from_clean_git_sha(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=True, usr_access_value=None)
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado"),
			patch(f"{SYNTH_MODULE}._git_sha_tag", return_value=("deadbeef", False, "v1.0")),
		):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design", usr_access_type="git")
		assert synth_cfg.usr_access_value == int("deadbeef", 16)

	def test_sets_dirty_bit_when_repo_is_dirty(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=True, usr_access_value=None)
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado"),
			patch(f"{SYNTH_MODULE}._git_sha_tag", return_value=("deadbeef", True, "v1.0")),
		):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design", usr_access_type="git")
		assert synth_cfg.usr_access_value == int("deadbeef", 16) | 0x10000000

	def test_raises_if_git_sha_unavailable(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=True, usr_access_value=None)
		cfg.get_synth.return_value = synth_cfg
		with patch(f"{SYNTH_MODULE}._git_sha_tag", return_value=(None, False, None)):
			with pytest.raises(error.SynthUsrAccessValueEmbedGitShaError):
				cmd_synth(cfg, design_name="my_design", usr_access_type="git")

	def test_skips_usr_access_when_already_set(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=True, usr_access_value=0xABCD1234)
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado"),
			patch(f"{SYNTH_MODULE}._git_sha_tag") as mock_git,
		):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design", usr_access_type="git")
		mock_git.assert_not_called()
		assert synth_cfg.usr_access_value == 0xABCD1234

	def test_runs_parallel_subcores_when_ooc_enabled(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(out_of_context_subcores=True, has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		subcore = MagicMock()
		subcore.core = "my_core"
		cfg.get_subcore_list.return_value = [subcore]
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado"),
			patch(f"{SYNTH_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design")
		mock_parallel.assert_called_once()
		tasks = mock_parallel.call_args[0][0]
		assert len(tasks) == 1
		_, label = tasks[0]
		assert label == "my_core"

	def test_skips_parallel_without_ooc_subcores(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(out_of_context_subcores=False, has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado"),
			patch(f"{SYNTH_MODULE}.run_parallel") as mock_parallel,
		):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, design_name="my_design")
		mock_parallel.assert_not_called()

	def test_bd_name_forwarded_correctly(self):
		cfg = _make_cfg()
		synth_cfg = _make_synth_cfg(has_bitstream=False)
		cfg.get_synth.return_value = synth_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.synth.return_value.build.return_value = MagicMock()
			cmd_synth(cfg, bd_name="my_bd")
		cfg.validate_synth.assert_called_once_with(bd="my_bd", design=None, core=None)
		MockTcl.return_value.synth.assert_called_once_with(design=None, bd="my_bd", core=None, resume=None)


# ===========================================================================
# cmd_dcp_open
# ===========================================================================


class TestCmdDcpOpen:
	def test_builds_tcl_with_dcp_file(self):
		cfg = _make_cfg()
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.open_dcp.return_value.build.return_value = MagicMock()
			cmd_dcp_open(cfg, dcp_file="/path/to/file.dcp")
		MockTcl.return_value.open_dcp.assert_called_once_with(dcp_file="/path/to/file.dcp")

	def test_runs_vivado_with_built_config(self):
		cfg = _make_cfg()
		mock_config = MagicMock()
		with (
			patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl,
			patch(f"{SYNTH_MODULE}.vivado.run_vivado") as mock_run,
		):
			MockTcl.return_value.open_dcp.return_value.build.return_value = mock_config
			cmd_dcp_open(cfg, dcp_file="/path/to/file.dcp")
		mock_run.assert_called_once_with(cfg, config_tcl=mock_config)

	def test_sets_tcl_mode_when_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.open_dcp.return_value.build.return_value = MagicMock()
			cmd_dcp_open(cfg, dcp_file="/path/to/file.dcp", nogui=True)
		assert vivado_cfg.mode == "tcl"

	def test_does_not_change_mode_without_nogui(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.open_dcp.return_value.build.return_value = MagicMock()
			cmd_dcp_open(cfg, dcp_file="/path/to/file.dcp", nogui=False)
		assert vivado_cfg.mode == "batch"

	def test_nogui_defaults_to_false(self):
		cfg = _make_cfg()
		vivado_cfg = MagicMock()
		vivado_cfg.mode = "batch"
		cfg.get_vivado.return_value = vivado_cfg
		with patch(f"{SYNTH_MODULE}.ConfigTclCommands") as MockTcl, patch(f"{SYNTH_MODULE}.vivado.run_vivado"):
			MockTcl.return_value.open_dcp.return_value.build.return_value = MagicMock()
			cmd_dcp_open(cfg, dcp_file="/path/to/file.dcp")
		assert vivado_cfg.mode == "batch"
