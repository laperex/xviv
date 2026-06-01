# import contextlib
# import logging
# import os
# import tempfile

# from xviv.config.project import XvivConfig
# from xviv.utils.process import run_tool
# from xviv.utils.tools import find_vitis_dir_path

# logger = logging.getLogger(__name__)


# def run_xsct(cfg: XvivConfig, config_tcl: str, *, label: str) -> None:
# 	config_tcl_path: str | None = None
# 	try:
# 		with tempfile.NamedTemporaryFile(mode="w", suffix="_xsct_config.tcl", delete=False, prefix="xviv_") as tmp:
# 			tmp.write(config_tcl)
# 			config_tcl_path = tmp.name

# 		try:
# 			run_tool(
# 				[cfg.get_vitis().xsct_bin, config_tcl_path],
# 				cwd=os.getcwd(),
# 				label=f"{__name__}_{label}",
# 				log_dir=cfg.log_dir,
# 				dry_run=cfg.dry_run,
# 				exit_on_fail=True,
# 			)
# 		except FileNotFoundError:
# 			try:
# 				find_vitis_dir_path(exit_on_fail=True)
# 			finally:
# 				raise

# 	finally:
# 		if config_tcl_path and not cfg.dry_run:
# 			with contextlib.suppress(OSError):
# 				os.unlink(config_tcl_path)


# # def run_xsct_live(cfg: XvivConfig, config_tcl: str) -> None:
# # 	try:
# # 		run_tool([cfg.get_vitis().xsct_bin, config_tcl], label='run_xsct_live', cwd=os.getcwd(), dry_run=cfg.dry_run, exit_on_fail=True)
# # 	except KeyboardInterrupt:
# # 		logger.info("xsct-live stopped by user")
# # 	except FileNotFoundError:
# # 		try:
# # 			find_vitis_dir_path(exit_on_fail=True)
# # 		finally:
# # 			raise


import tempfile
from pathlib import Path

from xviv.tools.vivado import XilinxToolRunner
from xviv.utils.job import Job


class XsctRunner(XilinxToolRunner):
	_DEFAULT_WORKERS: int = 4

	def job(
		self,
		target_dir: str,
		*,
		label: str,
		log_file: str,
		config_tcl: str | None,
		popen: bool = False,
	) -> tuple[Path, Job] | None:
		# Build simulation job
		if config_tcl is None:
			return None

		tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_")
		tmp.write(config_tcl)
		tmp.close()
		tcl_path = Path(tmp.name)

		cmd: list[str] = [self._cfg.get_vitis().xsct_bin, str(tcl_path)]

		return tcl_path, Job(
			label=label,
			cmd=tuple(cmd),
			cwd=target_dir,
			log_file=log_file,
			classifier=self.classify,
			dry_run=self._cfg.dry_run,
			interactive=False,
			detach=popen,
			env=None,
		)
