from __future__ import annotations

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
import logging
import os
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from xviv.config.model import FormalConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------


class SbyEngine:
	# ---- smtbmc-based ----
	SMTBMC_YICES = "smtbmc yices"
	SMTBMC_Z3 = "smtbmc z3"
	SMTBMC_BOOLECTOR = "smtbmc boolector"
	SMTBMC_BITWUZLA = "smtbmc bitwuzla"
	SMTBMC_MATHSAT = "smtbmc mathsat"
	SMTBMC_CVC4 = "smtbmc cvc4"
	SMTBMC_CVC5 = "smtbmc cvc5"

	# ---- hardware model checkers ----
	BTOR = "btor"
	ABC_PDR = "abc pdr"

	# ---- combinational (no depth) ----
	SMTBMC_COMB = "smtbmc --comb yices"

	@staticmethod
	def smtbmc(*solvers: str, opts: list[str] | None = None) -> str:
		parts = ["smtbmc"]
		parts.extend(opts or [])
		parts.extend(solvers)
		return " ".join(parts)

	@staticmethod
	def btor(*opts: str) -> str:
		return " ".join(["btor", *opts])

	@staticmethod
	def abc(*opts: str) -> str:
		return " ".join(["abc", *opts])


# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------


class SbyMode:
	BMC = "bmc"
	PROVE = "prove"
	COVER = "cover"
	LIVE = "live"


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


@dataclass
class SbyTask:
	name: str
	mode: str
	depth: int | None = None
	append: int | None = None
	engine: str | None = None
	extra_opts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------


class SbyScript:
	def __init__(self) -> None:
		self._lines: list[str] = []

	# ------------------------------------------------------------------
	# Read commands
	# ------------------------------------------------------------------

	def read_verilog(
		self,
		filename: str,
		*,
		formal: bool = True,
		sv: bool = True,
		defines: list[str] | None = None,
		include_dirs: list[str] | None = None,
		extra_flags: list[str] | None = None,
	) -> Self:
		parts = ["read_verilog"]
		if formal:
			parts.append("-formal")
		if sv:
			parts.append("-sv")
		for d in defines or []:
			parts.append(f"-D{d}")
		for i in include_dirs or []:
			parts.append(f"-I{i}")
		parts.extend(extra_flags or [])
		parts.append(os.path.basename(filename))
		self._lines.append(" ".join(parts))
		return self

	# ------------------------------------------------------------------
	# Synthesis / preparation passes
	# ------------------------------------------------------------------

	def hierarchy(self, top: str, *, check: bool = True, generate: bool = False) -> Self:
		parts = ["hierarchy"]
		if check:
			parts.append("-check")
		if generate:
			parts.append("-generate")
		parts += ["-top", top]
		self._lines.append(" ".join(parts))
		return self

	def proc(self, *, nofsm: bool = False) -> Self:
		self._lines.append("proc -nofsm" if nofsm else "proc")
		return self

	def opt(self, *, full: bool = True, nodffe: bool = False, nosdff: bool = False) -> Self:
		parts = ["opt"]
		if full:
			parts.append("-full")
		if nodffe:
			parts.append("-nodffe")
		if nosdff:
			parts.append("-nosdff")
		self._lines.append(" ".join(parts))
		return self

	def flatten(self) -> Self:
		self._lines.append("flatten")
		return self

	def setundef(self, *, zero: bool = True, undriven: bool = False) -> Self:
		parts = ["setundef"]
		if zero:
			parts.append("-zero")
		if undriven:
			parts.append("-undriven")
		self._lines.append(" ".join(parts))
		return self

	# ------------------------------------------------------------------
	# Formal-specific transforms
	# ------------------------------------------------------------------

	def async2sync(self) -> Self:
		self._lines.append("async2sync")
		return self

	def clk2fflogic(self) -> Self:
		self._lines.append("clk2fflogic")
		return self

	def chformal(
		self,
		*,
		assume: bool = False,
		assert2assume: bool = False,
		live2dltl: bool = False,
	) -> Self:
		if assume or assert2assume:
			self._lines.append("chformal -assume")
		if live2dltl:
			self._lines.append("chformal -live2dltl")
		return self

	def prep(self, top: str) -> Self:
		self._lines.append(f"prep -top {top}")
		return self

	# ------------------------------------------------------------------
	# Escape hatch
	# ------------------------------------------------------------------

	def raw(self, line: str) -> Self:
		self._lines.append(line)
		return self

	def build(self) -> list[str]:
		return list(self._lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


class SbyGenerator:
	def __init__(self) -> None:
		self._mode: str = SbyMode.BMC
		self._depth: int = 20
		self._append: int = 0
		self._engine: str = SbyEngine.SMTBMC_YICES
		self._top: str = ""
		self._sv: bool = True
		self._defines: list[str] = []
		self._include_dirs: list[str] = []
		self._sources: list[str] = []
		self._multiclock: bool = False
		self._async2sync: bool = False
		self._clk2fflogic: bool = False
		self._extra_opts: list[str] = []
		self._extra_script: list[str] = []
		self._tasks: list[SbyTask] = []

	# ------------------------------------------------------------------
	# Class-method constructor
	# ------------------------------------------------------------------

	@classmethod
	def from_config(cls, cfg: FormalConfig) -> typing.Self:
		gen = cls()
		gen._mode = cfg.mode
		gen._depth = cfg.depth
		gen._append = cfg.append
		gen._engine = cfg.engine
		gen._top = cfg.top
		gen._sv = cfg.sv
		gen._defines = list(cfg.defines)
		gen._include_dirs = list(cfg.include_dirs)
		gen._sources = [s.file for s in cfg.sources]
		gen._multiclock = cfg.multiclock
		gen._async2sync = cfg.async2sync
		gen._extra_opts = list(cfg.extra_opts)
		gen._extra_script = list(cfg.extra_script)
		return gen

	# ------------------------------------------------------------------
	# Fluent setters
	# ------------------------------------------------------------------

	def set_mode(self, mode: str) -> Self:

		self._mode = mode
		return self

	def set_depth(self, depth: int) -> Self:

		self._depth = depth
		return self

	def set_append(self, append: int) -> Self:

		self._append = append
		return self

	def set_engine(self, engine: str) -> Self:

		self._engine = engine
		return self

	def set_top(self, top: str) -> Self:

		self._top = top
		return self

	def set_sv(self, sv: bool) -> Self:

		self._sv = sv
		return self

	def set_defines(self, defines: list[str]) -> Self:

		self._defines = list(defines)
		return self

	def add_define(self, define: str) -> Self:

		self._defines.append(define)
		return self

	def set_include_dirs(self, include_dirs: list[str]) -> Self:

		self._include_dirs = list(include_dirs)
		return self

	def add_include_dir(self, path: str) -> Self:

		self._include_dirs.append(path)
		return self

	def set_sources(self, sources: list[str]) -> Self:

		self._sources = list(sources)
		return self

	def add_source(self, path: str) -> Self:

		self._sources.append(path)
		return self

	def set_multiclock(self, multiclock: bool) -> Self:

		self._multiclock = multiclock
		return self

	def set_async2sync(self, async2sync: bool) -> Self:

		self._async2sync = async2sync
		return self

	def set_clk2fflogic(self, clk2fflogic: bool) -> Self:

		self._clk2fflogic = clk2fflogic
		return self

	def set_extra_opts(self, opts: list[str]) -> Self:

		self._extra_opts = list(opts)
		return self

	def add_extra_opt(self, opt: str) -> Self:

		self._extra_opts.append(opt)
		return self

	def set_extra_script(self, lines: list[str]) -> Self:

		self._extra_script = list(lines)
		return self

	def add_extra_script(self, line: str) -> Self:

		self._extra_script.append(line)
		return self

	def add_task(self, task: SbyTask) -> Self:

		self._tasks.append(task)
		return self

	def set_tasks(self, tasks: list[SbyTask]) -> Self:

		self._tasks = list(tasks)
		return self

	# ------------------------------------------------------------------
	# Internal section renderers
	# ------------------------------------------------------------------

	def _render_options(self) -> list[str]:

		lines: list[str] = []

		if self._tasks:
			# In multi-task mode the global options serve as defaults;
			# each task then overrides what it needs.
			for task in self._tasks:
				lines.append(f"{task.name}: mode {task.mode}")
			lines.append(f"depth {self._depth}")
			if self._mode == SbyMode.COVER and self._append:
				lines.append(f"append {self._append}")
			for task in self._tasks:
				if task.depth is not None:
					lines.append(f"{task.name}: depth {task.depth}")
				if task.mode == SbyMode.COVER and task.append is not None:
					lines.append(f"{task.name}: append {task.append}")
				for opt in task.extra_opts:
					lines.append(f"{task.name}: {opt}")
		else:
			lines.append(f"mode {self._mode}")
			lines.append(f"depth {self._depth}")
			if self._mode == SbyMode.COVER and self._append:
				lines.append(f"append {self._append}")

		if self._multiclock:
			lines.append("multiclock on")

		lines.extend(self._extra_opts)
		return lines

	def _render_tasks(self) -> list[str] | None:

		if not self._tasks:
			return None
		return [task.name for task in self._tasks]

	def _render_engines(self) -> list[str]:

		if not self._tasks:
			return [self._engine]

		lines: list[str] = []
		# Tasks that have an explicit engine
		task_with_engine = {t.name for t in self._tasks if t.engine is not None}

		# Emit default engine only when at least one task inherits it
		if len(task_with_engine) < len(self._tasks):
			lines.append(self._engine)

		for task in self._tasks:
			if task.engine is not None:
				lines.append(f"{task.name}: {task.engine}")

		return lines

	def _render_script(self) -> list[str]:

		builder = SbyScript()

		if not self._sources:
			raise ValueError("SbyGenerator: cannot generate [script] — no source files have been added")

		# Read every source file.  Defines and include dirs apply to the
		# first file only; subsequent files inherit them through Yosys's
		# shared define/include state.
		for i, src in enumerate(self._sources):
			builder.read_verilog(
				src,
				formal=True,
				sv=self._sv,
				defines=self._defines if i == 0 else None,
				include_dirs=self._include_dirs if i == 0 else None,
			)

		# Standard formal preparation sequence
		builder.hierarchy(self._top)
		builder.proc()
		builder.opt(full=True)
		builder.flatten()
		builder.opt(full=True)
		builder.setundef(zero=True)

		# Optional clock-domain transforms (order matters)
		if self._async2sync:
			builder.async2sync()
			builder.opt(full=True)
		if self._clk2fflogic:
			builder.clk2fflogic()

		# User-supplied extra passes
		for line in self._extra_script:
			builder.raw(line)

		return builder.build()

	def _render_files(self) -> list[str]:

		return list(self._sources)

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def generate(self) -> str:

		if not self._top:
			raise ValueError("SbyGenerator: top module must be set before generating")
		if not self._sources:
			raise ValueError("SbyGenerator: at least one source file must be added before generating")

		parts: list[str] = []

		def section(name: str, lines: list[str]) -> None:
			parts.append(f"[{name}]")
			parts.extend(lines)
			parts.append("")  # blank line between sections

		# Optional [tasks] (must come first so sby reads it before [options])
		tasks_body = self._render_tasks()
		if tasks_body is not None:
			section("tasks", tasks_body)

		section("options", self._render_options())
		section("engines", self._render_engines())
		section("script", self._render_script())
		section("files", self._render_files())

		return "\n".join(parts)

	def write(self, path: str | Path) -> Path:

		dest = Path(path).resolve()
		dest.parent.mkdir(parents=True, exist_ok=True)
		dest.write_text(self.generate(), encoding="utf-8")
		logger.debug("wrote .sby file: %s", dest)
		return dest
