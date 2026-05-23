import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_tool(
	cmd: list[str],
	*,
	cwd: str,
	dry_run: bool = False,
	log: logging.Logger | None = None,
	log_path: Path | None = None,
	popen: bool = False,
	interactive: bool = False,
) -> int | None:
	job_log = log or logger
	job_log.info("Running: %s", " ".join(cmd))
	os.makedirs(cwd, exist_ok=True)

	if dry_run:
		return None

	log_file = None
	try:
		if log_path is not None:
			log_path.parent.mkdir(parents=True, exist_ok=True)
			log_file = log_path.open("w")
			job_log.info("Log: %s", log_path)

		if popen:
			return subprocess.Popen(cmd, cwd=cwd).pid

		if interactive:
			result = subprocess.run(cmd, cwd=cwd)
			if result.returncode != 0:
				raise subprocess.CalledProcessError(result.returncode, cmd)
			return None

		with subprocess.Popen(
			cmd,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1,
			cwd=cwd,
		) as proc:
			assert proc.stdout is not None
			for line in proc.stdout:
				stripped = line.rstrip()
				print(stripped)
				job_log.debug(stripped)
				if log_file:
					log_file.write(line)
					log_file.flush()
			proc.wait()

		if proc.returncode != 0:
			raise subprocess.CalledProcessError(proc.returncode, cmd)

	finally:
		if log_file:
			log_file.close()

	return None
