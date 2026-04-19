import importlib.resources
import logging
import os
import subprocess
import tempfile

from xviv.config.model import ProjectConfig


logger = logging.getLogger(__name__)


def run_vivado_xvlog(cfg: ProjectConfig, target_dir: str, fileset: list[str], xsim_lib: str) -> None:
	xvlog_bin = os.path.join(cfg.vivado.path, "bin", "xvlog")

	fileset.append(os.path.join(cfg.vivado.path, "data/verilog/src/glbl.v"))

	cmd = [xvlog_bin, "-sv", "-incr", "-work", xsim_lib, *fileset]
	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)
	subprocess.run(cmd, check=True, cwd=target_dir)


def run_vivado_xelab(cfg: ProjectConfig, target_dir: str, top: str, timescale: str, xsim_lib: str, run_all=False) -> None:
	xelab_bin = os.path.join(cfg.vivado.path, "bin", "xelab")

	cmd = [
		xelab_bin,
		f"{xsim_lib}.{top}",
		f"{xsim_lib}.glbl",
		"-L", "unifast_ver",
		"-L", "unisims_ver",
		"-L", "unimacro_ver",
		"-L", "secureip",
		"-debug", "typical",
		"-mt", "20",
		"-s", top,
		"-timescale", timescale
	]

	if run_all:
		cmd.append('-R')

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)
	subprocess.run(cmd, check=True, cwd=target_dir)


def run_vivado_xsim(
		cfg: ProjectConfig,
		target_dir: str,
		top: str,
		config_tcl_content: str,
) -> None:
	xsim_bin = os.path.join(cfg.vivado.path, "bin", "xsim")

	try:
		with tempfile.NamedTemporaryFile(
				mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_"
		) as tmp:
			tmp.write(config_tcl_content)
			config_tcl_path = tmp.name

		cmd = [
			xsim_bin,
			"--stats", top,
			"--wdb", os.path.join(target_dir, f"{top}.wdb"),
			"-t", config_tcl_path,
		]
		logger.info("Running: %s", " ".join(cmd))
		os.makedirs(target_dir, exist_ok=True)
		subprocess.run(cmd, check=True, cwd=target_dir)
	finally:
		os.unlink(config_tcl_path)


def run_vivado(
		cfg: ProjectConfig,
		tcl_script: str,
		command: str,
		extra_args: list[str],
		config_tcl_content: str,
) -> None:
	vivado_bin = os.path.join(cfg.vivado.path, "bin", "vivado")

	with tempfile.NamedTemporaryFile(
			mode="w", suffix="_config.tcl", delete=False, prefix="xviv_"
	) as tmp:
		tmp.write(config_tcl_content)
		config_tcl_path = tmp.name

	try:
		cmd = [
			vivado_bin,
			"-mode",    cfg.vivado.mode,
			"-nolog", "-nojournal", "-notrace", "-quiet",
			"-source",  tcl_script,
			"-tclargs", command, config_tcl_path,
			*extra_args,
		]
		logger.info("Running: %s", " ".join(cmd))
		subprocess.run(cmd, check=True)
	finally:
		os.unlink(config_tcl_path)


def _find_tcl_script() -> str:
	ref = importlib.resources.files("xviv") / "scripts" / "dispatch" / "vivado.tcl"

	with importlib.resources.as_file(ref) as path:
		return str(path)

