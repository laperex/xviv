# tests/test_tools_vivado.py

import subprocess
import pytest
from unittest.mock import patch, MagicMock, mock_open
from xviv.config.model import VivadoConfig, VitisConfig, FpgaConfig, BuildConfig
from xviv.config.project import XvivConfig
from xviv.tools.vivado import run_vivado


@pytest.fixture
def cfg(tmp_path):
    return XvivConfig(
        base_dir=str(tmp_path),
        fpga_default_ref="dev",
        fpga_named={"dev": FpgaConfig(fpga_part="xc7z020clg400-1")},
        vivado=VivadoConfig(path="/opt/vivado", mode="batch"),
        vitis=VitisConfig(),
        build=BuildConfig(),
        ips=[], bds=[], cores=[], synths=[],
        simulations=[], platforms=[], apps=[],
    )


class TestRunVivado:
    @patch("xviv.tools.vivado.subprocess.Popen")
    @patch("os.unlink")
    def test_calls_vivado_binary(self, mock_unlink, mock_popen, cfg, tmp_path):
        # Set up the mock process
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["INFO: done\n"])
        mock_proc.returncode = 0
        mock_proc.__enter__ = lambda s: s
        mock_proc.__exit__ = MagicMock(return_value=False)
        mock_popen.return_value = mock_proc

        with patch("builtins.open", mock_open()):
            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake.tcl"
                run_vivado(cfg, "/fake/vivado.tcl", "create_ip", [], "# tcl")

        called_cmd = mock_popen.call_args[0][0]
        assert "vivado" in called_cmd[0]
        assert "create_ip" in called_cmd

    @patch("xviv.tools.vivado.subprocess.Popen")
    @patch("os.unlink")
    def test_raises_on_nonzero_exit(self, mock_unlink, mock_popen, cfg):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 1
        mock_proc.__enter__ = lambda s: s
        mock_proc.__exit__ = MagicMock(return_value=False)
        mock_popen.return_value = mock_proc

        with patch("builtins.open", mock_open()):
            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake.tcl"
                with pytest.raises(subprocess.CalledProcessError):
                    run_vivado(cfg, "/fake/vivado.tcl", "synthesis", [], "# tcl")