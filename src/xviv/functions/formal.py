from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from xviv.config.model import FormalConfig
from xviv.config.project import XvivConfig
from xviv.utils import error

logger = logging.getLogger(__name__)


def generate_sby(cfg: FormalConfig) -> str:
	basenames = [os.path.basename(s.file) for s in cfg.sources]

	options: list[str] = [f"mode {cfg.mode}", f"depth {cfg.depth}"]

	if cfg.mode == "cover" and cfg.append:
		options.append(f"append {cfg.append}")
	if cfg.multiclock:
		options.append("multiclock on")

	options.extend(cfg.extra_opts)

	flags_global: list[str] = ["-formal"]

	if cfg.sv:
		flags_global.append("-sv")

	flags_global += [f"-D {d}" for d in cfg.defines]
	flags_global += [f"-I {d}" for d in cfg.include_dirs]
	flags_global_str = " ".join(flags_global)

	flags_extra = "-formal" + (" -sv" if cfg.sv else "")

	script: list[str] = []

	for i, bn in enumerate(basenames):
		if i == 0:
			script.append(f"read_verilog {flags_global_str} {bn}")
		else:
			script.append(f"read_verilog {flags_extra} {bn}")

	script += [
		f"hierarchy -check -top {cfg.top}",
		"proc",
		"opt -full",
		"flatten",
		"opt -full",
		"setundef -zero",
	]

	if cfg.async2sync:
		script.append("async2sync")
		script.append("opt -full")

	script.extend(cfg.extra_script)

	lines: list[str] = [
		"[options]",
		*options,
		"",
		"[engines]",
		cfg.engine,
		"",
		"[script]",
		*script,
		"",
		"[files]",
		*[s.file for s in cfg.sources],
		"",
	]
	return "\n".join(lines)


class FormalResult:
	def __init__(self, name: str, passed: bool, last_line: str, vcd: str | None) -> None:
		self.name = name
		self.passed = passed
		self.last_line = last_line
		self.vcd = vcd

	def __repr__(self) -> str:
		status = "PASS" if self.passed else "FAIL"
		return f"FormalResult({self.name!r}, {status})"


def run_formal(cfg: FormalConfig, *, dry_run: bool = False) -> FormalResult:
	work_dir = Path(cfg.work_dir)
	sby_dir = work_dir.parent
	sby_dir.mkdir(parents=True, exist_ok=True)

	sby_path = sby_dir / f"{cfg.name}.sby"
	sby_path.write_text(generate_sby(cfg))

	if dry_run:
		logger.info(f"[formal] wrote {sby_path}  (dry-run, not executing)")
		logger.info(sby_path.read_text())
		return FormalResult(cfg.name, passed=True, last_line="(dry-run)", vcd=None)

	sby_bin = shutil.which("sby")

	if sby_bin is None:
		raise error.FormalSbyNotFoundError()

	cmd = ["sby", "-f", str(sby_path)]
	last_line = ""

	with subprocess.Popen(
		cmd,
		cwd=str(sby_dir),
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	) as proc:
		for line in proc.stdout:
			print(line, end="", flush=True)

			if line.strip():
				last_line = line.strip()
		proc.wait()

	passed = proc.returncode == 0

	vcd: str | None = None
	if not passed:
		task_dir = sby_dir / cfg.name
		candidates = list(task_dir.rglob("*.vcd")) if task_dir.exists() else []
		if candidates:
			vcd = str(candidates[0])

	return FormalResult(
		name=cfg.name,
		passed=passed,
		last_line=last_line,
		vcd=vcd,
	)


def cmd_formal(cfg: XvivConfig, *, target: str | None = None) -> None:
	all_cfgs = cfg.get_formal_list()

	if not all_cfgs:
		raise error.FormalNoTargetsError()

	targets = [cfg.get_formal(target)] if target is not None else all_cfgs

	results: list[FormalResult] = []

	for fcfg in targets:
		cfg.validate_formal(fcfg.name)

		header = f"Formal: {fcfg.name}  [{fcfg.mode}, depth={fcfg.depth}]"
		logger.info(f"\n{header} {'-' * max(0, 60 - len(header))}")

		result = run_formal(fcfg, dry_run=cfg.dry_run)
		results.append(result)

		if result.vcd:
			logger.info(f"   counterexample trace -> {result.vcd}")
			logger.info(f"   open with: gtkwave {result.vcd}")

	logger.info("Formal Results " + "-" * 44)
	for r in results:
		status = "\033[32mPASS\033[0m" if r.passed else "\033[31mFAIL\033[0m"
		logger.info(f"  {r.name:<30}  {status}")

	failed = [r for r in results if not r.passed]
	if failed:
		raise SystemExit(1)
