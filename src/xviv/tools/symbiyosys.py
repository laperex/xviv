"""tools/symbiyosys.py — SymbiYosys runner for xviv.

Provides :class:`SbyRunner`, a :class:`~xviv.tools.vivado.ToolRunner` subclass
that queues and executes SymbiYosys (``sby``) formal-verification jobs through
the standard Job infrastructure.

Typical usage::

    from xviv.tools.symbiyosys import SbyRunner

    SbyRunner(cfg).verify_job(
        sby_file=sby_path,
        label=f"formal:{name}",
        log_file=log_path,
    ).run()
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import typing
from pathlib import Path

from xviv.tools.vivado import ToolRunner
from xviv.utils import error
from xviv.utils.job import Job
from xviv.utils.stream import OutputLine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns for sby output classification
# ---------------------------------------------------------------------------

# Optional "[HH:MM:SS] " timestamp present in most sby lines.
_TS = r"(?:\[\d{2}:\d{2}:\d{2}\]\s+)?"

# Final status line:   "SBY [HH:MM:SS] PASS"
_RE_FINAL_STATUS: re.Pattern[str] = re.compile(rf"^SBY\s+{_TS}(?P<status>PASS|FAIL|UNKNOWN|ERROR|TIMEOUT)\s*$")

# Per-engine status:   "SBY [HH:MM:SS] engine_0: FAIL"
# or with step prefix: "SBY [HH:MM:SS] engine_0 (step  5): PASS"
_RE_ENGINE_STATUS: re.Pattern[str] = re.compile(rf"^SBY\s+{_TS}engine_\d+(?:\s+\(step\s+\d+\))?:\s+(?P<status>PASS|FAIL|UNKNOWN|ERROR|TIMEOUT)\s*$")

# Cover-point reached: "SBY [...] engine_0: Reached cover statement at ..."
_RE_COVER_HIT: re.Pattern[str] = re.compile(rf"^SBY\s+{_TS}engine_\d+.*?Reached cover statement")

# Counterexample / trace file written:
#   "SBY [...] engine_0: Writing trace to VCD file: trace.vcd"
#   "SBY [...] engine_0: Writing trace to trace.vcd"
_RE_VCD_WRITTEN: re.Pattern[str] = re.compile(
	r"Writing (?:trace|counterexample) to (?:VCD )?file[:\s]+(.+\.vcd)",
	re.IGNORECASE,
)

# Generic SBY info:  "SBY [HH:MM:SS] <msg>"
_RE_SBY_ANY: re.Pattern[str] = re.compile(rf"^SBY\s+{_TS}.+$")

_STATUS_TO_LEVEL: dict[str, int] = {
	"PASS": logging.INFO,
	"FAIL": logging.ERROR,
	"UNKNOWN": logging.WARNING,
	"ERROR": logging.ERROR,
	"TIMEOUT": logging.WARNING,
}


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------


def find_sby_bin() -> str:
	"""Return the absolute path to the ``sby`` executable.

	Raises
	------
	:exc:`xviv.utils.error.FormalSbyNotFoundError`
	    When ``sby`` cannot be found on :envvar:`PATH`.
	"""
	path = shutil.which("sby")
	if path is None:
		raise error.FormalSbyNotFoundError()
	return path


def sby_version(sby_bin: str) -> tuple[int, int]:
	"""Probe ``sby_bin`` and return its ``(major, minor)`` version.

	Returns ``(0, 0)`` when the version string cannot be parsed.

	Parameters
	----------
	sby_bin:
	    Path (or bare name) of the SymbiYosys executable.
	"""
	try:
		out = subprocess.check_output(
			[sby_bin, "--version"],
			text=True,
			stderr=subprocess.STDOUT,
		)
		m = re.search(r"(\d+)\.(\d+)", out)
		if m:
			return int(m.group(1)), int(m.group(2))
	except Exception:
		pass
	return (0, 0)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SbyRunner(ToolRunner):
	"""ToolRunner that drives SymbiYosys (``sby``) jobs.

	Each call to :meth:`verify_job` enqueues one ``.sby`` invocation.
	:meth:`run` (inherited from :class:`ToolRunner`) executes them — in
	parallel when multiple jobs are queued and ``sequential_exec=False``.

	Example — single target::

	    SbyRunner(cfg)
	        .verify_job(sby_file=path, label="formal:counter", log_file=log)
	        .run()

	Example — parallel batch::

	    runner = SbyRunner(cfg)
	    for path, log in sby_jobs:
	        runner.verify_job(sby_file=path, label=path.stem, log_file=log)
	    runner.run(max_workers=4)
	"""

	# Allow up to 4 concurrent sby processes by default.
	_DEFAULT_WORKERS: int = 4

	def __init__(self, cfg) -> None:
		super().__init__(cfg)
		self.sby_bin: str = find_sby_bin()
		# Formal jobs are independent — run them in parallel.
		self.sequential_exec = False

	# ------------------------------------------------------------------
	# Output classifier
	# ------------------------------------------------------------------

	@classmethod
	def classify(cls, raw: str) -> OutputLine:
		"""Classify a raw ``sby`` output line into an :class:`OutputLine`.

		Classification rules (in priority order):

		1. Final ``PASS / FAIL / UNKNOWN / ERROR / TIMEOUT`` status lines
		   → logged at the corresponding level (INFO / ERROR / WARNING).
		2. Per-engine status lines (``engine_0: FAIL``) → same mapping.
		3. Cover-point hit lines → INFO.
		4. VCD-file-written lines → WARNING (surfaced to the user).
		5. Lines containing ``error:`` or ``warning:`` → ERROR / WARNING.
		6. Everything else → DEBUG.
		"""
		line = raw.rstrip()

		# 1. Final status
		m = _RE_FINAL_STATUS.match(line)
		if m:
			level = _STATUS_TO_LEVEL.get(m.group("status"), logging.INFO)
			return OutputLine(text=line, level=level, raw=raw)

		# 2. Per-engine status
		m = _RE_ENGINE_STATUS.match(line)
		if m:
			level = _STATUS_TO_LEVEL.get(m.group("status"), logging.DEBUG)
			return OutputLine(text=line, level=level, raw=raw)

		# 3. Cover-point reached
		if _RE_COVER_HIT.match(line):
			return OutputLine(text=line, level=logging.INFO, raw=raw)

		# 4. VCD / trace written
		if _RE_VCD_WRITTEN.search(line):
			return OutputLine(text=line, level=logging.WARNING, raw=raw)

		# 5. Yosys / solver error and warning pass-through
		lower = line.lower()
		if "error:" in lower or line.startswith("ERROR"):
			return OutputLine(text=line, level=logging.ERROR, raw=raw)
		if "warning:" in lower or line.startswith("Warning"):
			return OutputLine(text=line, level=logging.WARNING, raw=raw)

		# 6. Generic SBY info / everything else
		if _RE_SBY_ANY.match(line):
			return OutputLine(text=line, level=logging.DEBUG, raw=raw)

		return OutputLine(text=line, level=logging.DEBUG, raw=raw)

	# ------------------------------------------------------------------
	# Job construction
	# ------------------------------------------------------------------

	def verify_job(
		self,
		sby_file: str | Path,
		*,
		label: str,
		log_file: str,
		work_dir: str | None = None,
		task: str | None = None,
		force: bool = True,
	) -> typing.Self:
		"""Enqueue one SymbiYosys verification job.

		Parameters
		----------
		sby_file:
		    Path to the ``.sby`` configuration file that drives this run.
		label:
		    Short human-readable label shown in console and log output.
		log_file:
		    Destination file for captured stdout / stderr.
		work_dir:
		    CWD for the ``sby`` process.  Defaults to the parent directory
		    of ``sby_file`` so that relative paths in ``[files]`` resolve
		    correctly.
		task:
		    Named task to select from a multi-task ``.sby`` file.  Passed
		    verbatim as the last positional argument to ``sby``.
		force:
		    When ``True`` (the default) pass ``-f`` to ``sby``, causing it
		    to remove and recreate an existing work directory.
		"""
		sby_file = Path(sby_file).resolve()
		cwd = work_dir or str(sby_file.parent)

		cmd: list[str] = [self.sby_bin]
		if force:
			cmd.append("-f")
		cmd.append(str(sby_file))
		if task is not None:
			cmd.append(task)

		self._pairs.append(
			(
				sby_file,
				Job(
					label=label,
					cmd=tuple(cmd),
					cwd=cwd,
					log_file=log_file,
					classifier=self.classify,
					dry_run=self._cfg.dry_run,
					interactive=False,
					detach=False,
					env=None,
				),
			)
		)
		return self
