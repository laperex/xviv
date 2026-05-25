"""
Comprehensive tests for xviv — real-world usage patterns, edge cases, mocking.

Organised into cohesive "scenario" sections that mirror how engineers actually
use xviv:

1. Minimal Artix-7 RTL project (the README getting-started example)
2. Block-design + embedded platform project (MicroBlaze / Vitis)
3. Custom IP packaging + wrapper flow
4. Multi-FPGA project (different parts share a config)
5. Simulation – xsim and verilator, with UVM
6. Formal verification (sby generation)
7. Multi-stage synthesis flags / incremental flows
8. Source-file resolution: globs, stage tags, dirty edge cases
9. Duplicate / missing entity error coverage
10. Parallel-job error aggregation
11. Filesystem helpers (resolve_globs, is_stale, assert_file_exists)
12. Git SHA helpers (mocked subprocess)
13. _resolve_val coverage
14. FormalConfig validation (__post_init__)
15. run_formal dry-run path (no real `sby` needed)
16. SubCore identifier guards
17. Platform / App validation flows
18. TOML config loader
"""

from __future__ import annotations

import subprocess
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xviv.config.model import FormalConfig, SourceFile
from xviv.config.project import XvivConfig, _resolve_val
from xviv.functions.formal import FormalResult, generate_sby, run_formal
from xviv.utils import error
from xviv.utils.fs import assert_file_exists, is_stale, resolve_globs
from xviv.utils.git import _git_sha_tag
from xviv.utils.parallel import run_parallel

# ---------------------------------------------------------------------------
# Shared helpers & fixtures
# ---------------------------------------------------------------------------


def _project(tmp_path, *, work_dir=None) -> XvivConfig:
	"""Create an XvivConfig backed by a real (empty) project.toml."""
	config_file = tmp_path / "project.toml"
	config_file.touch()
	return XvivConfig(
		str(config_file),
		work_dir=work_dir or str(tmp_path / "build"),
	)


def _touch(path) -> str:
	"""Create an empty file and every parent directory; return string path."""
	p = Path(path)
	p.parent.mkdir(parents=True, exist_ok=True)
	p.touch()
	return str(p)


def _write(path, content: str) -> str:
	p = Path(path)
	p.parent.mkdir(parents=True, exist_ok=True)
	p.write_text(content)
	return str(p)


@pytest.fixture
def tmp(tmp_path):
	return tmp_path


@pytest.fixture
def bare(tmp_path) -> XvivConfig:
	"""Bare config – no fpga, no vivado."""
	return _project(tmp_path)


@pytest.fixture
def artix(tmp_path) -> XvivConfig:
	"""Typical Artix-7 project – single FPGA, RTL design, synth."""
	cfg = _project(tmp_path)
	cfg.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
	return cfg


@pytest.fixture
def zynq(tmp_path) -> XvivConfig:
	"""Zynq UltraScale project with vivado / vitis configured."""
	cfg = _project(tmp_path)
	cfg.add_fpga_cfg("zu9", fpga_part="xczu9eg-ffvb1156-2-e")
	viv_dir = tmp_path / "vivado"
	viv_dir.mkdir()
	cfg.add_vivado_cfg(str(viv_dir))
	vitis_dir = tmp_path / "vitis"
	vitis_dir.mkdir()
	cfg.add_vitis_cfg(str(vitis_dir))
	return cfg


# ===========================================================================
# 1. Minimal Artix-7 RTL project  (README getting-started)
# ===========================================================================


class TestMinimalRtlProject:
	"""
	Mirrors the README example:

		[[fpga]]  name = "main"  fpga_part = "xc7a200tfbg484-1"
		[[design]] name = "top"  sources = ["srcs/rtl/**/*.sv"]
		[[synth]]  design = "top"  constraints = ["constraints/top.xdc"]
	"""

	def test_fpga_defaults_to_first_entry(self, artix):
		assert artix._get_fpga_cfg_default.name == "main"
		assert artix._get_fpga_cfg_default.fpga_part == "xc7a200tfbg484-1"

	def test_add_design_infers_top_from_name(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		d = artix.get_design("top")
		assert d.top == "top"
		assert d.fpga_ref == "main"

	def test_add_design_explicit_top(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/cpu.sv")
		artix.add_design_cfg("cpu_design", sources=[src], top="cpu_core")
		assert artix.get_design("cpu_design").top == "cpu_core"

	def test_synth_wires_design_fpga(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		xdc = _touch(tmp_path / "constraints/top.xdc")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", constraints=[xdc])
		sc = artix.get_synth(design_name="top")
		assert sc.fpga_ref == "main"
		assert sc.top == "top"

	def test_synth_creates_expected_checkpoint_paths(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top")
		sc = artix.get_synth(design_name="top")
		build_dir = str(tmp_path / "build")
		assert sc.synth_dcp_file and sc.synth_dcp_file.startswith(build_dir)
		assert "top" in sc.synth_dcp_file
		assert sc.place_dcp_file and "top" in sc.place_dcp_file
		assert sc.route_dcp_file and "top" in sc.route_dcp_file

	def test_synth_bitstream_enabled_by_default_for_design(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top")
		sc = artix.get_synth(design_name="top")
		assert sc.bitstream_file is not None
		assert sc.bitstream_file.endswith(".bit")

	def test_synth_hw_platform_disabled_for_plain_design(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top")
		sc = artix.get_synth(design_name="top")
		# plain RTL design: no XSA by default
		assert sc.hw_platform_xsa_file is None

	def test_validate_design_succeeds_when_sources_exist(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.validate_design("top")  # must not raise

	def test_validate_design_fails_when_source_missing(self, artix, tmp_path):
		artix.add_design_cfg("top", sources=[str(tmp_path / "srcs/rtl/ghost.sv")])
		with pytest.raises(error.DesignSourcesMissingError):
			artix.validate_design("top")

	def test_validate_synth_fails_when_constraint_missing(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", constraints=[str(tmp_path / "no.xdc")])
		with pytest.raises(error.SynthConstraintsMissingError):
			artix.validate_synth(design="top")

	def test_validate_synth_succeeds_when_constraint_exists(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/rtl/top.sv")
		xdc = _touch(tmp_path / "constraints/top.xdc")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", constraints=[xdc])
		artix.validate_synth(design="top")  # must not raise

	def test_custom_build_dir_reflected_in_synth_paths(self, tmp_path):
		cfg = _project(tmp_path, work_dir=str(tmp_path / "out"))
		cfg.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		src = _touch(tmp_path / "top.sv")
		cfg.add_design_cfg("top", sources=[src])
		cfg.add_synth_cfg(design="top")
		sc = cfg.get_synth(design_name="top")
		assert "out" in sc.synth_dcp_file


# ===========================================================================
# 2. Block-design + embedded platform project (MicroBlaze / Vitis)
# ===========================================================================


class TestBlockDesignEmbeddedFlow:
	"""
	Covers:
		[[bd]] name = "system"
		[[synth]] bd = "system"
		[[platform]] name = "mb_platform"  bd = "system"  cpu = "microblaze_0"
		[[app]] name = "firmware"  platform = "mb_platform"
	"""

	def _setup(self, cfg: XvivConfig, tmp_path):
		cfg.add_bd_cfg("system")
		xdc = _touch(tmp_path / "constraints/system.xdc")
		cfg.add_synth_cfg(
			bd="system",
			constraints=[xdc],
			run_synth=True,
			run_place=True,
			run_route=True,
		)
		return cfg

	def test_bd_synth_top_defaults_to_wrapper(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		sc = artix.get_synth(bd_name="system")
		assert sc.top == "system_wrapper"

	def test_bd_synth_bitstream_and_xsa_enabled(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		sc = artix.get_synth(bd_name="system")
		assert sc.bitstream_file is not None
		assert sc.hw_platform_xsa_file is not None

	def test_platform_links_xsa_to_synth_output(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system", cpu="microblaze_0")
		pf = artix.get_platform("mb_platform")
		sc = artix.get_synth(bd_name="system")
		assert pf.xsa_file == sc.hw_platform_xsa_file

	def test_platform_links_bitstream_to_synth_output(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		pf = artix.get_platform("mb_platform")
		sc = artix.get_synth(bd_name="system")
		assert pf.bitstream_file == sc.bitstream_file

	def test_app_config_stores_elf_under_app_subdir(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		artix.add_app_cfg("firmware", platform="mb_platform")
		app = artix.get_app("firmware")
		assert "firmware" in app.elf_file
		assert app.elf_file.endswith(".elf")

	def test_app_default_template(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		artix.add_app_cfg("firmware", platform="mb_platform")
		assert artix.get_app("firmware").template == "empty_application"

	def test_platform_properties_flattened_correctly(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg(
			"mb_platform",
			bd="system",
			properties={"CONFIG": {"stdout": "mdm_1", "stdin": "mdm_1"}},
		)
		pf = artix.get_platform("mb_platform")
		prop_dict = dict(pf.properties)
		assert prop_dict.get("CONFIG.stdout") == "mdm_1"
		assert prop_dict.get("CONFIG.stdin") == "mdm_1"

	def test_platform_deeply_nested_properties(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg(
			"mb_platform",
			bd="system",
			properties={"A": {"B": {"C": "val"}}},
		)
		pf = artix.get_platform("mb_platform")
		prop_dict = dict(pf.properties)
		assert prop_dict["A.B.C"] == "val"

	def test_validate_platform_fails_when_xsa_missing(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		with pytest.raises(error.PlatformXsaMissingError):
			artix.validate_platform("mb_platform")

	def test_validate_platform_fails_when_bitstream_missing(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		pf = artix.get_platform("mb_platform")
		# create XSA but not bitstream
		_touch(pf.xsa_file)
		with pytest.raises(error.PlatformBitstreamMissingError):
			artix.validate_platform("mb_platform")

	def test_validate_platform_succeeds_when_both_exist(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		pf = artix.get_platform("mb_platform")
		_touch(pf.xsa_file)
		_touch(pf.bitstream_file)
		artix.validate_platform("mb_platform")  # must not raise

	def test_validate_app_fails_when_elf_missing(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		artix.add_app_cfg("firmware", platform="mb_platform")
		with pytest.raises(error.AppElfMissingError):
			artix.validate_app("firmware")

	def test_validate_app_no_sources_raises(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		artix.add_app_cfg("firmware", platform="mb_platform")
		app = artix.get_app("firmware")
		_touch(app.elf_file)
		with pytest.raises(error.AppSourcesEmptyError):
			artix.validate_app("firmware")

	def test_validate_app_succeeds_with_elf_and_sources(self, artix, tmp_path):
		self._setup(artix, tmp_path)
		artix.add_platform_cfg("mb_platform", bd="system")
		src = _touch(tmp_path / "fw/main.c")
		artix.add_app_cfg("firmware", platform="mb_platform", sources=[src])
		app = artix.get_app("firmware")
		_touch(app.elf_file)
		artix.validate_app("firmware")  # must not raise


# ===========================================================================
# 3. Custom IP packaging + wrapper flow
# ===========================================================================


class TestCustomIpFlow:
	"""
	Covers:
		[[ip]] name = "gamma_axi"  sources = ["srcs/ip/gamma_axi/**/*.sv"]
		[[wrapper]] ip = "gamma_axi"  sources = [...]
	"""

	def test_add_ip_default_vlnv_structure(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		ip = artix.get_ip("gamma_axi")
		assert ip.vlnv == "xviv.org:xviv:gamma_axi:1.0"

	def test_add_ip_custom_vlnv(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/my_ip/my_ip.sv")
		artix.add_ip_cfg("my_ip", sources=[src], vendor="acme", library="custom", version="2.1")
		ip = artix.get_ip("my_ip")
		assert ip.vlnv == "acme:custom:my_ip:2.1"

	def test_add_ip_top_defaults_to_name(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		assert artix.get_ip("gamma_axi").top == "gamma_axi"

	def test_add_ip_custom_top(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/foo/foo.sv")
		artix.add_ip_cfg("foo", sources=[src], top="foo_top")
		assert artix.get_ip("foo").top == "foo_top"

	def test_ip_repo_added_to_list(self, artix, tmp_path):
		repo = tmp_path / "custom_repo"
		repo.mkdir()
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src], repo=str(repo))
		assert str(repo) in artix.ip_repo_list

	def test_add_wrapper_creates_correct_wrapper_top(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		wsrc = _touch(tmp_path / "srcs/wrapper/gamma_axi_wrapper.sv")
		artix.add_wrapper_cfg(ip="gamma_axi", sources=[wsrc])
		w = artix.get_wrapper("gamma_axi")
		assert w.wrapper_top == "gamma_axi_wrapper"
		assert w.ip_top == "gamma_axi"

	def test_add_wrapper_custom_top(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		wsrc = _touch(tmp_path / "srcs/wrapper/flat.sv")
		artix.add_wrapper_cfg(ip="gamma_axi", sources=[wsrc], wrapper_top="flat_top")
		w = artix.get_wrapper("gamma_axi")
		assert w.wrapper_top == "flat_top"

	def test_add_wrapper_without_ip_raises(self, artix, tmp_path):
		wsrc = _touch(tmp_path / "srcs/wrapper/gamma_axi_wrapper.sv")
		with pytest.raises(error.WrapperIpMissing):
			artix.add_wrapper_cfg(ip="gamma_axi", sources=[wsrc])

	def test_validate_ip_raises_when_source_missing(self, artix, tmp_path):
		artix.add_ip_cfg("gamma_axi", sources=[str(tmp_path / "nonexistent.sv")])
		with pytest.raises(error.IpSourcesMissingError):
			artix.validate_ip("gamma_axi")

	def test_validate_ip_raises_when_no_sources(self, artix, tmp_path):
		artix.add_ip_cfg("gamma_axi", sources=[])
		with pytest.raises(error.IpSourcesEmptyError):
			artix.validate_ip("gamma_axi")

	def test_validate_ip_passes_when_source_exists(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		artix.validate_ip("gamma_axi")  # must not raise

	def test_validate_wrapper_raises_when_source_missing(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		artix.add_wrapper_cfg(ip="gamma_axi", sources=[str(tmp_path / "no_wrapper.sv")])
		with pytest.raises(error.WrapperSourcesMissingError):
			artix.validate_wrapper("gamma_axi")

	def test_validate_wrapper_raises_when_no_sources(self, artix, tmp_path):
		src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		artix.add_wrapper_cfg(ip="gamma_axi", sources=[])
		with pytest.raises(error.WrapperSourcesEmptyError):
			artix.validate_wrapper("gamma_axi")


# ===========================================================================
# 4. Multi-FPGA project
# ===========================================================================


class TestMultiFpgaProject:
	"""
	Two FPGAs in the same config:
	[[fpga]] name = "main"  fpga_part = "xc7a200tfbg484-1"
	[[fpga]] name = "aux"   fpga_part = "xc7a35tcsg324-1"
	"""

	def test_default_fpga_is_first_entry(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_fpga_cfg("aux", fpga_part="xc7a35tcsg324-1")
		assert bare._get_fpga_cfg_default.name == "main"

	def test_get_fpga_by_name(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_fpga_cfg("aux", fpga_part="xc7a35tcsg324-1")
		assert bare.get_fpga("aux").fpga_part == "xc7a35tcsg324-1"

	def test_get_fpga_none_returns_default(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		assert bare.get_fpga(None).name == "main"

	def test_design_pinned_to_specific_fpga(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_fpga_cfg("aux", fpga_part="xc7a35tcsg324-1")
		src = _touch(tmp_path / "blinky.sv")
		bare.add_design_cfg("blinky", sources=[src], fpga="aux")
		assert bare.get_design("blinky").fpga_ref == "aux"

	def test_fpga_board_part_only(self, bare, tmp_path):
		bare.add_fpga_cfg("board", board_part="xilinx.com:zcu102:part0:3.4")
		fp = bare.get_fpga("board")
		assert fp.board_part == "xilinx.com:zcu102:part0:3.4"
		assert fp.fpga_part is None

	def test_fpga_part_unspecified_raises(self, bare, tmp_path):
		with pytest.raises(error.FpgaPartUnspecifiedError):
			bare.add_fpga_cfg("empty")

	def test_no_fpga_default_raises(self, bare, tmp_path):
		with pytest.raises(error.NoFpgaError):
			_ = bare._get_fpga_cfg_default

	def test_design_references_unknown_fpga_raises(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		src = _touch(tmp_path / "top.sv")
		with pytest.raises(error.FpgaResolveError):
			bare.add_design_cfg("top", sources=[src], fpga="unknown_fpga")


# ===========================================================================
# 5. Simulation – xsim and verilator, UVM
# ===========================================================================


class TestSimulationConfig:
	def test_sim_top_defaults_to_name(self, artix, tmp_path):
		src = _touch(tmp_path / "tb_top.sv")
		artix.add_sim_cfg("tb_top", sources=[src])
		assert artix.get_sim("tb_top").top == "tb_top"

	def test_sim_custom_top(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src], top="tb_module")
		assert artix.get_sim("tb_top").top == "tb_module"

	def test_sim_default_backend_is_xsim(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src])
		assert artix.get_sim("tb_top").backend == "xsim"

	def test_sim_verilator_backend_stored(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src], backend="verilator")
		assert artix.get_sim("tb_top").backend == "verilator"

	def test_sim_invalid_backend_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		with pytest.raises(error.InvalidSimulationBackend):
			artix.add_sim_cfg("tb_top", sources=[src], backend="questa")

	def test_sim_timescale_default(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src])
		assert artix.get_sim("tb_top").timescale == "1ns/1ps"

	def test_sim_custom_timescale(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src], timescale="1ps/1fs")
		assert artix.get_sim("tb_top").timescale == "1ps/1fs"

	def test_sim_work_dir_under_build_sim(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb_top", sources=[src])
		sim = artix.get_sim("tb_top")
		assert "sim" in sim.work_dir
		assert "tb_top" in sim.work_dir

	def test_uvm_config_attached_to_simulation(self, artix, tmp_path):
		src = _touch(tmp_path / "tb_gamma.sv")
		artix.add_sim_cfg("tb_gamma", sources=[src])
		artix.add_uvm_cfg(test="gamma_basic_test", simulation="tb_gamma")
		uvm = artix.get_uvm("gamma_basic_test", "tb_gamma")
		assert uvm.test == "gamma_basic_test"
		assert uvm.simulation == "tb_gamma"

	def test_uvm_verbosity_default_is_uvm_medium(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src])
		artix.add_uvm_cfg(test="my_test", simulation="tb")
		assert artix.get_uvm("my_test", "tb").verbosity == "UVM_MEDIUM"

	def test_uvm_custom_verbosity(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src])
		artix.add_uvm_cfg(test="my_test", simulation="tb", verbosity="UVM_HIGH")
		assert artix.get_uvm("my_test", "tb").verbosity == "UVM_HIGH"

	def test_multiple_uvm_tests_for_same_sim(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src])
		artix.add_uvm_cfg(test="test_a", simulation="tb")
		artix.add_uvm_cfg(test="test_b", simulation="tb")
		assert artix.get_uvm("test_a", "tb").test == "test_a"
		assert artix.get_uvm("test_b", "tb").test == "test_b"

	def test_uvm_inline_in_sim_cfg(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg(
			"tb",
			sources=[src],
			uvm=[{"test": "inline_test"}],
		)
		assert artix.get_uvm("inline_test", "tb").test == "inline_test"

	def test_uvm_verilator_requires_pkg_dir(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src], backend="verilator")
		# verilator without uvm_pkg_dir should raise when adding UVM
		with pytest.raises(error.UvmPkgDirRequiredError):
			artix.add_uvm_cfg(test="uvm_test", simulation="tb")

	def test_uvm_verilator_with_pkg_dir_succeeds(self, artix, tmp_path):
		pkg = tmp_path / "uvm_pkg"
		pkg.mkdir()
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src], backend="verilator", uvm_pkg_dir=str(pkg))
		artix.add_uvm_cfg(test="uvm_test", simulation="tb")
		assert artix.get_uvm("uvm_test", "tb") is not None

	def test_sim_defines_and_plusargs_stored(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src], defines=["GATE_SIM", "DEBUG"], plusargs=["+verbose"])
		sim = artix.get_sim("tb")
		assert "GATE_SIM" in sim.defines
		assert "+verbose" in sim.plusargs

	def test_sim_verilator_trace_options(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src], backend="verilator", trace=True, trace_fst=True, trace_depth=20)
		sim = artix.get_sim("tb")
		assert sim.trace is True
		assert sim.trace_fst is True
		assert sim.trace_depth == 20


# ===========================================================================
# 6. Formal verification (sby generation)
# ===========================================================================


class TestFormalConfig:
	def _make_formal(self, tmp_path, **kwargs) -> FormalConfig:
		defaults = dict(
			name="gamma_props",
			top="gamma_axi",
			mode="prove",
			sources=[str(tmp_path / "gamma_axi.sv"), str(tmp_path / "gamma_axi_props.sv")],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=20,
			append=0,
			engine="smtbmc yices z3",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		defaults.update(kwargs)
		return FormalConfig(**defaults)

	def test_formal_invalid_mode_raises_in_post_init(self, tmp_path):
		with pytest.raises(error.FormalInvalidModeError):
			self._make_formal(tmp_path, mode="fuzz")

	def test_formal_valid_modes_accepted(self, tmp_path):
		for mode in ("bmc", "prove", "cover"):
			cfg = self._make_formal(tmp_path, mode=mode)
			assert cfg.mode == mode

	def test_generate_sby_options_section(self, tmp_path):
		cfg = self._make_formal(tmp_path, mode="prove", depth=30)
		sby = generate_sby(cfg)
		assert "[options]" in sby
		assert "mode prove" in sby
		assert "depth 30" in sby

	def test_generate_sby_cover_append(self, tmp_path):
		cfg = self._make_formal(tmp_path, mode="cover", depth=10, append=5)
		sby = generate_sby(cfg)
		assert "append 5" in sby

	def test_generate_sby_prove_no_append(self, tmp_path):
		"""append line should be suppressed for prove/bmc modes."""
		cfg = self._make_formal(tmp_path, mode="prove", append=5)
		sby = generate_sby(cfg)
		assert "append" not in sby

	def test_generate_sby_engines_section(self, tmp_path):
		cfg = self._make_formal(tmp_path, engine="smtbmc boolector")
		sby = generate_sby(cfg)
		assert "[engines]" in sby
		assert "smtbmc boolector" in sby

	def test_generate_sby_script_section(self, tmp_path):
		cfg = self._make_formal(tmp_path)
		sby = generate_sby(cfg)
		assert "[script]" in sby
		assert "hierarchy -check -top gamma_axi" in sby
		assert "proc" in sby
		assert "flatten" in sby

	def test_generate_sby_files_section(self, tmp_path):
		src1 = str(tmp_path / "gamma_axi.sv")
		src2 = str(tmp_path / "gamma_axi_props.sv")
		cfg = self._make_formal(tmp_path, sources=[src1, src2])
		sby = generate_sby(cfg)
		assert "[files]" in sby
		assert src1 in sby
		assert src2 in sby

	def test_generate_sby_sv_flag_on_first_read(self, tmp_path):
		cfg = self._make_formal(tmp_path)
		sby = generate_sby(cfg)
		assert "-sv" in sby

	def test_generate_sby_sv_disabled(self, tmp_path):
		cfg = self._make_formal(tmp_path, sv=False)
		sby = generate_sby(cfg)
		lines = sby.splitlines()
		script_lines = lines[lines.index("[script]") + 1 :]
		first_read = next(l for l in script_lines if "read_verilog" in l)
		assert "-sv" not in first_read

	def test_generate_sby_defines_included(self, tmp_path):
		cfg = self._make_formal(tmp_path, defines=["FORMAL", "NOASSERT"])
		sby = generate_sby(cfg)
		assert "-D FORMAL" in sby
		assert "-D NOASSERT" in sby

	def test_generate_sby_include_dirs_included(self, tmp_path):
		cfg = self._make_formal(tmp_path, include_dirs=["/some/include", "/other"])
		sby = generate_sby(cfg)
		assert "-I /some/include" in sby
		assert "-I /other" in sby

	def test_generate_sby_multiclock(self, tmp_path):
		cfg = self._make_formal(tmp_path, multiclock=True)
		sby = generate_sby(cfg)
		assert "multiclock on" in sby

	def test_generate_sby_async2sync(self, tmp_path):
		cfg = self._make_formal(tmp_path, async2sync=True)
		sby = generate_sby(cfg)
		assert "async2sync" in sby

	def test_generate_sby_extra_script_appended(self, tmp_path):
		cfg = self._make_formal(tmp_path, extra_script=["cover -show"])
		sby = generate_sby(cfg)
		assert "cover -show" in sby

	def test_generate_sby_extra_opts_appended(self, tmp_path):
		cfg = self._make_formal(tmp_path, extra_opts=["expect pass"])
		sby = generate_sby(cfg)
		assert "expect pass" in sby

	def test_formal_add_to_config(self, artix, tmp_path):
		src1 = _touch(tmp_path / "gamma_axi.sv")
		src2 = _touch(tmp_path / "gamma_axi_props.sv")
		artix.add_formal_cfg(
			"gamma_props",
			top="gamma_axi",
			mode="prove",
			sources=[src1, src2],
			depth=30,
		)
		fcfg = artix.get_formal("gamma_props")
		assert fcfg.mode == "prove"
		assert fcfg.depth == 30

	def test_validate_formal_fails_when_source_missing(self, artix, tmp_path):
		artix.add_formal_cfg(
			"gamma_props",
			top="gamma_axi",
			mode="bmc",
			sources=[str(tmp_path / "ghost.sv")],
		)
		with pytest.raises(error.FormalSourceMissingError):
			artix.validate_formal("gamma_props")

	def test_validate_formal_passes_when_sources_exist(self, artix, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		artix.add_formal_cfg("gamma_props", top="gamma_axi", mode="bmc", sources=[src])
		artix.validate_formal("gamma_props")  # must not raise

	def test_get_formal_list_returns_all(self, artix, tmp_path):
		src = _touch(tmp_path / "a.sv")
		artix.add_formal_cfg("p1", top="m1", mode="bmc", sources=[src])
		artix.add_formal_cfg("p2", top="m2", mode="prove", sources=[src])
		assert len(artix.get_formal_list()) == 2

	def test_run_formal_dry_run_returns_pass(self, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		cfg = FormalConfig(
			name="gamma_props",
			top="gamma_axi",
			mode="prove",
			sources=[src],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=20,
			append=0,
			engine="smtbmc yices",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		result = run_formal(cfg, dry_run=True)
		assert isinstance(result, FormalResult)
		assert result.passed is True
		assert result.last_line == "(dry-run)"
		assert result.vcd is None

	def test_run_formal_writes_sby_file(self, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		cfg = FormalConfig(
			name="gamma_props",
			top="gamma_axi",
			mode="prove",
			sources=[src],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=20,
			append=0,
			engine="smtbmc yices",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		result = run_formal(cfg, dry_run=True)
		sby = tmp_path / "formal" / "gamma_props.sby"
		assert sby.exists()
		assert "mode prove" in sby.read_text()

	@patch("shutil.which", return_value=None)
	def test_run_formal_raises_when_sby_not_found(self, mock_which, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		cfg = FormalConfig(
			name="gamma_props",
			top="gamma_axi",
			mode="bmc",
			sources=[src],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=10,
			append=0,
			engine="smtbmc",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		with pytest.raises(error.FormalSbyNotFoundError):
			run_formal(cfg, dry_run=False)

	@patch("shutil.which", return_value="/usr/bin/sby")
	@patch("subprocess.Popen")
	def test_run_formal_pass_when_returncode_zero(self, mock_popen, mock_which, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		cfg = FormalConfig(
			name="gamma_props",
			top="gamma_axi",
			mode="bmc",
			sources=[src],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=10,
			append=0,
			engine="smtbmc",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		proc = MagicMock()
		proc.returncode = 0
		proc.stdout = iter(["[gamma_props] PASS\n"])
		proc.__enter__ = lambda s: proc
		proc.__exit__ = MagicMock(return_value=False)
		mock_popen.return_value = proc
		result = run_formal(cfg, dry_run=False)
		assert result.passed is True

	@patch("shutil.which", return_value="/usr/bin/sby")
	@patch("subprocess.Popen")
	def test_run_formal_fail_when_returncode_nonzero(self, mock_popen, mock_which, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		cfg = FormalConfig(
			name="gamma_props",
			top="gamma_axi",
			mode="bmc",
			sources=[src],
			work_dir=str(tmp_path / "formal" / "gamma_props"),
			depth=10,
			append=0,
			engine="smtbmc",
			defines=[],
			include_dirs=[],
			multiclock=False,
			async2sync=False,
			sv=True,
			extra_script=[],
			extra_opts=[],
		)
		proc = MagicMock()
		proc.returncode = 1
		proc.stdout = iter(["[gamma_props] FAIL: property violated at step 5\n"])
		proc.__enter__ = lambda s: proc
		proc.__exit__ = MagicMock(return_value=False)
		mock_popen.return_value = proc
		result = run_formal(cfg, dry_run=False)
		assert result.passed is False


# ===========================================================================
# 7. Multi-stage synthesis flags / incremental flows
# ===========================================================================


class TestSynthFlags:
	def test_synth_out_of_context_mode_for_core(self, artix, tmp_path):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_synth_cfg(core="clk_wiz_0")
		sc = artix.get_synth(core_name="clk_wiz_0")
		assert sc.synth_mode == "out_of_context"

	def test_synth_core_bitstream_disabled(self, artix, tmp_path):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_synth_cfg(core="clk_wiz_0")
		sc = artix.get_synth(core_name="clk_wiz_0")
		assert sc.bitstream_file is None

	def test_synth_core_stub_enabled_by_default(self, artix, tmp_path):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_synth_cfg(core="clk_wiz_0")
		sc = artix.get_synth(core_name="clk_wiz_0")
		assert sc.synth_stub_file is not None

	def test_synth_design_default_mode_is_default(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top")
		sc = artix.get_synth(design_name="top")
		assert sc.synth_mode == "default"

	def test_synth_explicit_directives_stored(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(
			design="top",
			synth_directive="AreaOptimized_high",
			place_directive="AltSpreadLogic_high",
			route_directive="AggressiveExplore",
			phys_opt_directive="AggressiveExplore",
			opt_directive="AggressiveExplore",
		)
		sc = artix.get_synth(design_name="top")
		assert sc.synth_directive == "AreaOptimized_high"
		assert sc.place_directive == "AltSpreadLogic_high"
		assert sc.route_directive == "AggressiveExplore"

	def test_synth_disable_all_stages(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(
			design="top",
			run_synth=False,
			run_opt=False,
			run_place=False,
			run_phys_opt=False,
			run_route=False,
		)
		sc = artix.get_synth(design_name="top")
		assert sc.run_synth is False
		assert sc.run_place is False
		assert sc.run_route is False

	def test_synth_disable_all_dcps(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(
			design="top",
			synth_dcp=False,
			place_dcp=False,
			route_dcp=False,
		)
		sc = artix.get_synth(design_name="top")
		assert sc.synth_dcp_file is None
		assert sc.place_dcp_file is None
		assert sc.route_dcp_file is None

	def test_synth_custom_dcp_paths(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(
			design="top",
			synth_dcp=str(tmp_path / "my_synth.dcp"),
			route_dcp=str(tmp_path / "my_route.dcp"),
		)
		sc = artix.get_synth(design_name="top")
		assert sc.synth_dcp_file == str(tmp_path / "my_synth.dcp")
		assert sc.route_dcp_file == str(tmp_path / "my_route.dcp")

	def test_synth_usr_access_value_stored(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", usr_access_value=0xDEADBEEF)
		sc = artix.get_synth(design_name="top")
		assert sc.usr_access_value == 0xDEADBEEF

	def test_synth_report_flags_enabled(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(
			design="top",
			synth_report_timing_summary=True,
			synth_report_utilization=True,
			route_report_drc=True,
			route_report_power=True,
		)
		sc = artix.get_synth(design_name="top")
		assert sc.synth_report_timing_summary_file is not None
		assert sc.synth_report_utilization_file is not None
		assert sc.route_report_drc_file is not None
		assert sc.route_report_power_file is not None

	def test_synth_impl_timing_sdf_auto_enables_when_netlist_set(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", impl_timing_netlist=True)
		sc = artix.get_synth(design_name="top")
		assert sc.impl_timing_sdf_file is not None

	def test_synth_impl_timing_sdf_disabled_when_no_netlist(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top", impl_timing_netlist=False)
		sc = artix.get_synth(design_name="top")
		assert sc.impl_timing_sdf_file is None


# ===========================================================================
# 8. Source-file resolution: globs, stage tags, dirty edge cases
# ===========================================================================


class TestSourceFileResolution:
	def test_string_source_gets_all_stages(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		sources = artix.get_design("top").sources
		assert len(sources) == 1
		sf = sources[0]
		assert sf.used_in_synth
		assert sf.used_in_impl
		assert sf.used_in_sim
		assert sf.used_in_ooc

	def test_dict_source_with_specific_stages(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg(
			"top",
			sources=[{"files": [src], "used_in": ["synth", "impl"]}],
		)
		sf = artix.get_design("top").sources[0]
		assert sf.used_in_synth
		assert sf.used_in_impl
		assert not sf.used_in_sim
		assert not sf.used_in_ooc

	def test_dict_source_sim_only(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_design_cfg(
			"top",
			sources=[{"files": [src], "used_in": ["sim"]}],
		)
		sf = artix.get_design("top").sources[0]
		assert not sf.used_in_synth
		assert sf.used_in_sim

	def test_dict_source_missing_files_key_raises(self, artix, tmp_path):
		with pytest.raises(error.SourceSpecMissingKeyError):
			artix.add_design_cfg(
				"top",
				sources=[{"used_in": ["synth"]}],
			)

	def test_dict_source_missing_used_in_key_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		with pytest.raises(error.SourceSpecMissingKeyError):
			artix.add_design_cfg(
				"top",
				sources=[{"files": [src]}],
			)

	def test_dict_source_unknown_stage_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		with pytest.raises(error.SourceSpecUnknownStageError):
			artix.add_design_cfg(
				"top",
				sources=[{"files": [src], "used_in": ["synth", "unknown_stage"]}],
			)

	def test_glob_resolves_multiple_files(self, artix, tmp_path):
		rtl_dir = tmp_path / "srcs/rtl"
		rtl_dir.mkdir(parents=True)
		for name in ("a.sv", "b.sv", "c.sv"):
			(rtl_dir / name).touch()
		artix.add_design_cfg("top", sources=["srcs/rtl/*.sv"])
		sources = artix.get_design("top").sources
		assert len(sources) == 3

	def test_glob_with_no_matches_results_in_empty(self, artix, tmp_path):
		artix.add_design_cfg("top", sources=["srcs/nonexistent/**/*.sv"])
		sources = artix.get_design("top").sources
		assert sources == []

	def test_glob_recursive_double_star(self, artix, tmp_path):
		deep = tmp_path / "srcs/rtl/subdir"
		deep.mkdir(parents=True)
		(deep / "deep.sv").touch()
		(tmp_path / "srcs/rtl/shallow.sv").touch()
		artix.add_design_cfg("top", sources=["srcs/rtl/**/*.sv"])
		sources = artix.get_design("top").sources
		assert len(sources) == 2

	def test_sourcefile_from_stages_helper(self):
		sf = SourceFile.from_stages("/some/file.sv", {"synth", "ooc"})
		assert sf.used_in_synth
		assert sf.used_in_ooc
		assert not sf.used_in_sim
		assert not sf.used_in_impl

	def test_sourcefile_used_in_properties_consistent(self):
		sf = SourceFile.from_stages("/f.sv", frozenset(["synth", "impl", "sim", "ooc"]))
		assert sf.used_in_synth
		assert sf.used_in_impl
		assert sf.used_in_sim
		assert sf.used_in_ooc


# ===========================================================================
# 9. Duplicate / missing entity error coverage
# ===========================================================================


class TestDuplicateAndMissingErrors:
	def test_duplicate_fpga_raises(self, artix):
		with pytest.raises(error.FpgaAlreadyExistsError):
			artix.add_fpga_cfg("main", fpga_part="xc7a35t-1cpg236c")

	def test_duplicate_ip_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		with pytest.raises(error.IpAlreadyExistsError):
			artix.add_ip_cfg("gamma_axi", sources=[src])

	def test_duplicate_wrapper_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		wsrc = _touch(tmp_path / "w.sv")
		artix.add_wrapper_cfg(ip="gamma_axi", sources=[wsrc])
		with pytest.raises(error.WrapperAlreadyExistsError):
			artix.add_wrapper_cfg(ip="gamma_axi", sources=[wsrc])

	def test_duplicate_bd_raises(self, artix):
		artix.add_bd_cfg("system")
		with pytest.raises(error.BdAlreadyExistsError):
			artix.add_bd_cfg("system")

	def test_duplicate_design_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		with pytest.raises(error.DesignAlreadyExistsError):
			artix.add_design_cfg("top", sources=[src])

	def test_duplicate_core_raises(self, artix):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		with pytest.raises(error.CoreAlreadyExistsError):
			artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")

	def test_duplicate_synth_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_synth_cfg(design="top")
		with pytest.raises(error.SynthAlreadyExistsError):
			artix.add_synth_cfg(design="top")

	def test_duplicate_sim_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src])
		with pytest.raises(error.SimAlreadyExistsError):
			artix.add_sim_cfg("tb", sources=[src])

	def test_duplicate_platform_raises(self, artix, tmp_path):
		artix.add_bd_cfg("system")
		artix.add_synth_cfg(bd="system")
		artix.add_platform_cfg("mb", bd="system")
		with pytest.raises(error.PlatformAlreadyExistsError):
			artix.add_platform_cfg("mb", bd="system")

	def test_duplicate_app_raises(self, artix, tmp_path):
		artix.add_bd_cfg("system")
		artix.add_synth_cfg(bd="system")
		artix.add_platform_cfg("mb", bd="system")
		artix.add_app_cfg("fw", platform="mb")
		with pytest.raises(error.AppAlreadyExistsError):
			artix.add_app_cfg("fw", platform="mb")

	def test_duplicate_formal_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "a.sv")
		artix.add_formal_cfg("p", top="m", mode="bmc", sources=[src])
		with pytest.raises(error.FormalAlreadyExistsError):
			artix.add_formal_cfg("p", top="m", mode="bmc", sources=[src])

	def test_duplicate_vivado_raises(self, zynq, tmp_path):
		with pytest.raises(error.VivadoAlreadySpecifiedError):
			zynq.add_vivado_cfg()

	def test_duplicate_vitis_raises(self, zynq, tmp_path):
		with pytest.raises(error.VitisAlreadySpecifiedError):
			zynq.add_vitis_cfg()

	def test_get_missing_design_raises(self, artix):
		with pytest.raises(error.DesignDoesNotExistError):
			artix.get_design("ghost")

	def test_get_missing_ip_raises(self, artix):
		with pytest.raises(error.IpDoesNotExistError):
			artix.get_ip("ghost")

	def test_get_missing_wrapper_raises(self, artix):
		with pytest.raises(error.WrapperDoesNotExistError):
			artix.get_wrapper("ghost")

	def test_get_missing_bd_raises(self, artix):
		with pytest.raises(error.BdDoesNotExistError):
			artix.get_bd("ghost")

	def test_get_missing_core_raises(self, artix):
		with pytest.raises(error.CoreDoesNotExistError):
			artix.get_core("ghost")

	def test_get_missing_synth_raises(self, artix, tmp_path):
		with pytest.raises(error.SynthDoesNotExistError):
			artix.get_synth(design_name="ghost")

	def test_get_missing_sim_raises(self, artix):
		with pytest.raises(error.SimDoesNotExistError):
			artix.get_sim("ghost")

	def test_get_missing_platform_raises(self, artix):
		with pytest.raises(error.PlatformDoesNotExistError):
			artix.get_platform("ghost")

	def test_get_missing_app_raises(self, artix):
		with pytest.raises(error.AppDoesNotExistError):
			artix.get_app("ghost")

	def test_get_missing_formal_raises(self, artix):
		with pytest.raises(error.FormalDoesNotExistError):
			artix.get_formal("ghost")

	def test_get_missing_fpga_raises(self, artix):
		with pytest.raises(error.FpgaDoesNotExistError):
			artix.get_fpga("ghost")

	def test_get_missing_uvm_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "tb.sv")
		artix.add_sim_cfg("tb", sources=[src])
		with pytest.raises(error.UvmDoesNotExistError):
			artix.get_uvm("ghost_test", "tb")

	def test_get_vivado_uninitialized_raises(self, bare):
		with pytest.raises(error.UninitializedVivadoError):
			bare.get_vivado()

	def test_get_vitis_uninitialized_raises(self, bare):
		with pytest.raises(error.UninitializedVitisError):
			bare.get_vitis()

	def test_get_catalog_uninitialized_raises(self, bare):
		with pytest.raises(error.UninitializedCoreCatalogError):
			bare.get_catalog()

	def test_synth_identifier_unspecified_raises(self, artix):
		with pytest.raises(error.SynthIdentifierUnspecifiedError):
			artix.get_synth()

	def test_synth_identifier_multiple_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_bd_cfg("system")
		with pytest.raises(error.SynthIdentifierMultipleError):
			artix.get_synth(design_name="top", bd_name="system")

	def test_platform_identifier_unspecified_raises(self, artix):
		with pytest.raises(error.PlatformIdentifierUnspecifiedError):
			artix.add_platform_cfg("mb")

	def test_platform_identifier_multiple_raises(self, artix, tmp_path):
		artix.add_bd_cfg("system")
		artix.add_synth_cfg(bd="system")
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("design_a", sources=[src])
		artix.add_synth_cfg(design="design_a")
		# can't simultaneously provide both bd AND design
		with pytest.raises(error.PlatformIdentifierMultipleError):
			artix.add_platform_cfg("mb", bd="system", design="design_a")

	def test_core_identifier_unspecified_raises(self, artix):
		with pytest.raises(error.CoreIdentifierUnspecifiedError):
			artix.add_core_cfg("clk_wiz_0")

	def test_core_identifier_multiple_raises(self, artix, tmp_path):
		src = _touch(tmp_path / "gamma_axi.sv")
		artix.add_ip_cfg("gamma_axi", sources=[src])
		with pytest.raises(error.CoreIdentifierMultipleError):
			artix.add_core_cfg("clk_wiz_0", ip="gamma_axi", vlnv="xilinx.com:ip:clk_wiz:6.0")

	def test_subcore_identifier_unspecified_raises(self, artix):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		with pytest.raises(error.SubCoreIdentifierUnspecifiedError):
			artix.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/top/clk_wiz_0")

	def test_subcore_identifier_multiple_raises(self, artix, tmp_path):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_bd_cfg("system")
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		with pytest.raises(error.SubCoreIdentifierMultipleError):
			artix.add_subcore_cfg(
				core="clk_wiz_0",
				inst_hier_path="/top/clk_wiz_0",
				bd="system",
				design="top",
			)

	def test_subcore_duplicate_bd_raises(self, artix):
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_bd_cfg("system")
		artix.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/system/clk_wiz_0", bd="system")
		with pytest.raises(error.SubCoreBdAlreadyExistsError):
			artix.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/system/clk_wiz_0", bd="system")

	def test_formal_no_targets_raises(self, artix, tmp_path):
		from xviv.functions.formal import cmd_formal

		with pytest.raises(error.FormalNoTargetsError):
			cmd_formal(artix, target=None)


# ===========================================================================
# 10. Parallel-job error aggregation
# ===========================================================================


class TestParallelJobs:
	def test_all_succeed_no_exception(self):
		results = []
		jobs = [(lambda i=i: results.append(i), f"job_{i}") for i in range(5)]
		run_parallel(jobs, max_workers=4)
		assert sorted(results) == list(range(5))

	def test_single_failure_raises_parallel_job_error(self):
		def bad():
			raise ValueError("boom")

		with pytest.raises(error.ParallelJobError) as exc_info:
			run_parallel([(bad, "bad_job")], max_workers=1)
		err = exc_info.value
		assert len(err.failures) == 1
		assert err.failures[0][0] == "bad_job"
		assert isinstance(err.failures[0][1], ValueError)

	def test_multiple_failures_all_reported(self):
		def fail(msg):
			raise RuntimeError(msg)

		jobs = [(lambda m=m: fail(m), f"job_{m}") for m in ["a", "b", "c"]]
		with pytest.raises(error.ParallelJobError) as exc_info:
			run_parallel(jobs, max_workers=3)
		assert len(exc_info.value.failures) == 3

	def test_partial_failure_raises_with_mixed_results(self):
		results = []

		def ok():
			results.append("ok")

		def bad():
			raise RuntimeError("bad")

		with pytest.raises(error.ParallelJobError):
			run_parallel([(ok, "ok_job"), (bad, "bad_job"), (ok, "ok2_job")], max_workers=3)
		# good jobs still ran
		assert results.count("ok") == 2

	def test_empty_job_list_is_no_op(self):
		run_parallel([])  # must not raise

	def test_parallel_job_error_message_contains_label(self):
		def bad():
			raise ValueError("exploded")

		with pytest.raises(error.ParallelJobError) as exc_info:
			run_parallel([(bad, "critical_task")], max_workers=1)
		assert "critical_task" in str(exc_info.value)
		assert "ValueError" in str(exc_info.value)

	def test_parallel_actually_concurrent(self):
		"""Jobs must execute concurrently, not sequentially."""
		times = []

		def slow():
			times.append(time.monotonic())
			time.sleep(0.05)
			times.append(time.monotonic())

		jobs = [(slow, f"s{i}") for i in range(4)]
		t0 = time.monotonic()
		run_parallel(jobs, max_workers=4)
		elapsed = time.monotonic() - t0
		# 4 sequential 50ms jobs would take ~200ms; concurrent should be <150ms
		assert elapsed < 0.15


# ===========================================================================
# 11. Filesystem helpers
# ===========================================================================


class TestFilesystemHelpers:
	def test_resolve_globs_plain_path_absolute(self, tmp_path):
		f = _touch(tmp_path / "top.sv")
		result = resolve_globs([str(tmp_path / "top.sv")], str(tmp_path))
		assert f in result

	def test_resolve_globs_with_wildcard(self, tmp_path):
		for n in ("a.sv", "b.sv", "c.sv"):
			_touch(tmp_path / n)
		result = resolve_globs(["*.sv"], str(tmp_path))
		assert len(result) == 3

	def test_resolve_globs_no_match_returns_empty(self, tmp_path):
		result = resolve_globs(["nope/**/*.sv"], str(tmp_path))
		assert result == []

	def test_resolve_globs_recursive(self, tmp_path):
		deep = tmp_path / "a" / "b"
		deep.mkdir(parents=True)
		(deep / "deep.sv").touch()
		(tmp_path / "shallow.sv").touch()
		result = resolve_globs(["**/*.sv"], str(tmp_path))
		assert len(result) == 2

	def test_is_stale_when_dst_does_not_exist(self, tmp_path):
		src = _touch(tmp_path / "src.sv")
		result = is_stale(src, str(tmp_path / "nonexistent.out"))
		assert result is True

	def test_is_stale_when_src_is_newer(self, tmp_path):
		src = tmp_path / "src.sv"
		dst = tmp_path / "dst.out"
		dst.touch()
		time.sleep(0.01)
		src.touch()
		assert is_stale(str(src), str(dst)) is True

	def test_is_stale_when_dst_is_newer(self, tmp_path):
		src = tmp_path / "src.sv"
		dst = tmp_path / "dst.out"
		src.touch()
		time.sleep(0.01)
		dst.touch()
		assert is_stale(str(src), str(dst)) is False

	def test_assert_file_exists_passes(self, tmp_path):
		f = _touch(tmp_path / "real.sv")
		assert_file_exists(f)  # must not raise

	def test_assert_file_exists_raises(self, tmp_path):
		with pytest.raises(error.FileNotFoundError):
			assert_file_exists(str(tmp_path / "ghost.sv"))


# ===========================================================================
# 12. Git SHA helpers (mocked subprocess)
# ===========================================================================


class TestGitShaHelper:
	@patch("subprocess.check_output")
	def test_clean_repo_returns_sha_not_dirty(self, mock_cmd):
		mock_cmd.side_effect = [b"abc1234\n", b""]  # sha, then clean status
		sha, dirty, tag = _git_sha_tag()
		assert sha == "abc1234"
		assert dirty is False
		assert tag == "abc1234"

	@patch("subprocess.check_output")
	def test_dirty_repo_sets_dirty_flag(self, mock_cmd):
		mock_cmd.side_effect = [b"abc1234\n", b" M srcs/rtl/top.sv\n"]
		sha, dirty, tag = _git_sha_tag()
		assert dirty is True
		assert "_dirty" in tag

	@patch("subprocess.check_output")
	def test_git_not_in_repo_returns_empty(self, mock_cmd):
		mock_cmd.side_effect = subprocess.CalledProcessError(128, "git")
		sha, dirty, tag = _git_sha_tag()
		assert sha == ""
		assert dirty is False

	@patch("subprocess.check_output")
	def test_status_failure_treats_as_clean(self, mock_cmd):
		"""SHA succeeds but git status raises – should not crash, treat as clean."""
		mock_cmd.side_effect = [b"abc1234\n", subprocess.CalledProcessError(1, "git")]
		sha, dirty, tag = _git_sha_tag()
		assert sha == "abc1234"
		assert dirty is False

	@patch("subprocess.check_output")
	def test_sha_stripped_of_whitespace(self, mock_cmd):
		mock_cmd.side_effect = [b"  deadbef  \n", b""]
		sha, _, _ = _git_sha_tag()
		assert sha == "deadbef"


# ===========================================================================
# 13. _resolve_val helper
# ===========================================================================


class TestResolveVal:
	def test_true_returns_default(self):
		assert _resolve_val(True, "/default/path.dcp") == "/default/path.dcp"

	def test_false_returns_none(self):
		assert _resolve_val(False, "/default/path.dcp") is None

	def test_none_returns_none(self):
		assert _resolve_val(None, "/default/path.dcp") is None

	def test_string_returns_string(self):
		assert _resolve_val("/custom/path.dcp", "/default/path.dcp") == "/custom/path.dcp"

	def test_empty_string_returns_empty_string(self):
		assert _resolve_val("", "/default/path.dcp") == ""


# ===========================================================================
# 14. TOML config loader (integration)
# ===========================================================================


class TestTomlLoader:
	def test_minimal_toml_loads(self, tmp_path):
		from xviv.config.loader import load_config

		toml_text = textwrap.dedent("""\
			[project]
			build_dir = "build"

			[[fpga]]
			name = "main"
			fpga_part = "xc7a200tfbg484-1"
		""")
		p = tmp_path / "project.toml"
		p.write_text(toml_text)

		with (
			patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
			patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		):
			cfg = load_config(str(p))

		assert cfg.get_fpga("main").fpga_part == "xc7a200tfbg484-1"

	def test_toml_with_design_and_synth(self, tmp_path):
		from xviv.config.loader import load_config

		src = _touch(tmp_path / "srcs/rtl/top.sv")
		xdc = _touch(tmp_path / "constraints/top.xdc")

		toml_text = textwrap.dedent(f"""\
			[project]
			build_dir = "build"

			[[fpga]]
			name = "main"
			fpga_part = "xc7a200tfbg484-1"

			[[design]]
			name = "top"
			sources = ["{src}"]

			[[synth]]
			design = "top"
			constraints = ["{xdc}"]
		""")
		p = tmp_path / "project.toml"
		p.write_text(toml_text)

		with (
			patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
			patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		):
			cfg = load_config(str(p))

		assert cfg.get_design("top") is not None
		assert cfg.get_synth(design_name="top") is not None

	def test_toml_unknown_key_raises(self, tmp_path):
		from xviv.config.loader import load_config

		toml_text = textwrap.dedent("""\
			[project]
			build_dir = "build"

			[[fpga]]
			name = "main"
			fpga_part = "xc7a200tfbg484-1"

			[[garbage]]
			name = "bad"
		""")
		p = tmp_path / "project.toml"
		p.write_text(toml_text)

		with (
			patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
			patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		):
			with pytest.raises(error.ProjectConfigUnknownKeyError):
				load_config(str(p))

	def test_toml_missing_file_raises(self, tmp_path):
		from xviv.config.loader import resolve_config

		with pytest.raises(error.ProjectConfigTomlFileMissingError):
			with patch("os.path.exists", return_value=False):
				resolve_config("")  # no project.toml in CWD (or we pass nonexistent path)

	def test_toml_formal_section_loads(self, tmp_path):
		from xviv.config.loader import load_config

		src = _touch(tmp_path / "gamma_axi.sv")

		toml_text = textwrap.dedent(f"""\
			[project]
			build_dir = "build"

			[[fpga]]
			name = "main"
			fpga_part = "xc7a200tfbg484-1"

			[[formal]]
			name = "gamma_props"
			top = "gamma_axi"
			mode = "prove"
			sources = ["{src}"]
			depth = 30
		""")
		p = tmp_path / "project.toml"
		p.write_text(toml_text)

		with (
			patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
			patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		):
			cfg = load_config(str(p))

		fcfg = cfg.get_formal("gamma_props")
		assert fcfg.depth == 30
		assert fcfg.mode == "prove"

	def test_toml_simulation_with_uvm_inline(self, tmp_path):
		from xviv.config.loader import load_config

		src = _touch(tmp_path / "tb_gamma.sv")

		toml_text = textwrap.dedent(f"""\
			[project]
			build_dir = "build"

			[[fpga]]
			name = "main"
			fpga_part = "xc7a200tfbg484-1"

			[[simulation]]
			name = "tb_gamma"
			sources = ["{src}"]

			[[simulation.uvm]]
			test = "gamma_basic_test"
			verbosity = "UVM_HIGH"
		""")
		p = tmp_path / "project.toml"
		p.write_text(toml_text)

		with (
			patch("xviv.config.loader.find_vivado_dir_path", return_value=None),
			patch("xviv.config.loader.find_vitis_dir_path", return_value=None),
		):
			cfg = load_config(str(p))

		uvm = cfg.get_uvm("gamma_basic_test", "tb_gamma")
		assert uvm.verbosity == "UVM_HIGH"


# ===========================================================================
# 15. SubCore list queries
# ===========================================================================


class TestSubCoreListQueries:
	def test_get_subcore_list_by_bd(self, artix):
		artix.add_bd_cfg("system")
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_core_cfg("axi_gpio_0", vlnv="xilinx.com:ip:axi_gpio:2.0")
		artix.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/system/clk_wiz_0", bd="system")
		artix.add_subcore_cfg(core="axi_gpio_0", inst_hier_path="/system/axi_gpio_0", bd="system")
		result = artix.get_subcore_list(bd_name="system")
		assert len(result) == 2
		cores = {sc.core for sc in result}
		assert "clk_wiz_0" in cores
		assert "axi_gpio_0" in cores

	def test_get_subcore_list_by_design(self, artix, tmp_path):
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		artix.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		artix.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/top/clk_wiz_0", design="top")
		result = artix.get_subcore_list(design_name="top")
		assert len(result) == 1
		assert result[0].core == "clk_wiz_0"

	def test_get_subcore_list_unspecified_raises(self, artix):
		with pytest.raises(error.SubCoreListIdentifierUnspecifiedError):
			artix.get_subcore_list()

	def test_get_subcore_list_multiple_raises(self, artix, tmp_path):
		artix.add_bd_cfg("system")
		src = _touch(tmp_path / "top.sv")
		artix.add_design_cfg("top", sources=[src])
		with pytest.raises(error.SubCoreListIdentifierMultipleError):
			artix.get_subcore_list(bd_name="system", design_name="top")

	def test_get_subcore_list_empty_when_none_registered(self, artix):
		artix.add_bd_cfg("system")
		result = artix.get_subcore_list(bd_name="system")
		assert result == []


# ===========================================================================
# 16. Error message sanity checks (human-readable strings)
# ===========================================================================


class TestErrorMessages:
	"""Guard that __str__ on all custom errors produces something useful."""

	def test_uninitialized_vivado_message(self):
		e = error.UninitializedVivadoError()
		assert "vivado" in str(e).lower() or "VivadoConfig" in str(e)

	def test_uninitialized_vitis_message(self):
		e = error.UninitializedVitisError()
		assert "vitis" in str(e).lower() or "VitisConfig" in str(e)

	def test_invalid_path_includes_path(self):
		e = error.InvalidPathError("/some/bad/path", "Vivado")
		assert "/some/bad/path" in str(e)
		assert "Vivado" in str(e)

	def test_vlnv_resolve_error_includes_vlnv(self):
		e = error.VlnvResolveError("xilinx.com:ip:missing:1.0")
		assert "xilinx.com:ip:missing:1.0" in str(e)

	def test_fpga_ref_mismatch_error(self):
		e = error.FpgaRefMismatchError("BD", "system", "main", "aux")
		s = str(e)
		assert "main" in s or "aux" in s

	def test_synth_does_not_exist_error(self):
		e = error.SynthDoesNotExistError(design="top", core=None, bd=None)
		assert "top" in str(e)

	def test_parallel_job_error_message(self):
		e = error.ParallelJobError([("job_a", RuntimeError("kaboom"))])
		s = str(e)
		assert "job_a" in s
		assert "kaboom" in s

	def test_synth_identifier_multiple_error_message(self):
		e = error.SynthIdentifierMultipleError(design="top", core=None, bd="system")
		s = str(e)
		assert "top" in s
		assert "system" in s

	def test_formal_invalid_mode_message(self):
		e = error.FormalInvalidModeError("gamma_props", "fuzz")
		s = str(e)
		assert "fuzz" in s
		assert "gamma_props" in s

	def test_source_spec_unknown_stage_message(self):
		e = error.SourceSpecUnknownStageError({"bananas"}, {"files": ["f.sv"], "used_in": ["bananas"]})
		s = str(e)
		assert "bananas" in s

	def test_wrapper_ip_missing_message(self):
		e = error.WrapperIpMissing("gamma_axi")
		assert "gamma_axi" in str(e)

	def test_uvm_does_not_exist_error(self):
		e = error.UvmDoesNotExistError("my_test", "tb_gamma")
		s = str(e)
		assert "my_test" in s or "tb_gamma" in s


# ===========================================================================
# 17. Vivado / Vitis path propagation
# ===========================================================================


class TestVivadoVitisConfig:
	def test_vivado_bin_path_built_from_dir(self, bare, tmp_path):
		vdir = tmp_path / "vivado"
		vdir.mkdir()
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(str(vdir))
		vc = bare.get_vivado()
		assert str(vdir) in vc.vivado_bin

	def test_vivado_xsim_bin_path_built_from_dir(self, bare, tmp_path):
		vdir = tmp_path / "vivado"
		vdir.mkdir()
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(str(vdir))
		vc = bare.get_vivado()
		assert str(vdir) in vc.xsim_bin

	def test_vivado_glbl_path_set(self, bare, tmp_path):
		vdir = tmp_path / "vivado"
		vdir.mkdir()
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(str(vdir))
		vc = bare.get_vivado()
		assert "glbl.v" in vc.glbl_file

	def test_vivado_mode_default_is_batch(self, bare, tmp_path):
		vdir = tmp_path / "vivado"
		vdir.mkdir()
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(str(vdir))
		assert bare.get_vivado().mode == "batch"

	def test_vivado_none_path_no_bin_prefix(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(path=None)
		vc = bare.get_vivado()
		# without a path, bins remain as plain names
		assert vc.vivado_bin == "vivado"
		assert vc.xsim_bin == "xsim"

	def test_vitis_xsct_bin_path_built_from_dir(self, bare, tmp_path):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		vdir = tmp_path / "vivado"
		vdir.mkdir()
		bare.add_vivado_cfg(str(vdir))
		vtdir = tmp_path / "vitis"
		vtdir.mkdir()
		bare.add_vitis_cfg(str(vtdir))
		vt = bare.get_vitis()
		assert str(vtdir) in vt.xsct_bin

	def test_vitis_none_path_no_bin_prefix(self, bare):
		bare.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")
		bare.add_vivado_cfg(path=None)
		bare.add_vitis_cfg(path=None)
		vt = bare.get_vitis()
		assert vt.xsct_bin == "xsct"


# ===========================================================================
# 18. Full project config path helpers (directory properties)
# ===========================================================================


class TestDirectoryProperties:
	def test_synth_dir_under_work_dir(self, artix, tmp_path):
		assert artix.synth_dir.startswith(str(tmp_path / "build"))
		assert "synth" in artix.synth_dir

	def test_core_dir_under_work_dir(self, artix, tmp_path):
		assert artix.core_dir.startswith(str(tmp_path / "build"))

	def test_bd_dir_under_work_dir(self, artix, tmp_path):
		assert artix.bd_dir.startswith(str(tmp_path / "build"))

	def test_scripts_dir_under_base_dir(self, artix, tmp_path):
		assert artix.scripts_dir.startswith(str(tmp_path))
		assert "scripts" in artix.scripts_dir

	def test_formal_dir_under_work_dir(self, artix, tmp_path):
		assert artix.formal_dir.startswith(str(tmp_path / "build"))

	def test_wrapper_dir_under_work_dir(self, artix, tmp_path):
		assert artix.wrapper_dir.startswith(str(tmp_path / "build"))

	def test_ip_repo_default_under_build(self, artix, tmp_path):
		assert artix._get_ip_repo_default.startswith(str(tmp_path / "build"))


# ===========================================================================
# 19. FormalResult repr
# ===========================================================================


class TestFormalResult:
	def test_repr_pass(self):
		r = FormalResult("gamma_props", passed=True, last_line="PASS", vcd=None)
		assert "PASS" in repr(r)
		assert "gamma_props" in repr(r)

	def test_repr_fail(self):
		r = FormalResult("gamma_props", passed=False, last_line="FAIL", vcd="/some.vcd")
		assert "FAIL" in repr(r)

	def test_vcd_accessible(self):
		r = FormalResult("p", passed=False, last_line="FAIL", vcd="/trace.vcd")
		assert r.vcd == "/trace.vcd"


# ===========================================================================
# 20. Elaborate real-world scenario: full AXI DMA + MicroBlaze project
# ===========================================================================


class TestFullAXIDMAProject:
	"""
	A more realistic project that assembles multiple subsystems:

	- Custom AXI DMA IP  (gamma_axi)
	- Clock wizard core  (clk_wiz_0)
	- Block design       (system)
	- RTL design         (dma_wrapper) that references the BD
	- Synthesis run      (system BD synth)
	- Formal proof       (dma_props)
	- Two simulations:   functional xsim, timing verilator
	- UVM test suite
	- Platform + App     (mb_platform / firmware)
	"""

	def _build_project(self, tmp_path) -> XvivConfig:
		cfg = _project(tmp_path)
		cfg.add_fpga_cfg("main", fpga_part="xc7a200tfbg484-1")

		# -- Custom IP ---------------------------------------------------
		ip_src = _touch(tmp_path / "srcs/ip/gamma_axi/gamma_axi.sv")
		cfg.add_ip_cfg("gamma_axi", sources=[ip_src])

		# -- Catalog IP (clock wizard) -----------------------------------
		cfg.add_core_cfg("clk_wiz_0", vlnv="xilinx.com:ip:clk_wiz:6.0")
		cfg.add_synth_cfg(core="clk_wiz_0")  # OOC synth

		# -- Block design ------------------------------------------------
		cfg.add_bd_cfg("system")
		cfg.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/system/clk_wiz_0", bd="system")
		xdc = _touch(tmp_path / "constraints/system.xdc")
		cfg.add_synth_cfg(bd="system", constraints=[xdc])

		# -- Platform + embedded app -------------------------------------
		cfg.add_platform_cfg("mb_platform", bd="system", cpu="microblaze_0")
		fw_src = _touch(tmp_path / "srcs/sw/main.c")
		cfg.add_app_cfg("firmware", platform="mb_platform", sources=[fw_src])

		# -- Functional simulation (xsim) --------------------------------
		tb_src = _touch(tmp_path / "srcs/sim/tb_gamma.sv")
		cfg.add_sim_cfg(
			"tb_gamma",
			sources=[tb_src, ip_src],
			backend="xsim",
			timescale="1ns/1ps",
			defines=["SIM_FUNCTIONAL"],
		)
		cfg.add_uvm_cfg(test="gamma_basic_test", simulation="tb_gamma", verbosity="UVM_HIGH")
		cfg.add_uvm_cfg(test="gamma_stress_test", simulation="tb_gamma", verbosity="UVM_MEDIUM")

		# -- Formal verification -----------------------------------------
		props_src = _touch(tmp_path / "srcs/formal/gamma_props.sv")
		cfg.add_formal_cfg(
			"gamma_props",
			top="gamma_axi",
			mode="prove",
			sources=[ip_src, props_src],
			depth=40,
		)

		return cfg

	def test_project_assembles_without_error(self, tmp_path):
		cfg = self._build_project(tmp_path)
		assert cfg is not None

	def test_bd_subcore_registered(self, tmp_path):
		cfg = self._build_project(tmp_path)
		subcores = cfg.get_subcore_list(bd_name="system")
		assert any(sc.core == "clk_wiz_0" for sc in subcores)

	def test_core_synth_is_ooc(self, tmp_path):
		cfg = self._build_project(tmp_path)
		sc = cfg.get_synth(core_name="clk_wiz_0")
		assert sc.synth_mode == "out_of_context"
		assert sc.bitstream_file is None

	def test_bd_synth_has_bitstream(self, tmp_path):
		cfg = self._build_project(tmp_path)
		sc = cfg.get_synth(bd_name="system")
		assert sc.bitstream_file is not None

	def test_platform_xsa_links_to_bd_synth(self, tmp_path):
		cfg = self._build_project(tmp_path)
		pf = cfg.get_platform("mb_platform")
		sc = cfg.get_synth(bd_name="system")
		assert pf.xsa_file == sc.hw_platform_xsa_file

	def test_two_uvm_tests_registered(self, tmp_path):
		cfg = self._build_project(tmp_path)
		basic = cfg.get_uvm("gamma_basic_test", "tb_gamma")
		stress = cfg.get_uvm("gamma_stress_test", "tb_gamma")
		assert basic.verbosity == "UVM_HIGH"
		assert stress.verbosity == "UVM_MEDIUM"

	def test_sim_defines_stored(self, tmp_path):
		cfg = self._build_project(tmp_path)
		sim = cfg.get_sim("tb_gamma")
		assert "SIM_FUNCTIONAL" in sim.defines

	def test_formal_depth_stored(self, tmp_path):
		cfg = self._build_project(tmp_path)
		fcfg = cfg.get_formal("gamma_props")
		assert fcfg.depth == 40

	def test_app_elf_path_set(self, tmp_path):
		cfg = self._build_project(tmp_path)
		app = cfg.get_app("firmware")
		assert app.elf_file.endswith(".elf")

	def test_ip_vlnv_correct(self, tmp_path):
		cfg = self._build_project(tmp_path)
		ip = cfg.get_ip("gamma_axi")
		assert ip.vlnv.startswith("xviv.org:xviv:gamma_axi")

	def test_sby_generation_for_formal(self, tmp_path):
		cfg = self._build_project(tmp_path)
		fcfg = cfg.get_formal("gamma_props")
		sby = generate_sby(fcfg)
		assert "mode prove" in sby
		assert "depth 40" in sby
		assert "hierarchy -check -top gamma_axi" in sby

	def test_get_formal_list_has_one_entry(self, tmp_path):
		cfg = self._build_project(tmp_path)
		assert len(cfg.get_formal_list()) == 1

	def test_ip_repo_present_in_list(self, tmp_path):
		cfg = self._build_project(tmp_path)
		# default IP repo should be registered (even if dir doesn't exist yet)
		assert cfg._get_ip_repo_default is not None
