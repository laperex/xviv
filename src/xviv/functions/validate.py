from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from xviv.config.params import ValidateParams
from xviv.config.project import XvivConfig
from xviv.parsers.rtl import PortInfo, RTLPortExtractor
from xviv.parsers.xdc import PortConstraint, XDCParser
from xviv.utils.ascii_table import AsciiTable
from xviv.utils.log import _supports_color

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ANSI colour helpers (honour NO_COLOR / non-TTY)
# ---------------------------------------------------------------------------


def _c(code: str, text: str) -> str:
	if not _supports_color():
		return text
	return f"\033[{code}m{text}\033[0m"


def _RED(t: str) -> str:
	return _c("31;1", t)


def _YELLOW(t: str) -> str:
	return _c("33;1", t)


def _GREEN(t: str) -> str:
	return _c("32;1", t)


def _CYAN(t: str) -> str:
	return _c("36", t)


def _BOLD(t: str) -> str:
	return _c("1", t)


def _DIM(t: str) -> str:
	return _c("2", t)


# ---------------------------------------------------------------------------
# XDC glob - Python regex
# ---------------------------------------------------------------------------


def _xdc_pat_to_re(pattern: str) -> re.Pattern:

	buf: List[str] = []
	i = 0
	while i < len(pattern):
		c = pattern[i]
		if c == "*":
			buf.append(".*")
		elif c == "?":
			buf.append(".")
		elif c == "[":
			j = pattern.find("]", i + 1)
			if j == -1:
				buf.append(r"\[")
			else:
				inner = pattern[i + 1 : j]
				if inner == "*":
					buf.append(r"\[[^\]]*\]")
					i = j + 1
					continue
				elif inner == "?":
					buf.append(r"\[[^\]]\]")
					i = j + 1
					continue
				else:
					buf.append(r"\[" + re.escape(inner) + r"\]")
					i = j + 1
					continue
		elif c in r"\.^${}()+|":
			buf.append("\\" + c)
		else:
			buf.append(re.escape(c))
		i += 1
	return re.compile("^" + "".join(buf) + "$")


def _matches(bit: str, pattern: str) -> bool:
	rx = _xdc_pat_to_re(pattern)
	if rx.match(bit):
		return True

	# Plain name (no brackets) matches unexpanded bus bit names too.
	if "[" not in pattern:
		base = re.match(r"^(\w+)", bit)
		if base and base.group(1) == pattern:
			return True
	return False


# ---------------------------------------------------------------------------
# Lint engine data model
# ---------------------------------------------------------------------------


@dataclass
class LintResult:
	port_bit: str
	direction: str
	port_info: PortInfo
	constraint: PortConstraint
	no_xdc_entry: bool = False
	missing_pkg_pin: bool = False
	missing_iostd: bool = False
	missing_clk_def: bool = False


# ---------------------------------------------------------------------------
# Lint engine
# ---------------------------------------------------------------------------


class XDCLinter:
	def __init__(
		self,
		port_constraints: Dict[str, PortConstraint],
		rtl_ports: List[PortInfo],
		clocks: Dict[str, PortConstraint],
	) -> None:
		self.port_constraints = port_constraints
		self.rtl_ports = rtl_ports
		self.clocks = clocks
		self.results: List[LintResult] = []
		self.stale_patterns: List[str] = []

	def run(self) -> None:
		self.results.clear()
		self.stale_patterns.clear()

		# Expand every RTL port to its individual bits.
		all_bits: Dict[str, PortInfo] = {}
		for pi in self.rtl_ports:
			for bit in pi.expand_bits():
				all_bits[bit] = pi

		# For each bit, merge all matching XDC constraints.
		for bit, pi in sorted(all_bits.items(), key=lambda x: (x[1].name, x[0])):
			merged = PortConstraint()
			matched_any = False

			for pattern, pc in self.port_constraints.items():
				if _matches(bit, pattern):
					merged.merge(pc)
					matched_any = True

			r = LintResult(
				port_bit=bit,
				direction=pi.direction,
				port_info=pi,
				constraint=merged,
			)
			if not matched_any:
				r.no_xdc_entry = True
			else:
				r.missing_pkg_pin = merged.package_pin is None
				r.missing_iostd = merged.iostandard is None
				if pi.direction == "In":
					is_clk_name = bool(re.search(r"clk|clock|sys_clk", bit, re.I))
					if is_clk_name and not merged.is_clock:
						r.missing_clk_def = True

			self.results.append(r)

		# Identify stale patterns (XDC entries that matched nothing in RTL).
		for pattern in self.port_constraints:
			if not any(_matches(bit, pattern) for bit in all_bits):
				self.stale_patterns.append(pattern)

	# ------------------------------------------------------------------
	# Convenience sub-lists
	# ------------------------------------------------------------------

	@property
	def errors(self) -> List[LintResult]:
		return [r for r in self.results if r.no_xdc_entry]

	@property
	def warnings(self) -> List[LintResult]:
		return [r for r in self.results if not r.no_xdc_entry and (r.missing_pkg_pin or r.missing_iostd or r.missing_clk_def)]

	@property
	def ok(self) -> List[LintResult]:
		return [r for r in self.results if not r.no_xdc_entry and not r.missing_pkg_pin and not r.missing_iostd and not r.missing_clk_def]


# ---------------------------------------------------------------------------
# Terminal report
# ---------------------------------------------------------------------------

_DIR_CODES = {"In": "36", "Out": "33;1", "InOut": "35"}


def _dir_str(d: str) -> str:
	code = _DIR_CODES.get(d, "0")
	return _c(code, f"{d:6}")


def _timing_str(c: PortConstraint) -> str:
	if c.is_clock:
		ps = f"{c.clock_period_ns:.2f}ns" if c.clock_period_ns else "?"
		return _GREEN(f"CLK({ps})")
	if c.has_false_path:
		return _DIM("FP")
	if c.has_input_delay:
		return _GREEN("IN_DLY")
	if c.has_output_delay:
		return _GREEN("OUT_DLY")
	if c.has_max_delay:
		return _DIM("MAX_DLY")
	if c.has_set_logic:
		return _DIM("SET_LGC")
	return _DIM("─")


def _print_bit_row(r: LintResult, indent: int = 2) -> None:
	c = r.constraint
	bad = r.no_xdc_entry or r.missing_pkg_pin or r.missing_iostd
	pkg = c.package_pin or ""
	std = c.iostandard or ""
	pkg_d = _GREEN(pkg) if pkg else (_RED("MISSING") if not r.no_xdc_entry else _DIM("─"))
	std_d = _GREEN(std) if std else (_RED("MISSING") if not r.no_xdc_entry else _DIM("─"))
	marker = _RED("✗") if r.no_xdc_entry else (_YELLOW("⚠") if bad else _GREEN("✓"))
	name_str = " " * indent + r.port_bit
	print(f"  {marker} {name_str}  {_dir_str(r.direction)}  {r.port_info.type_str}  {pkg_d}  {std_d}  {_timing_str(c)}")


def print_io_report(
	linter: XDCLinter,
	rtl_extractor: RTLPortExtractor,
	xdc_parser: XDCParser,
	xdc_paths: List[str],
	rtl_paths: List[str],
) -> int:

	MAX_NAME = 30

	def trunc(s: str) -> str:
		return s if len(s) <= MAX_NAME else s[: MAX_NAME - 3] + "..."

	def timing_plain(c: PortConstraint) -> str:
		if c.is_clock:
			ps = f"{c.clock_period_ns:.2f}ns" if c.clock_period_ns else "?"
			return f"CLK({ps})"
		if c.has_false_path:
			return "FP"
		if c.has_input_delay:
			return "IN_DLY"
		if c.has_output_delay:
			return "OUT_DLY"
		if c.has_max_delay:
			return "MAX_DLY"
		if c.has_set_logic:
			return "SET_LGC"
		return "-"

	def row_status(r: LintResult) -> str:
		if r.no_xdc_entry:
			return "FAIL"
		if r.missing_pkg_pin or r.missing_iostd or r.missing_clk_def:
			return "WARN"
		return "OK"

	# --- Header ---
	for p in rtl_paths:
		print(f"RTL : {_CYAN(p)}")
	print(f"Top : {_BOLD(rtl_extractor.module_name or '?')}")
	for p in xdc_paths:
		print(f"XDC : {_CYAN(p)}")
	for e in rtl_extractor.errors:
		print(_RED(f"RTL error: {e}"))
	for w in xdc_parser.parse_warnings:
		print(_YELLOW(f"XDC warning: {w}"))

	# --- Build table rows ---
	rows: List[List[str]] = []
	port_groups: Dict[str, List[LintResult]] = {}
	for r in linter.results:
		port_groups.setdefault(r.port_info.name, []).append(r)

	for port_name, group in port_groups.items():
		pi = group[0].port_info

		if pi.width == 1:
			r = group[0]
			c = r.constraint
			rows.append(
				[
					row_status(r),
					trunc(r.port_bit),
					pi.direction,
					pi.type_str,
					c.package_pin or "-",
					c.iostandard or "-",
					timing_plain(c),
				]
			)
			continue

		all_ok = all(not (r.no_xdc_entry or r.missing_pkg_pin or r.missing_iostd) for r in group)
		all_nocon = all(r.no_xdc_entry for r in group)

		if all_ok or all_nocon:
			combined = PortConstraint()
			for r in group:
				combined.merge(r.constraint)
			rows.append(
				[
					"FAIL" if all_nocon else "OK",
					trunc(f"{port_name}[{pi.lsb}..{pi.msb}]"),
					pi.direction,
					pi.type_str,
					combined.package_pin or "-",
					combined.iostandard or "-",
					timing_plain(combined),
				]
			)
		else:
			# Mixed status: expand to one row per bit
			for r in group:
				c = r.constraint
				rows.append(
					[
						row_status(r),
						trunc(r.port_bit),
						r.direction,
						r.port_info.type_str,
						c.package_pin or ("MISSING" if not r.no_xdc_entry else "-"),
						c.iostandard or ("MISSING" if not r.no_xdc_entry else "-"),
						timing_plain(c),
					]
				)

	# --- Render box table ---

	# COLOR_MAP = {
	# 	"OK": _GREEN,
	# 	"FAIL": _RED,
	# 	"WARN": _YELLOW,
	# 	"-": _DIM,
	# 	"FP": _DIM,
	# 	"MISSING": _RED,
	# 	"IN_DLY": _GREEN,
	# 	"OUT_DLY": _GREEN,
	# 	"MAX_DLY": _DIM,
	# 	"SET_LGC": _DIM,
	# 	"In": _BLUE,
	# }

	t = AsciiTable(
		headers=["Status", "Port", "Dir", "Type", "PKG_PIN", "IOSTANDARD", "Timing"],
		max_widths=[6, 30],
		# color_map=COLOR_MAP,
	)

	for row in rows:
		t.add_row(*row)
	t.print()

	# --- Issues ---
	errors = linter.errors
	warnings = linter.warnings
	stale = linter.stale_patterns

	if errors:
		print(f"\n{_RED('ERRORS')} - ports with no XDC entry:")
		for r in errors:
			print(f"  x {r.port_bit}  [{r.direction}]")

	if warnings:
		print(f"\n{_YELLOW('WARNINGS')} - partially constrained ports:")
		for r in warnings:
			issues: List[str] = []
			if r.missing_pkg_pin:
				issues.append("no PACKAGE_PIN")
			if r.missing_iostd:
				issues.append("no IOSTANDARD")
			if r.missing_clk_def:
				issues.append("clock - no create_clock")
			print(f"  ! {r.port_bit}  {', '.join(issues)}")

	if stale:
		print(f"\n{_YELLOW('STALE XDC')} - patterns matching no RTL port:")
		for p in stale:
			print(f"  ? {p}")

	# --- Summary ---
	total = len(linter.results)
	n_ok = len(linter.ok)
	n_warn = len(warnings)
	n_err = len(errors)
	pct_ok = int(100 * n_ok / total) if total else 0

	print("\nSUMMARY")
	print(f"  Total   : {total}")
	print(f"  OK      : {_GREEN(str(n_ok))}  ({pct_ok}%)")
	print(f"  Warnings: {_YELLOW(str(n_warn)) if n_warn else str(n_warn)}")
	print(f"  Errors  : {_RED(str(n_err)) if n_err else str(n_err)}")

	if not (errors or warnings or stale):
		print(_GREEN("\nAll RTL ports are fully constrained."))
		return 0
	return 1


# ---------------------------------------------------------------------------
# Public command
# ---------------------------------------------------------------------------


def cmd_validate_io(cfg: XvivConfig, params: ValidateParams) -> None:
	design_name = params.design
	bd_name = params.bd
	core_name = params.core

	# --- core: not yet implemented ----------------------------------------
	if core_name:
		logger.warning("validate synth --core is not yet implemented for standalone core targets.  Skipping validation.")
		return

	# --- Resolve synth config ---------------------------------------------
	synth_cfg = cfg.get_synth(
		design_name=design_name,
		bd_name=bd_name,
		core_name=core_name,
	)

	# --- Collect XDC constraint files -------------------------------------
	xdc_files = [sf.file for sf in synth_cfg.constraints if sf.file.endswith(".xdc")]
	if not xdc_files:
		logger.warning("No .xdc constraint files found for this synth target.")

	# --- Collect RTL source files + determine top -------------------------
	rtl_files: List[str] = []
	top_module: Optional[str] = synth_cfg.top

	if design_name:
		# Sources come from the [[sources]] block of the [[design]] entry.
		design_cfg = cfg.get_design(design_name)
		rtl_files = [sf.file for sf in design_cfg.sources if sf.used_in_synth]

	elif bd_name:
		# For a BD target the single RTL source is the generated wrapper file.
		bd_cfg = cfg.get_bd(bd_name)
		rtl_files = [bd_cfg.bd_wrapper_file]

	if not rtl_files:
		logger.error("No RTL source files could be resolved for the validate target.")
		return

	# --- Parse XDC --------------------------------------------------------
	xdc_parser = XDCParser()
	for xdc_file in xdc_files:
		xdc_parser.parse(xdc_file)

	# --- Extract RTL ports ------------------------------------------------
	rtl_extractor = RTLPortExtractor(rtl_files, top_module=top_module)

	if rtl_extractor.errors and not rtl_extractor.ports:
		for e in rtl_extractor.errors:
			logger.error("RTL extraction failed: %s", e)
		return

	# --- Run lint ---------------------------------------------------------
	linter = XDCLinter(
		xdc_parser.port_constraints,
		rtl_extractor.ports,
		xdc_parser.clocks,
	)
	linter.run()

	# --- Report -----------------------------------------------------------

	if rc := print_io_report(
		linter,
		rtl_extractor,
		xdc_parser,
		xdc_paths=xdc_files,
		rtl_paths=rtl_files,
	):
		sys.exit(rc)
