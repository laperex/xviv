from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CalledProcessError

from xviv.config.model import FormalConfig
from xviv.config.project import XvivConfig
from xviv.generator.sby import SbyGenerator
from xviv.tools.symbiyosys import SbyRunner
from xviv.utils import error
from xviv.utils.theme import theme_cfg

# from xviv.utils.error import JobFailedError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex: elapsed time in sby logfile  "SBY [00:01:23] ..."
_RE_SBY_TS = re.compile(r"SBY\s+\[(\d+):(\d+):(\d+)\]")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PropertyResult:
	name: str
	kind: str  # "assert" | "cover"
	passed: bool
	trace: str | None = None
	step: int | None = None


@dataclass
class FormalResult:
	name: str
	mode: str
	status: str
	passed: bool
	elapsed: float | None = None
	traces: list[str] = field(default_factory=list)
	log_file: str = ""
	sby_file: str = ""
	properties: list[PropertyResult] = field(default_factory=list)
	last_line: str = ""

	def __repr__(self) -> str:
		return f"FormalResult({self.name!r}, {self.status})"


# ---------------------------------------------------------------------------
# Helpers: sby output directory inspection
# ---------------------------------------------------------------------------


def _sby_work_dir(cfg: FormalConfig) -> Path:

	return Path(cfg.work_dir)


def _read_sby_status(work_dir: Path) -> str:

	status_file = work_dir / "status"
	try:
		text = status_file.read_text(encoding="utf-8").strip()
		return text if text else "UNKNOWN"
	except OSError:
		return "UNKNOWN"


def _find_traces(work_dir: Path) -> list[str]:

	if not work_dir.exists():
		return []
	return [str(p) for p in sorted(work_dir.rglob("*.vcd"))]


def _elapsed_from_logfile(log_file: str) -> float | None:

	try:
		text = Path(log_file).read_text(encoding="utf-8", errors="replace")
	except OSError:
		return None

	last: re.Match[str] | None = None
	for m in _RE_SBY_TS.finditer(text):
		last = m
	if last is None:
		return None

	h, m_, s = int(last.group(1)), int(last.group(2)), int(last.group(3))
	return h * 3600 + m_ * 60 + s


def _parse_properties(log_file: str, mode: str) -> list[PropertyResult]:

	try:
		text = Path(log_file).read_text(encoding="utf-8", errors="replace")
	except OSError:
		return []

	properties: list[PropertyResult] = []

	# Pair "Reached cover statement" with the immediately following VCD line
	cover_re = re.compile(r"Reached cover statement at (.+?) in step (\d+)", re.IGNORECASE)
	vcd_re = re.compile(r"Writing (?:trace|counterexample) to (?:VCD )?file[:\s]+(.+\.vcd)", re.IGNORECASE)

	cover_matches = list(cover_re.finditer(text))
	vcd_matches = list(vcd_re.finditer(text))

	if mode == "cover" and cover_matches:
		for i, cm in enumerate(cover_matches):
			vcd_path = vcd_matches[i].group(1).strip() if i < len(vcd_matches) else None
			properties.append(
				PropertyResult(
					name=cm.group(1).strip(),
					kind="cover",
					passed=True,
					trace=vcd_path,
					step=int(cm.group(2)),
				)
			)
		return properties

	# For BMC/prove: extract engine status lines
	engine_re = re.compile(r"engine_\d+(?:\s+\(step\s+(\d+)\))?:\s+(PASS|FAIL|UNKNOWN|ERROR|TIMEOUT)")
	for m in engine_re.finditer(text):
		step = int(m.group(1)) if m.group(1) else None
		status = m.group(2)
		kind = "assert"
		passed = status == "PASS"

		# Try to pair with a VCD line nearby if failed
		trace: str | None = None
		if not passed and vcd_matches:
			trace = vcd_matches[0].group(1).strip()

		properties.append(
			PropertyResult(
				name=f"engine result ({status})",
				kind=kind,
				passed=passed,
				trace=trace,
				step=step,
			)
		)

	return properties


def _last_nonempty_line(log_file: str) -> str:

	try:
		text = Path(log_file).read_text(encoding="utf-8", errors="replace")
		for line in reversed(text.splitlines()):
			stripped = line.strip()
			if stripped:
				return stripped
	except OSError:
		pass
	return ""


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run_formal(
	cfg: FormalConfig,
	*,
	project_cfg: XvivConfig,
	dry_run: bool = False,
) -> FormalResult:

	work_dir = _sby_work_dir(cfg)
	sby_dir = work_dir.parent
	sby_dir.mkdir(parents=True, exist_ok=True)

	sby_path = sby_dir / f"{cfg.name}.sby"
	log_file = os.path.join(project_cfg.log_dir, f"formal_{cfg.name}.log")

	# --- 1. Generate .sby ---------------------------------------------------
	SbyGenerator.from_config(cfg).write(sby_path)
	logger.debug("[formal:%s] wrote %s", cfg.name, sby_path)

	if dry_run:
		logger.info("[formal:%s] dry-run - skipping sby execution", cfg.name)
		logger.debug("[formal:%s] .sby content:\n%s", cfg.name, sby_path.read_text())
		return FormalResult(
			name=cfg.name,
			mode=cfg.mode,
			status="PASS",
			passed=True,
			elapsed=None,
			traces=[],
			log_file=log_file,
			sby_file=str(sby_path),
			last_line="(dry-run)",
		)

	# --- 2. Execute via SbyRunner -------------------------------------------
	t0 = time.monotonic()
	try:
		SbyRunner(project_cfg).verify_job(
			sby_file=sby_path,
			label=f"formal:{cfg.name}",
			log_file=log_file,
			work_dir=str(sby_dir),
			force=True,
		).run()
	except error.JobFailedError:
		# sby exits non-zero on FAIL/UNKNOWN/ERROR - this is expected.
		# We determine the true status from the output directory below.
		pass
	except CalledProcessError:
		# Same: non-zero exit from CalledProcessError raised by stream_pipe.
		pass
	elapsed = time.monotonic() - t0

	# --- 3. Determine status ------------------------------------------------
	status = _read_sby_status(work_dir)

	# Fall back: if the status file wasn't written (sby crashed), treat as ERROR
	if status == "UNKNOWN" and not work_dir.exists():
		status = "ERROR"

	passed = status == "PASS"

	# --- 4. Collect artifacts -----------------------------------------------
	traces = _find_traces(work_dir)
	properties = _parse_properties(log_file, cfg.mode)

	# Prefer elapsed from sby timestamps; wall-clock is fallback
	sby_elapsed = _elapsed_from_logfile(log_file)
	final_elapsed = sby_elapsed if sby_elapsed is not None else elapsed

	last_line = _last_nonempty_line(log_file)

	return FormalResult(
		name=cfg.name,
		mode=cfg.mode,
		status=status,
		passed=passed,
		elapsed=final_elapsed,
		traces=traces,
		log_file=log_file,
		sby_file=str(sby_path),
		properties=properties,
		last_line=last_line,
	)


# ---------------------------------------------------------------------------
# Top-level command
# ---------------------------------------------------------------------------


def _format_status(result: FormalResult) -> str:

	if result.status == "PASS":
		return theme_cfg.passed("PASS")
	if result.status in {"FAIL", "ERROR"}:
		return theme_cfg.fail(result.status)

	return theme_cfg.warn(result.status)


def _log_result(result: FormalResult) -> None:

	if result.traces:
		for trace in result.traces:
			logger.warning("  counterexample - %s", trace)
			logger.warning("  open with:       gtkwave %s", trace)

	if result.properties:
		for prop in result.properties:
			sym = "PASS" if prop.passed else "FAIL"
			step_info = f"  @step {prop.step}" if prop.step is not None else ""
			logger.debug("    %s  [%s]  %s%s", sym, prop.kind, prop.name, step_info)

	if result.elapsed is not None:
		logger.debug("  elapsed: %.1f s", result.elapsed)

	if result.log_file:
		logger.debug("  log:     %s", result.log_file)


def cmd_formal(
	cfg: XvivConfig,
	*,
	target: str | None = None,
	parallel: bool = True,
	max_workers: int = 4,
) -> None:

	all_cfgs = cfg.get_formal_list()

	if not all_cfgs:
		raise error.FormalNoTargetsError()

	if target is not None:
		targets = [cfg.get_formal(target)]
	else:
		targets = all_cfgs

	# Validate all selected targets before starting any run
	for fcfg in targets:
		cfg.validate_formal(fcfg.name)

	# ------------------------------------------------------------------
	# Header banner
	# ------------------------------------------------------------------
	n = len(targets)
	mode_summary = ", ".join(sorted({f.mode for f in targets}))
	logger.info(
		"\n%s Formal Verification %s  [%d target%s  modes: %s]",
		"=" * 20,
		"=" * 20,
		n,
		"s" if n != 1 else "",
		mode_summary,
	)

	# ------------------------------------------------------------------
	# Execute - parallel or sequential
	# ------------------------------------------------------------------
	results: list[FormalResult] = []

	if parallel and len(targets) > 1:
		logger.info(theme_cfg.dim(f"Parallel execution  max_workers={max_workers}"))

		def _run(fcfg: FormalConfig) -> FormalResult:
			_log_target_header(fcfg)
			return run_formal(fcfg, project_cfg=cfg, dry_run=cfg.dry_run)

		with ThreadPoolExecutor(max_workers=max_workers) as pool:
			future_to_cfg = {pool.submit(_run, fcfg): fcfg for fcfg in targets}
			for future in as_completed(future_to_cfg):
				try:
					result = future.result()
				except Exception as exc:
					fcfg = future_to_cfg[future]
					logger.error("[formal:%s] unexpected error: %s", fcfg.name, exc)
					result = FormalResult(
						name=fcfg.name,
						mode=fcfg.mode,
						status="ERROR",
						passed=False,
						last_line=str(exc),
					)
				results.append(result)
	else:
		for fcfg in targets:
			_log_target_header(fcfg)
			result = run_formal(fcfg, project_cfg=cfg, dry_run=cfg.dry_run)
			results.append(result)

	# Restore deterministic order (parallel futures complete out of order)
	name_to_result = {r.name: r for r in results}
	results = [name_to_result[fcfg.name] for fcfg in targets if fcfg.name in name_to_result]

	# ------------------------------------------------------------------
	# Per-target detail
	# ------------------------------------------------------------------
	for result in results:
		_log_result(result)

	# ------------------------------------------------------------------
	# Summary table
	# ------------------------------------------------------------------
	divider = "-" * 58
	logger.info("\nFormal Results  %s", divider)
	logger.info("  %-32s  %-8s  %s", "Target", "Mode", "Status")
	logger.info("  %s", divider)

	for result in results:
		elapsed_str = f"{result.elapsed:.0f}s" if result.elapsed is not None else "-"
		status_tag = _format_status(result)
		logger.info(
			"  %-32s  %-8s  %s  %s",
			result.name,
			result.mode,
			status_tag,
			theme_cfg.dim(f"({elapsed_str})"),
		)

	logger.info("  %s", divider)

	# ------------------------------------------------------------------
	# Final outcome
	# ------------------------------------------------------------------
	failed = [r for r in results if not r.passed]
	passed = [r for r in results if r.passed]

	logger.info(
		"\n  %s   %s",
		theme_cfg.passed(f"{len(passed)} passed"),
		theme_cfg.fail(f"{len(failed)} failed"),
	)

	if failed:
		logger.error(
			"\nFailing targets: %s",
			", ".join(r.name for r in failed),
		)
		raise SystemExit(1)


def _log_target_header(fcfg: FormalConfig) -> None:
	title = f"formal: {fcfg.name}  [{fcfg.mode}, depth={fcfg.depth}]"

	logger.info("\n%s", theme_cfg.bold(title))
