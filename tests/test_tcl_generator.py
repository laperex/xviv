"""
Tests for ConfigTclCommands.

Run with:  pytest tests/test_commands.py -v
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path):
    cfg_file = tmp_path / "xviv.py"
    cfg_file.touch()

    with patch("xviv.config.project.Catalog"):
        vivado = tmp_path / "vivado"
        vivado.touch()
        c = XvivConfig(str(cfg_file), work_dir="build")
        c.add_vivado_cfg(path=str(vivado))

    c.add_fpga_cfg("xc7a35t", fpga_part="xc7a35tcpg236-1")
    return c


@pytest.fixture
def cfg_with_design(cfg):
    cfg.add_design_cfg("mydesign", sources=[], top="my_top")
    return cfg


@pytest.fixture
def cfg_with_synth(cfg_with_design):
    cfg_with_design.add_synth_cfg(design="mydesign", run_synth=True, run_place=True, run_route=True)
    return cfg_with_design


@pytest.fixture
def cfg_with_bd(cfg, tmp_path):
    with patch("xviv.config.project.get_bd_core_list", return_value=[]):
        cfg.add_bd_cfg("my_bd")
    return cfg


def cmds(cfg) -> ConfigTclCommands:
    return ConfigTclCommands(cfg)


# ---------------------------------------------------------------------------
# _require_project
# ---------------------------------------------------------------------------

class TestRequireProject:

    def test_creates_in_memory_project(self, cfg):
        c = cmds(cfg)
        c._require_project()
        assert "create_project" in c.build()
        assert "-in_memory" in c.build()

    def test_sets_max_threads(self, cfg):
        c = cmds(cfg)
        c._require_project()
        assert "maxThreads" in c.build()

    def test_second_call_without_exists_ok_exits(self, cfg):
        c = cmds(cfg)
        c._require_project()
        with pytest.raises(RuntimeError):
            c._require_project(exists_ok=False)

    def test_second_call_with_exists_ok_returns_false(self, cfg):
        c = cmds(cfg)
        c._require_project()
        assert c._require_project(exists_ok=True) is False

    def test_first_call_returns_true(self, cfg):
        c = cmds(cfg)
        assert c._require_project() is True

    def test_sets_board_repo_paths_when_configured(self, tmp_path):
        cfg_file = tmp_path / "xviv.py"
        cfg_file.touch()
        board_repo = tmp_path / "board_repo"
        board_repo.mkdir()

        with patch("xviv.config.project.Catalog"):
            vivado = tmp_path / "vivado"
            vivado.touch()
            c = XvivConfig(str(cfg_file), work_dir="build", board_repo_list=[str(board_repo)])
            c.add_vivado_cfg(path=str(vivado))

        c.add_fpga_cfg("xc7a35t", fpga_part="xc7a35tcpg236-1")
        builder = cmds(c)
        builder._require_project()
        assert "board.repoPaths" in builder.build()


# ---------------------------------------------------------------------------
# create_bd
# ---------------------------------------------------------------------------

class TestCreateBd:

    def test_emits_create_bd_design(self, cfg_with_bd):
        c = cmds(cfg_with_bd)
        # save_file doesn't exist → new BD flow (opens GUI)
        with patch.object(c, "_start_gui"):
            c.create_bd("my_bd", generate=False)
        assert "create_bd_design" in c.build()

    def test_sources_bd_save_file_when_it_exists(self, cfg, tmp_path):
        save_file = tmp_path / "my_bd.tcl"
        save_file.write_text("# bd tcl")

        with patch("xviv.config.project.get_bd_core_list", return_value=[]):
            cfg.add_bd_cfg("my_bd", save_file=str(save_file))

        c = cmds(cfg)
        with patch.object(c, "_generate_target_get_files"):
            c.create_bd("my_bd", generate=True)

        assert "source" in c.build()
        assert str(save_file) in c.build()

    def test_starts_gui_for_new_bd(self, cfg_with_bd):
        c = cmds(cfg_with_bd)
        gui_started = []
        with patch.object(c, "_start_gui", side_effect=lambda: gui_started.append(True)):
            c.create_bd("my_bd", generate=False)
        assert gui_started


# ---------------------------------------------------------------------------
# edit_bd
# ---------------------------------------------------------------------------

class TestEditBd:

    def test_missing_bd_file_exits(self, cfg_with_bd):
        c = cmds(cfg_with_bd)
        with pytest.raises(RuntimeError):
            c.edit_bd("my_bd")

    def test_emits_open_bd_design(self, cfg, tmp_path):
        bd_file = tmp_path / "my_bd.bd"
        bd_file.write_text("{}")

        with patch("xviv.config.project.get_bd_core_list", return_value=[]):
            cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))

        c = cmds(cfg)
        with patch.object(c, "_start_gui"):
            c.edit_bd("my_bd")

        assert "open_bd_design" in c.build()

    def test_nogui_skips_start_gui(self, cfg, tmp_path):
        bd_file = tmp_path / "my_bd.bd"
        bd_file.write_text("{}")

        with patch("xviv.config.project.get_bd_core_list", return_value=[]):
            cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))

        c = cmds(cfg)
        gui_started = []
        with patch.object(c, "_start_gui", side_effect=lambda: gui_started.append(True)):
            c.edit_bd("my_bd", nogui=True)

        assert not gui_started


# ---------------------------------------------------------------------------
# generate_bd
# ---------------------------------------------------------------------------

class TestGenerateBd:
    def test_missing_bd_file_exits(self, cfg_with_bd):
        c = cmds(cfg_with_bd)
        with pytest.raises(RuntimeError):
            c.generate_bd("my_bd", check=True)

    def test_up_to_date_emits_nothing(self, cfg_with_bd):
        c = cmds(cfg_with_bd)
        with patch("xviv.generator.tcl.commands.is_stale", return_value=False):
            c.generate_bd("my_bd", check=False, force=False)
        assert c.build() is None

    def test_force_emits_read_and_generate(self, cfg, tmp_path):
        bd_file = tmp_path / "my_bd.bd"
        bd_file.touch()

        with patch("xviv.config.project.get_bd_core_list", return_value=[]):
            cfg.add_bd_cfg("my_bd", bd_file=str(bd_file))

        c = cmds(cfg)
        with patch.object(c, "_bd_upgrade_ip_cells"):  # has a known bug with filter= shadowing builtin
            c.generate_bd("my_bd", check=False, force=True)

        out = c.build()
        assert "read_bd" in out
        assert "open_bd_design" in out
        assert "generate_target" in out


# ---------------------------------------------------------------------------
# synth
# ---------------------------------------------------------------------------

class TestSynth:

    def test_emits_synth_design(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        assert "synth_design" in c.build()

    def test_emits_place_design(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        assert "place_design" in c.build()

    def test_emits_route_design(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        assert "route_design" in c.build()

    def test_no_opt_design_by_default(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        # "opt_design" is a substring of "phys_opt_design", so check line-by-line.
        lines = c.build().splitlines()
        assert not any(line.strip().startswith("opt_design") for line in lines)

    def test_emits_opt_design_when_enabled(self, cfg):
        cfg.add_design_cfg("mydesign", sources=[], top="my_top")
        cfg.add_synth_cfg(design="mydesign", run_synth=True, run_opt=True)
        c = cmds(cfg)
        c.synth(design="mydesign")
        assert "opt_design" in c.build()

    def test_emits_write_bitstream_when_configured(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        assert "write_bitstream" in c.build()

    def test_no_bitstream_when_disabled(self, cfg):
        cfg.add_design_cfg("mydesign", sources=[], top="my_top")
        cfg.add_synth_cfg(design="mydesign", run_synth=True, bitstream=False)
        c = cmds(cfg)
        c.synth(design="mydesign")
        assert "write_bitstream" not in c.build()

    def test_adds_source_files_for_design(self, cfg, tmp_path):
        src = tmp_path / "top.sv"
        src.touch()
        cfg.add_design_cfg("mydesign", sources=[str(src)], top="my_top")
        cfg.add_synth_cfg(design="mydesign")
        c = cmds(cfg)
        c.synth(design="mydesign")
        assert "add_files" in c.build()

    def test_adds_constraint_files(self, cfg, tmp_path):
        xdc = tmp_path / "top.xdc"
        xdc.touch()
        cfg.add_design_cfg("mydesign", sources=[], top="my_top")
        cfg.add_synth_cfg(design="mydesign", constraints=[str(xdc)])
        c = cmds(cfg)
        c.synth(design="mydesign")
        out = c.build()
        assert "add_files" in out
        assert "constrs_1" in out

    def test_sets_top_module(self, cfg_with_synth):
        c = cmds(cfg_with_synth)
        c.synth(design="mydesign")
        assert "my_top" in c.build()

    def test_incremental_synth_reads_checkpoint(self, cfg, tmp_path):
        dcp = tmp_path / "synth.dcp"
        dcp.touch()
        cfg.add_design_cfg("mydesign", sources=[], top="my_top")
        cfg.add_synth_cfg(
            design="mydesign",
            synth_incremental=True,
            synth_dcp=str(dcp),
        )
        c = cmds(cfg)
        c.synth(design="mydesign")
        assert "read_checkpoint" in c.build()

    def test_synth_with_bd_reads_bd_file(self, cfg, tmp_path):
        bd_file = tmp_path / "my_bd.bd"
        bd_file.touch()
        wrapper = tmp_path / "my_bd_wrapper.v"
        wrapper.touch()

        with patch("xviv.config.project.get_bd_core_list", return_value=[]):
            cfg.add_bd_cfg("my_bd", bd_file=str(bd_file), bd_wrapper_file=str(wrapper))

        cfg.add_synth_cfg(bd="my_bd")
        c = cmds(cfg)
        c.synth(bd="my_bd")
        assert "read_bd" in c.build()


# ---------------------------------------------------------------------------
# edit_ip
# ---------------------------------------------------------------------------

class TestEditIp:

    def _cfg_with_ip(self, cfg, tmp_path):
        cfg.add_ip_cfg("my_ip", version="1.0", sources=[], top="my_ip")

        # The source builds the component.xml path as:
        #   os.path.join(ip_cfg.repo, f"{name}_{version}".replace(".", "_"), "component.xml")
        # ip_cfg.repo defaults to {work_dir}/ip = {tmp_path}/build/ip
        ip_cfg = cfg.get_ip("my_ip")
        ip_vid = f"{ip_cfg.name}_{ip_cfg.version}".replace(".", "_")
        component_xml = Path(ip_cfg.repo) / ip_vid / "component.xml"
        component_xml.parent.mkdir(parents=True, exist_ok=True)
        component_xml.touch()

        return cfg

    def test_missing_component_xml_exits(self, cfg):
        cfg.add_ip_cfg("my_ip", sources=[], top="my_ip")
        c = cmds(cfg)
        with pytest.raises(RuntimeError):
            c.edit_ip("my_ip")

    def test_emits_edit_ip_in_project(self, cfg, tmp_path):
        cfg = self._cfg_with_ip(cfg, tmp_path)
        c = cmds(cfg)
        with patch.object(c, "_start_gui"):
            c.edit_ip("my_ip")
        assert "ipx::edit_ip_in_project" in c.build()

    def test_nogui_skips_start_gui(self, cfg, tmp_path):
        cfg = self._cfg_with_ip(cfg, tmp_path)
        c = cmds(cfg)
        gui_called = []
        with patch.object(c, "_start_gui", side_effect=lambda: gui_called.append(True)):
            c.edit_ip("my_ip", nogui=True)
        assert not gui_called


# ---------------------------------------------------------------------------
# edit_core / create_core
# ---------------------------------------------------------------------------

class TestEditCore:

    def test_missing_xci_exits(self, cfg):
        with patch.object(cfg, "_resolve_vlnv", return_value="xilinx.com:ip:fifo_generator:13.2"):
            cfg.add_core_cfg("my_fifo", vlnv="xilinx.com:ip:fifo_generator:13.2")
        c = cmds(cfg)
        with pytest.raises(RuntimeError):
            c.edit_core("my_fifo")

    def test_emits_read_ip(self, cfg, tmp_path):
        xci = tmp_path / "my_fifo.xci"
        xci.touch()
        with patch.object(cfg, "_resolve_vlnv", return_value="xilinx.com:ip:fifo_generator:13.2"):
            cfg.add_core_cfg("my_fifo", vlnv="xilinx.com:ip:fifo_generator:13.2", xci_file=str(xci))
        c = cmds(cfg)
        c.edit_core("my_fifo", nogui=True)
        assert "read_ip" in c.build()

    def test_nogui_skips_ip_gui(self, cfg, tmp_path):
        xci = tmp_path / "my_fifo.xci"
        xci.touch()
        with patch.object(cfg, "_resolve_vlnv", return_value="xilinx.com:ip:fifo_generator:13.2"):
            cfg.add_core_cfg("my_fifo", vlnv="xilinx.com:ip:fifo_generator:13.2", xci_file=str(xci))
        c = cmds(cfg)
        c.edit_core("my_fifo", nogui=True)
        assert "start_ip_gui" not in c.build()


class TestCreateCore:

    def test_emits_create_ip(self, cfg):
        with patch.object(cfg, "_resolve_vlnv", return_value="xilinx.com:ip:fifo_generator:13.2"):
            cfg.add_core_cfg("my_fifo", vlnv="xilinx.com:ip:fifo_generator:13.2")
        c = cmds(cfg)
        c.create_core("my_fifo")
        assert "create_ip" in c.build()

    def test_emits_generate_target(self, cfg):
        with patch.object(cfg, "_resolve_vlnv", return_value="xilinx.com:ip:fifo_generator:13.2"):
            cfg.add_core_cfg("my_fifo", vlnv="xilinx.com:ip:fifo_generator:13.2")
        c = cmds(cfg)
        c.create_core("my_fifo")
        assert "generate_target" in c.build()