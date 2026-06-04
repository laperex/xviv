import tempfile
import typing
from pathlib import Path

from xviv.tools.vivado import XilinxToolRunner
from xviv.utils.job import Job


class XsctRunner(XilinxToolRunner):
	_DEFAULT_WORKERS: int = 4

	def job(
		self,
		tcl: str | None,
		*,
		label: str,
		log_file: str,
		popen: bool = False,
	) -> typing.Self:
		if tcl is None:
			return None

		tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_sim_config.tcl", delete=False, prefix="xviv_")
		tmp.write(tcl)
		tmp.close()
		tcl_path = Path(tmp.name)

		cmd: list[str] = [self._cfg.get_vitis().xsct_bin, str(tcl_path)]

		self._pairs.append(
			(
				tcl_path,
				Job(
					label=label,
					cmd=tuple(cmd),
					cwd=self._cfg.work_dir,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=popen,
					env=None,
				),
			)
		)

		return self
