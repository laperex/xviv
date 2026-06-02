"""generator/sby.py — ``.sby`` configuration-file generator for SymbiYosys.

This module provides a structured, builder-style API for generating
SymbiYosys (``.sby``) configuration files from a
:class:`~xviv.config.model.FormalConfig` or from scratch.

Typical usage — from a ``FormalConfig``::

    from xviv.generator.sby import SbyGenerator

    content = SbyGenerator.from_config(fcfg).generate()
    SbyGenerator.from_config(fcfg).write(sby_path)

Typical usage — fluent builder::

    content = (
        SbyGenerator()
        .set_mode(SbyMode.BMC)
        .set_depth(20)
        .set_engine(SbyEngine.SMTBMC_YICES)
        .set_top("my_module")
        .add_source("/path/to/my_module.sv")
        .set_sv(True)
        .generate()
    )

Multi-task ``.sby`` (prove + cover in one file)::

    from xviv.generator.sby import SbyGenerator, SbyTask, SbyMode, SbyEngine

    gen = (
        SbyGenerator()
        .set_top("my_module")
        .add_source("/path/to/my_module.sv")
        .set_engine(SbyEngine.SMTBMC_YICES)
        .add_task(SbyTask("prove", mode=SbyMode.PROVE, depth=30))
        .add_task(SbyTask("cover", mode=SbyMode.COVER, depth=20, append=10,
                          engine=SbyEngine.SMTBMC_Z3))
    )
    gen.write("/build/formal/my_module.sby")
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
import logging  # noqa: E402  (standard lib import after local — acceptable for module-level logger)
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from xviv.config.model import FormalConfig

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------


class SbyEngine:
	"""Named engine constants and factory helpers for ``[engines]`` sections.

	Each class attribute is a ready-to-use engine line for a ``.sby`` file.
	The factory methods let you compose custom engine strings with arbitrary
	solver flags.

	SMT-BMC solvers
	~~~~~~~~~~~~~~~
	``SMTBMC_*`` constants target the ``smtbmc`` front-end, which drives a
	variety of SMT solvers.  ``SMTBMC_YICES`` is a good default for BMC and
	prove; ``SMTBMC_Z3`` is slower but handles more theories.

	Hardware model checkers
	~~~~~~~~~~~~~~~~~~~~~~~
	``BTOR`` uses the Boolector/Bitwuzla hardware model checker.
	``ABC_PDR`` uses the ABC tool's PDR/IC3 algorithm, which is excellent
	for unbounded proof but not suited to cover.
	"""

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
		"""Compose a ``smtbmc`` engine string.

		Parameters
		----------
		*solvers:
		    One or more SMT-solver names (e.g. ``"yices"``, ``"z3"``).
		    When more than one is given, ``smtbmc`` tries them in order.
		opts:
		    Additional ``smtbmc`` flags inserted before the solver names
		    (e.g. ``["--unroll"]`` or ``["--syn"]``).

		Examples
		--------
		>>> SbyEngine.smtbmc("yices", "z3")
		'smtbmc yices z3'
		>>> SbyEngine.smtbmc("yices", opts=["--unroll"])
		'smtbmc --unroll yices'
		"""
		parts = ["smtbmc"]
		parts.extend(opts or [])
		parts.extend(solvers)
		return " ".join(parts)

	@staticmethod
	def btor(*opts: str) -> str:
		"""Compose a ``btor`` engine string with optional flags.

		Examples
		--------
		>>> SbyEngine.btor()
		'btor'
		>>> SbyEngine.btor("--nopdr")
		'btor --nopdr'
		"""
		return " ".join(["btor", *opts])

	@staticmethod
	def abc(*opts: str) -> str:
		"""Compose an ``abc`` engine string.

		Examples
		--------
		>>> SbyEngine.abc("pdr")
		'abc pdr'
		"""
		return " ".join(["abc", *opts])


# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------


class SbyMode:
	"""SymbiYosys verification mode names."""

	BMC = "bmc"
	"""Bounded model checking — check assertions up to *depth* steps."""

	PROVE = "prove"
	"""Unbounded proof — prove assertions hold for all reachable states."""

	COVER = "cover"
	"""Cover-point reachability — find traces that hit ``cover`` statements."""

	LIVE = "live"
	"""Liveness checking (requires ``smtbmc`` with ``--bmc`` disabled)."""


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


@dataclass
class SbyTask:
	"""Configuration for one named task inside a multi-task ``.sby`` file.

	When one or more :class:`SbyTask` objects are added to a
	:class:`SbyGenerator`, the generator emits a ``[tasks]`` section and
	prefixes each task's option overrides with ``<name>:``.

	Parameters
	----------
	name:
	    Identifier used in ``[tasks]``, as a CLI argument to ``sby``,
	    and as a prefix for option overrides.
	mode:
	    Verification mode (:class:`SbyMode` constant or raw string).
	depth:
	    Depth override for this task; ``None`` inherits the global depth.
	append:
	    Cover-mode append override; ``None`` inherits the global value.
	engine:
	    Engine override for this task; ``None`` inherits the global engine.
	extra_opts:
	    Additional raw ``[options]`` lines prefixed with ``<name>:``.
	"""

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
	"""Fluent builder for the ``[script]`` section of a ``.sby`` file.

	Each method appends one Yosys command and returns ``self`` for
	chaining.  Call :meth:`build` to materialise the command list.

	Example::

	    lines = (
	        SbyScript()
	        .read_verilog("counter.sv", defines=["FORMAL"])
	        .hierarchy("counter")
	        .proc()
	        .opt()
	        .flatten()
	        .opt()
	        .setundef()
	        .build()
	    )
	"""

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
		"""Emit ``read_verilog [-formal] [-sv] [-D…] [-I…] <basename>``.

		Only the basename of *filename* is used because sby copies all
		declared files into a ``src/`` subdirectory before running Yosys.

		Parameters
		----------
		filename:
		    Path (or basename) of the source file to read.
		formal:
		    Emit ``-formal`` to expose ``$assert`` / ``$assume`` cells.
		sv:
		    Emit ``-sv`` for SystemVerilog support.
		defines:
		    Preprocessor macros emitted as ``-D<name>`` or ``-D<name>=<val>``.
		include_dirs:
		    Include directories emitted as ``-I<path>``.
		extra_flags:
		    Any additional flags appended verbatim.
		"""
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
		"""Emit ``hierarchy [-check] [-generate] -top <top>``."""
		parts = ["hierarchy"]
		if check:
			parts.append("-check")
		if generate:
			parts.append("-generate")
		parts += ["-top", top]
		self._lines.append(" ".join(parts))
		return self

	def proc(self, *, nofsm: bool = False) -> Self:
		"""Emit ``proc`` (process block lowering).

		Parameters
		----------
		nofsm:
		    Pass ``-nofsm`` to disable FSM extraction within ``proc``.
		"""
		self._lines.append("proc -nofsm" if nofsm else "proc")
		return self

	def opt(self, *, full: bool = True, nodffe: bool = False, nosdff: bool = False) -> Self:
		"""Emit an ``opt`` pass.

		Parameters
		----------
		full:
		    Emit ``-full`` for a more thorough (slower) optimisation pass.
		nodffe:
		    Emit ``-nodffe`` to skip D-flip-flop with enable extraction.
		nosdff:
		    Emit ``-nosdff`` to skip set/reset flip-flop extraction.
		"""
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
		"""Emit ``flatten`` (inline all module instances)."""
		self._lines.append("flatten")
		return self

	def setundef(self, *, zero: bool = True, undriven: bool = False) -> Self:
		"""Emit ``setundef`` to resolve undefined signal values.

		Parameters
		----------
		zero:
		    Emit ``-zero`` to drive all undefined signals to 0.
		undriven:
		    Emit ``-undriven`` to also handle undriven nets.
		"""
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
		"""Emit ``async2sync`` to convert asynchronous resets to synchronous.

		Required when using engines that don't handle async reset natively
		(most SMT-BMC configurations).
		"""
		self._lines.append("async2sync")
		return self

	def clk2fflogic(self) -> Self:
		"""Emit ``clk2fflogic`` to convert clock signals to FF logic.

		Use for designs verified without a global clock (multiclock mode).
		"""
		self._lines.append("clk2fflogic")
		return self

	def chformal(
		self,
		*,
		assume: bool = False,
		assert2assume: bool = False,
		live2dltl: bool = False,
	) -> Self:
		"""Emit ``chformal`` to transform formal properties.

		Parameters
		----------
		assume:
		    Convert all ``assert`` statements to ``assume``.
		assert2assume:
		    Alias for *assume*.
		live2dltl:
		    Convert liveness to DLTL properties.
		"""
		if assume or assert2assume:
			self._lines.append("chformal -assume")
		if live2dltl:
			self._lines.append("chformal -live2dltl")
		return self

	def prep(self, top: str) -> Self:
		"""Emit ``prep -top <top>`` (modern alternative to hierarchy + proc + opt).

		``prep`` is a convenience pass that runs hierarchy, proc, and a
		basic opt in one step.  Prefer the explicit sequence for reproducibility.
		"""
		self._lines.append(f"prep -top {top}")
		return self

	# ------------------------------------------------------------------
	# Escape hatch
	# ------------------------------------------------------------------

	def raw(self, line: str) -> Self:
		"""Append *line* verbatim to the script."""
		self._lines.append(line)
		return self

	def build(self) -> list[str]:
		"""Return the accumulated list of Yosys command strings."""
		return list(self._lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


class SbyGenerator:
	"""Generator for SymbiYosys (``.sby``) configuration files.

	Build either from a :class:`~xviv.config.model.FormalConfig` via the
	:meth:`from_config` class method, or incrementally using the fluent
	setter API.

	The generated file always contains:

	* ``[options]`` — verification mode, depth, multiclock flag, etc.
	* ``[engines]`` — solver / model-checker specification.
	* ``[script]`` — Yosys commands for reading and preparing the design.
	* ``[files]``  — absolute paths of all source files (copied by sby).

	When tasks are added via :meth:`add_task`, a ``[tasks]`` section is
	emitted and per-task option / engine overrides are injected.
	"""

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
	def from_config(cls, cfg: FormalConfig) -> "SbyGenerator":
		"""Return a :class:`SbyGenerator` fully populated from *cfg*.

		This is the primary entry point when generating a ``.sby`` file
		for a configured formal verification target.

		Parameters
		----------
		cfg:
		    A :class:`~xviv.config.model.FormalConfig` as returned by
		    :meth:`~xviv.config.project.XvivConfig.get_formal`.
		"""
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
		"""Set the verification mode (``bmc``, ``prove``, ``cover``, ``live``)."""
		self._mode = mode
		return self

	def set_depth(self, depth: int) -> Self:
		"""Set the BMC / prove depth (number of time steps)."""
		self._depth = depth
		return self

	def set_append(self, append: int) -> Self:
		"""Set cover-mode append depth (extra steps after cover is hit)."""
		self._append = append
		return self

	def set_engine(self, engine: str) -> Self:
		"""Set the default engine string (see :class:`SbyEngine`)."""
		self._engine = engine
		return self

	def set_top(self, top: str) -> Self:
		"""Set the top-level module name."""
		self._top = top
		return self

	def set_sv(self, sv: bool) -> Self:
		"""Enable or disable SystemVerilog parsing (``-sv`` to Yosys)."""
		self._sv = sv
		return self

	def set_defines(self, defines: list[str]) -> Self:
		"""Replace the preprocessor-define list."""
		self._defines = list(defines)
		return self

	def add_define(self, define: str) -> Self:
		"""Append one preprocessor define."""
		self._defines.append(define)
		return self

	def set_include_dirs(self, include_dirs: list[str]) -> Self:
		"""Replace the include-directory list."""
		self._include_dirs = list(include_dirs)
		return self

	def add_include_dir(self, path: str) -> Self:
		"""Append one include directory."""
		self._include_dirs.append(path)
		return self

	def set_sources(self, sources: list[str]) -> Self:
		"""Replace the source-file list with *sources* (absolute paths)."""
		self._sources = list(sources)
		return self

	def add_source(self, path: str) -> Self:
		"""Append one source file (absolute path)."""
		self._sources.append(path)
		return self

	def set_multiclock(self, multiclock: bool) -> Self:
		"""Enable or disable the ``multiclock on`` option."""
		self._multiclock = multiclock
		return self

	def set_async2sync(self, async2sync: bool) -> Self:
		"""Enable or disable the ``async2sync`` Yosys pass in the script."""
		self._async2sync = async2sync
		return self

	def set_clk2fflogic(self, clk2fflogic: bool) -> Self:
		"""Enable or disable ``clk2fflogic`` (use with multiclock designs)."""
		self._clk2fflogic = clk2fflogic
		return self

	def set_extra_opts(self, opts: list[str]) -> Self:
		"""Replace extra raw lines appended to ``[options]``."""
		self._extra_opts = list(opts)
		return self

	def add_extra_opt(self, opt: str) -> Self:
		"""Append one raw line to ``[options]``."""
		self._extra_opts.append(opt)
		return self

	def set_extra_script(self, lines: list[str]) -> Self:
		"""Replace extra raw lines appended to ``[script]``."""
		self._extra_script = list(lines)
		return self

	def add_extra_script(self, line: str) -> Self:
		"""Append one raw Yosys command to the end of ``[script]``."""
		self._extra_script.append(line)
		return self

	def add_task(self, task: SbyTask) -> Self:
		"""Register a :class:`SbyTask` for multi-task ``.sby`` generation."""
		self._tasks.append(task)
		return self

	def set_tasks(self, tasks: list[SbyTask]) -> Self:
		"""Replace the task list."""
		self._tasks = list(tasks)
		return self

	# ------------------------------------------------------------------
	# Internal section renderers
	# ------------------------------------------------------------------

	def _render_options(self) -> list[str]:
		"""Render the ``[options]`` section body."""
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
		"""Render the ``[tasks]`` section body, or ``None`` if no tasks."""
		if not self._tasks:
			return None
		return [task.name for task in self._tasks]

	def _render_engines(self) -> list[str]:
		"""Render the ``[engines]`` section body.

		With tasks, emit per-task engine lines where an override is set,
		and the default engine for any task that inherits it.
		"""
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
		"""Render the ``[script]`` section body via :class:`SbyScript`."""
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
		"""Render the ``[files]`` section body (one absolute path per line)."""
		return list(self._sources)

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def generate(self) -> str:
		"""Render the complete ``.sby`` file content and return it as a string.

		Raises
		------
		:exc:`ValueError`
		    When no source files have been provided, or no top module has
		    been set.
		"""
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
		"""Write the generated ``.sby`` content to *path*.

		Parent directories are created automatically.

		Returns
		-------
		:class:`~pathlib.Path`
		    The resolved, written path.
		"""
		dest = Path(path).resolve()
		dest.parent.mkdir(parents=True, exist_ok=True)
		dest.write_text(self.generate(), encoding="utf-8")
		logger.debug("wrote .sby file: %s", dest)
		return dest
