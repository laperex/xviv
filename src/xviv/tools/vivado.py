import logging
import os
import subprocess
import sys
import tempfile
import typing
from pathlib import Path

from xviv.config.project import XvivConfig

logger = logging.getLogger(__name__)


def run_vivado_xvlog(
	cfg: XvivConfig, target_dir: str, fileset: list[str], xsim_lib: str
) -> None:
	xvlog_bin = os.path.join(cfg.get_vivado().path, "bin", "xvlog")

	extra_files = [os.path.join(cfg.get_vivado().path, "data/verilog/src/glbl.v")]

	cmd = [xvlog_bin, "-sv", "-incr", "-work", xsim_lib, *fileset, *extra_files]
	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	try:
		subprocess.run(cmd, check=True, cwd=target_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)


def run_vivado_xelab(
	cfg: XvivConfig,
	target_dir: str,
	top: str,
	timescale: str,
	xsim_lib: str,
	run_all=False,
) -> None:
	xelab_bin = os.path.join(cfg.get_vivado().path, "bin", "xelab")

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
		cmd.append("-R")

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	try:
		subprocess.run(cmd, check=True, cwd=target_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)


def run_vivado_xsim(
	cfg: XvivConfig,
	target_dir: str,
	top: str,
	config_tcl_content: str,
) -> None:
	xsim_bin = os.path.join(cfg.get_vivado().path, "bin", "xsim")

	try:
		with tempfile.NamedTemporaryFile(
			mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_"
		) as tmp:
			tmp.write(config_tcl_content)
			config_tcl_path = tmp.name

		cmd = [
			xsim_bin,
			"--stats",
			top,
			"--wdb",
			os.path.join(target_dir, f"{top}.wdb"),
			"-t",
			config_tcl_path,
		]
		logger.info("Running: %s", " ".join(cmd))
		os.makedirs(target_dir, exist_ok=True)

		try:
			subprocess.run(cmd, check=True, cwd=target_dir)
		except subprocess.CalledProcessError as e:
			sys.exit(e.returncode)
	finally:
		os.unlink(config_tcl_path)


def run_vivado(
	cfg: XvivConfig,
	config_tcl: typing.Optional[str],
	extra_args: list[str] = [],
	label: typing.Optional[str] = None,
	log_dir: typing.Optional[str] = None,
	dry_run: bool = False 
) -> None:
	vivado_bin = os.path.join(cfg.get_vivado().path, "bin", "vivado")
	job_log = logger.getChild(label) if label else logger

	# with tempfile.NamedTemporaryFile(
	# 	mode="w", suffix="_config.tcl", delete=False, prefix="xviv_"
	# ) as tmp:
	# 	tmp.write(config_tcl)
	# 	config_tcl_path = tmp.name
	
	if config_tcl is None:
		return None

	config_tcl_path = os.path.join(cfg.work_dir, "xviv_config.tcl")
	
	with open(config_tcl_path, 'w') as f:
		f.write(config_tcl)

	if dry_run:
		return None

	try:
		cmd = [
			vivado_bin,
			"-mode", cfg.get_vivado().mode,
			"-nolog", "-nojournal", "-notrace", "-quiet",
			"-source", config_tcl_path,
			*extra_args,
		]
		job_log.info("Running: %s", " ".join(cmd))

		if cfg.get_vivado().mode == "tcl":
			# interactive — connect directly to terminal, no log capture
			result = subprocess.run(cmd)
			if result.returncode != 0:
				job_log.error("Vivado exited with code %d", result.returncode)
				raise subprocess.CalledProcessError(result.returncode, cmd)
			return

		log_path = Path(log_dir) / f"{label}.log" if log_dir else None
		if log_path:
			log_path.parent.mkdir(parents=True, exist_ok=True)
		log_file = log_path.open("w") if log_path else None

		try:
			with subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
			) as proc:
				assert proc.stdout
				for line in proc.stdout:
					stripped = line.rstrip()
					job_log.info(stripped)
					if log_file:
						log_file.write(line)
				proc.wait()
		finally:
			if log_file:
				log_file.close()

		if proc.returncode != 0:
			job_log.error("Vivado exited with code %d", proc.returncode)
			raise subprocess.CalledProcessError(proc.returncode, cmd)

	finally:
		os.unlink(config_tcl_path)
