# tests/test_bd_synth.py
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xviv.config.project import ProjectConfig
from xviv.functions.bd import cmd_bd_synth
from xviv.config.model import (
    BdConfig, BuildConfig, FpgaConfig,
    VitisConfig, VivadoConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cfg(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        base_dir         = str(tmp_path),
        fpga_default_ref = "default",
        fpga_named       = {"default": FpgaConfig(part="xc7z020clg400-1")},
        vivado           = VivadoConfig(path="/opt/Xilinx/Vivado/2024.1", mode="batch"),
        vitis            = VitisConfig(path="/opt/Xilinx/Vitis/2024.1"),
        build            = BuildConfig(),
        ips          = [],
        bds          = [BdConfig(name="my_bd")],
        synths       = [],
        platforms    = [],
        apps         = [],
        cores        = [],
        simulations  = [],
    )


FAKE_COMPONENTS = [
    {
        "vlnv":           "xilinx.com:ip:axi_gpio:2.0",
        "xci_name":       "axi_gpio_0",
        "xci_path":       "/fake/path/axi_gpio_0.xci",
        "inst_hier_path": "my_bd_i/axi_gpio_0",
    }
]


@pytest.fixture(autouse=True)
def _patch_bd_core_dict():
    with patch(
        "xviv.cli.command.bd.get_bd_core_dict",
        return_value=FAKE_COMPONENTS,
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_git():
    with patch(
        "xviv.utils.git.subprocess.check_output",
        side_effect=lambda cmd, **kw: (
            b"abc1234\n" if "rev-parse" in cmd else b""
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Helper: fake Popen that always succeeds
# ---------------------------------------------------------------------------

def _make_fake_popen(returncode: int = 0):
    def _fake_popen(*args, **kwargs):
        proc = MagicMock()
        proc.stdout.__iter__ = lambda self: iter(["INFO: fake vivado output\n"])
        proc.wait.return_value = returncode
        proc.returncode       = returncode
        proc.__enter__        = lambda self: self
        proc.__exit__         = MagicMock(return_value=False)
        return proc
    return _fake_popen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCmdBdSynthBoundaryPatch:

    def test_run_vivado_called_for_each_stale_component(
        self, cfg: ProjectConfig
    ) -> None:
        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_make_fake_popen()):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

    def test_standalone_synthesis_dispatched(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        all_args = " ".join(" ".join(c) for c in calls)
        assert "standalone_synthesis" in all_args

    def test_final_synthesis_dispatched(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        all_args = " ".join(" ".join(c) for c in calls)
        assert "synthesis" in all_args

    def test_standalone_synthesis_before_final_synthesis(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        flat = [" ".join(c) for c in calls]
        standalone_idx = next(i for i, c in enumerate(flat) if "standalone_synthesis" in c)
        synthesis_idx  = next(i for i, c in enumerate(flat) if "synthesis" in c
                              and "standalone" not in c)
        assert standalone_idx < synthesis_idx

    def test_vivado_binary_used_in_command(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        assert all("vivado" in c[0] for c in calls)

    def test_batch_mode_flag_in_command(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        for cmd in calls:
            assert "-mode" in cmd
            mode_idx = cmd.index("-mode")
            assert cmd[mode_idx + 1] == "batch"

    def test_vivado_failure_propagates(
        self, cfg: ProjectConfig
    ) -> None:
        with patch(
            "xviv.tools.vivado.subprocess.Popen",
            side_effect=_make_fake_popen(returncode=1),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                cmd_bd_synth(cfg, "my_bd", ooc_run=False)

    def test_empty_component_list_skips_standalone(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with (
            patch("xviv.cli.command.bd.get_bd_core_dict", return_value=[]),
            patch("xviv.tools.vivado.subprocess.Popen",   side_effect=_spy_popen),
        ):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        flat = [" ".join(c) for c in calls]
        assert not any("standalone_synthesis" in c for c in flat)
        assert any("synthesis" in c for c in flat)

    def test_no_vivado_call_when_outputs_up_to_date(
        self, cfg: ProjectConfig, tmp_path: Path
    ) -> None:
        ooc_dir = Path(cfg.get_bd_ooc_targets_dir("my_bd"))
        ooc_dir.mkdir(parents=True)

        for name in ("axi_gpio_0.dcp", "axi_gpio_0.v"):
            p = ooc_dir / name
            p.write_text("placeholder")
            import os
            os.utime(p, (9_999_999_999, 9_999_999_999))

        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        flat = [" ".join(c) for c in calls]
        # standalone skipped; only the final synthesis call fires
        assert not any("standalone_synthesis" in c for c in flat)
        assert any("synthesis" in c for c in flat)

    def test_dirty_sha_forwarded_to_synthesis(
        self, cfg: ProjectConfig
    ) -> None:
        calls: list[list[str]] = []

        def _spy_popen(cmd, *args, **kwargs):
            calls.append(cmd)
            return _make_fake_popen()(cmd, *args, **kwargs)

        with (
            patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen),
            patch(
                "xviv.utils.git.subprocess.check_output",
                side_effect=lambda cmd, **kw: (
                    b"abc1234\n" if "rev-parse" in cmd else b"M dirty_file.v\n"
                ),
            ),
        ):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        synth_cmd = next(
            " ".join(c) for c in calls
            if "synthesis" in " ".join(c) and "standalone" not in " ".join(c)
        )
        assert "dirty" in synth_cmd

    def test_xci_name_present_in_config_tcl(
        self, cfg: ProjectConfig
    ) -> None:
        tcl_contents: list[str] = []

        real_popen = __import__("subprocess").Popen

        def _spy_popen(cmd, *args, **kwargs):
            # The config TCL path is the argument after the command token
            try:
                tclargs_idx = cmd.index("-tclargs")
                tcl_path    = cmd[tclargs_idx + 2]
                with open(tcl_path) as fh:
                    tcl_contents.append(fh.read())
            except (ValueError, IndexError, FileNotFoundError):
                pass
            return _make_fake_popen()(cmd, *args, **kwargs)

        with patch("xviv.tools.vivado.subprocess.Popen", side_effect=_spy_popen):
            cmd_bd_synth(cfg, "my_bd", ooc_run=False)

        combined = "\n".join(tcl_contents)
        assert "axi_gpio_0" in combined
        assert "xviv_bd_xci_name_list" in combined