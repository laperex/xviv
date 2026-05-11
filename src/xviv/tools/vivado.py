import contextlib
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

	if cfg.get_vivado().dry_run:
		return

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
	sdfmax_entries: list[str] = [],
) -> None:
	xelab_bin = os.path.join(cfg.get_vivado().path, "bin", "xelab")

	cmd = [
		xelab_bin,
		f"{xsim_lib}.{top}",
		f"{xsim_lib}.glbl",
		"-L", "unimacro_ver",
		"-L", "secureip",
		"-debug", "typical",
		"-mt", "20",
		"-s", top,
		"-timescale", timescale
	]

	for i in sdfmax_entries:
		cmd += ['-sdfmax', i]

	if sdfmax_entries:
		cmd.append(["-L", "simprims_ver"])
	else:
		cmd.append(["-L", "unifast_ver"])
		cmd.append(["-L", "unisims_ver"])

	if run_all:
		cmd.append("-R")

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	if cfg.get_vivado().dry_run:
		return

	try:
		subprocess.run(cmd, check=True, cwd=target_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)


def run_vivado_xsim(
	cfg: XvivConfig,
	target_dir: str,
	config_tcl: str | None,

	top: str | None = None,
	wdb_file: str | None = None,
	stats: bool = True,
	nogui: bool = False,
	popen = False
) -> int | None:
	xsim_bin = os.path.join(cfg.get_vivado().path, "bin", "xsim")

	if config_tcl is None:
		return

	pid = None

	with tempfile.NamedTemporaryFile(
		mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_"
	) as tmp:
		tmp.write(config_tcl)
		config_tcl_path = tmp.name

	cmd = list(filter(None, [
		xsim_bin,
		"--stats" if stats else None,
		top if top else None,
		wdb_file if wdb_file else None,
		"-t", config_tcl_path,
		"-g" if not nogui else None,
	]))

	logger.info("Running: %s", " ".join(cmd))
	os.makedirs(target_dir, exist_ok=True)

	if cfg.get_vivado().dry_run:
		return

	try:
		if popen:
			proc = subprocess.Popen(cmd, cwd=target_dir)

			pid = proc.pid
		else:
			subprocess.run(cmd, check=True, cwd=target_dir)
	except subprocess.CalledProcessError as e:
		sys.exit(e.returncode)

	return pid


def run_vivado(
	cfg: XvivConfig,
	config_tcl: str | None,
	extra_args: list[str] | None = None,
	label: str | None = None,
	log_dir: str | None = None,
) -> None:
	if config_tcl is None:
		return

	vivado = cfg.get_vivado()
	vivado_bin = os.path.join(vivado.path, "bin", "vivado")
	job_log = logger.getChild(label) if label else logger

	config_tcl_path: str | None = None
	log_file = None

	try:
		# Write TCL to a named temp file
		with tempfile.NamedTemporaryFile(
			mode="w", suffix="_config.tcl", delete=False, prefix=f"xviv_{label or ''}_"
		) as tmp:
			tmp.write(config_tcl)
			config_tcl_path = tmp.name

		if vivado.dry_run:
			job_log.info("[dry-run] TCL written to: %s", config_tcl_path)
			job_log.debug("[dry-run] TCL contents:\n%s", config_tcl)
			return

		cmd = [
			vivado_bin,
			"-mode", vivado.mode,
			"-nolog", "-nojournal", "-notrace", "-quiet",
			"-source", config_tcl_path,
			*(extra_args or []),
		]
		job_log.info("Running: %s", " ".join(cmd))

		# TCL interactive mode - attach directly to terminal
		if vivado.mode == "tcl":
			result = subprocess.run(cmd)
			if result.returncode != 0:
				raise subprocess.CalledProcessError(result.returncode, cmd)
			return

		# Batch mode - stream output and write per-job log
		log_stem = label or "vivado"
		log_path = Path(log_dir or cfg.work_dir) / f"{log_stem}.log"
		log_path.parent.mkdir(parents=True, exist_ok=True)
		log_file = log_path.open("w")

		job_log.info("Log: %s", log_path)

		with subprocess.Popen(
			cmd,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1,
		) as proc:
			if proc.stdout is None:
				raise RuntimeError("stdout pipe unexpectedly None")

			for line in proc.stdout:
				stripped = line.rstrip()
				job_log.info(stripped)
				log_file.write(line)
				log_file.flush()
			proc.wait()

		if proc.returncode != 0:
			job_log.error("Vivado exited with code %d (log: %s)", proc.returncode, log_path)
			raise subprocess.CalledProcessError(proc.returncode, cmd)

	finally:
		if log_file:
			log_file.close()
		if config_tcl_path and not vivado.dry_run:
			with contextlib.suppress(OSError):
				os.unlink(config_tcl_path)