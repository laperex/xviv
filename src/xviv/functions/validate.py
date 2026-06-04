from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from xviv.config.params import ValidateParams
from xviv.config.project import XvivConfig
from xviv.parsers.rtl import PortInfo, RTLPortExtractor
from xviv.parsers.xdc import PortConstraint, XDCParser
from xviv.utils.ascii_table import AsciiTable
from xviv.utils.theme import theme_cfg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XDC glob - Python regex
# ---------------------------------------------------------------------------


def _xdc_pat_to_re(pattern: str) -> re.Pattern:

	buf: list[str] = []
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
		port_constraints: dict[str, PortConstraint],
		rtl_ports: list[PortInfo],
		clocks: dict[str, PortConstraint],
	) -> None:
		self.port_constraints = port_constraints
		self.rtl_ports = rtl_ports
		self.clocks = clocks
		self.results: list[LintResult] = []
		self.stale_patterns: list[str] = []

	def run(self) -> None:
		self.results.clear()
		self.stale_patterns.clear()

		# Expand every RTL port to its individual bits.
		all_bits: dict[str, PortInfo] = {}
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
	def errors(self) -> list[LintResult]:
		return [r for r in self.results if r.no_xdc_entry]

	@property
	def warnings(self) -> list[LintResult]:
		return [r for r in self.results if not r.no_xdc_entry and (r.missing_pkg_pin or r.missing_iostd or r.missing_clk_def)]

	@property
	def ok(self) -> list[LintResult]:
		return [r for r in self.results if not r.no_xdc_entry and not r.missing_pkg_pin and not r.missing_iostd and not r.missing_clk_def]


def _truncate_str(s: str, MAX_NAME=30) -> str:
	return s if len(s) <= MAX_NAME else s[: MAX_NAME - 3] + "..."


def print_io_report(
	linter: XDCLinter, rtl_extractor: RTLPortExtractor, xdc_parser: XDCParser, xdc_paths: list[str], rtl_paths: list[str], error_only: bool = False
) -> None:
	def get_timing(c: PortConstraint) -> str:
		if c.is_clock:
			ps = f"{c.clock_period_ns:.2f}ns" if c.clock_period_ns else "?"
			return theme_cfg.bold(theme_cfg.cyan(f"CLK({ps})"))  # bold cyan
		if c.has_false_path:
			return theme_cfg.dim("FP")
		if c.has_input_delay:
			return theme_cfg.green("IN_DLY")
		if c.has_output_delay:
			return theme_cfg.green("OUT_DLY")
		if c.has_max_delay:
			return theme_cfg.dim("MAX_DLY")
		if c.has_set_logic:
			return theme_cfg.dim("SET_LGC")
		return theme_cfg.dim("-")

	def row_status(r: LintResult) -> str:
		if r.no_xdc_entry:
			return theme_cfg.fail("ERROR")
		if r.missing_pkg_pin or r.missing_iostd or r.missing_clk_def:
			return theme_cfg.warn("WARN")
		return theme_cfg.ok("OK")

	def pkg_pin_str(c: PortConstraint, no_xdc: bool) -> str:
		if c.package_pin:
			return c.package_pin
		if not no_xdc:
			return theme_cfg.error("MISSING")
		return theme_cfg.dim("-")

	def iostd_str(c: PortConstraint, no_xdc: bool) -> str:
		if c.iostandard:
			return theme_cfg.bold(c.iostandard)
		if not no_xdc:
			return theme_cfg.error("MISSING")
		return theme_cfg.dim("-")

	def dir_str(c: str) -> str:
		if c == "In":
			return theme_cfg.cyan(c)

		return theme_cfg.magenta(c)

	def type_str(c: str) -> str:
		if c == "<error>":
			return theme_cfg.error("MISSING")

		if c:
			return c

		return theme_cfg.dim("-")

	# --- Build table rows ---

	errors = linter.errors
	warnings = linter.warnings
	stale = linter.stale_patterns

	if not errors and not warnings and not stale:
		error_only = False

	rows: list[list[str]] = []

	port_groups: dict[str, list[LintResult]] = {}
	for r in linter.results:
		port_groups.setdefault(r.port_info.name, []).append(r)

	for port_name, group in port_groups.items():
		pi = group[0].port_info

		all_ok = all(not (r.no_xdc_entry or r.missing_pkg_pin or r.missing_iostd) for r in group)
		all_nocon = all(r.no_xdc_entry for r in group)
		bus_compact = pi.width > 1 and (all_ok or all_nocon)

		for i, r in enumerate(group):
			c = r.constraint

			if bus_compact and i == 0:
				status = theme_cfg.fail("ERROR") if all_nocon else theme_cfg.ok("OK")
				name = _truncate_str(f"{port_name}[{pi.lsb}..{pi.msb}]")
				direc = dir_str(pi.direction)
				type_ = type_str(pi.type_str)
			elif bus_compact:
				status = name = direc = type_ = ""
			else:
				status = row_status(r)
				name = _truncate_str(r.port_bit)
				direc = dir_str(r.direction)
				type_ = type_str(r.port_info.type_str)

			if not status and not name and not direc and not type_:
				continue

			if error_only and "OK" in status:
				continue

			rows.append([status, name, direc, type_, pkg_pin_str(c, r.no_xdc_entry), iostd_str(c, r.no_xdc_entry), get_timing(c)])

	if rows:
		t = AsciiTable(
			title="I/O COVERAGE" + (" ERRORS" if error_only else "") + (" - OK" if not errors and not warnings and not stale else ""),
			headers=["STATUS", "Port", "Dir", "Type", "PKG_PIN", "IOSTANDARD", "Timing"],
		)

		for row in rows:
			t.add_row(*row)
		t.print()

	# # --- Issues ---
	if errors or warnings or stale:
		t = AsciiTable(
			title="I/O ISSUES" + (" ERRORS" if error_only else ""),
		)

		for r in errors:
			t.add_row(theme_cfg.fail("UNCONSTRAINED"), r.port_bit, dir_str(r.direction), "no XDC entry", "RTL")

		if warnings:
			if errors:
				t.add_divider()

		for r in warnings:
			issues = []
			if r.missing_pkg_pin:
				issues.append("no PACKAGE_PIN")
			if r.missing_iostd:
				issues.append("no IOSTANDARD")
			if r.missing_clk_def:
				issues.append("no create_clock")
			t.add_row(theme_cfg.warn("PARTIALLY CONSTRAINED"), r.port_bit, dir_str(r.direction), "  ·  ".join(issues), "RTL")

		if stale:
			if errors or warnings:
				t.add_divider()

		for p in stale:
			t.add_row(theme_cfg.critical("STALE"), p, "", "", "XDC")

		t.print()

	# if stale:
	# 	print(f"\n{theme_cfg.header('STALE XDC')}")
	# 	for p in stale:
	# 		print(f"  {theme_cfg.dim('?')}  {p}")

	# # --- Summary ---
	# total = len(linter.results)
	# n_ok = len(linter.ok)
	# n_warn = len(warnings)
	# n_err = len(errors)
	# pct_ok = int(100 * n_ok / total) if total else 0

	# print("\nSUMMARY")
	# print(f"  Total   : {total}")
	# print(f"  OK      : {theme_cfg.green(str(n_ok))}  ({pct_ok}%)")
	# print(f"  Warnings: {theme_cfg.yellow(str(n_warn)) if n_warn else str(n_warn)}")
	# print(f"  Errors  : {theme_cfg.red(str(n_err)) if n_err else str(n_err)}")

	# if not (errors or warnings or stale):
	# 	print(theme_cfg.green("\nAll RTL ports are fully constrained."))
	# 	return 0
	# return 1


# ---------------------------------------------------------------------------
# Public command
# ---------------------------------------------------------------------------


def cmd_validate_synth(cfg: XvivConfig, params: ValidateParams) -> None:
	design_name = params.design
	bd_name = params.bd
	core_name = params.core

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
	rtl_files: list[str] = []
	top_module: str | None = synth_cfg.top

	if design_name:
		design_cfg = cfg.get_design(design_name)
		rtl_files = [sf.file for sf in design_cfg.sources if sf.used_in_synth]

	elif bd_name:
		bd_cfg = cfg.get_bd(bd_name)
		rtl_files = [bd_cfg.bd_wrapper_file]

	if not rtl_files:
		logger.error("No RTL source files could be resolved for the validate target.")
		return

	xdc_parser = XDCParser()
	for xdc_file in xdc_files:
		xdc_parser.parse(xdc_file)

	rtl_extractor = RTLPortExtractor(rtl_files, top_module=top_module)

	if rtl_extractor.errors and not rtl_extractor.ports:
		for e in rtl_extractor.errors:
			logger.error("RTL extraction failed: %s", e)
		return

	synth_cfg = cfg.get_synth(bd_name=params.bd, design_name=params.design, core_name=params.core)

	print()
	if bd_name:
		print(f"BD     : {bd_name}")
	if design_name:
		print(f"Design : {design_name}")
	if core_name:
		print(f"Core   : {core_name}")

	print(f"Top    : {synth_cfg.top}")
	print(f"FPGA   : {synth_cfg.fpga}")

	if fpga_cfg := cfg._get_fpga_cfg_optional(synth_cfg.fpga):
		if fpga_cfg.board_part:
			print(f"  {fpga_cfg.board_part}")
		if fpga_cfg.fpga_part:
			print(f"  {fpga_cfg.fpga_part}")
	else:
		logger.error(f"FPGA - {synth_cfg.fpga} specified in [[synth]] not defined in config.")

	print(
		"STAGES:\t"
		+ "  ──▶  ".join(
			[
				theme_cfg.green(name)
				for name, flag in [
					("SYNTH", synth_cfg.run_synth),
					("OPT", synth_cfg.run_opt),
					("PLACE", synth_cfg.run_place),
					("PHYS_OPT", synth_cfg.run_phys_opt),
					("ROUTE", synth_cfg.run_route),
				]
				if flag
			]
		)
	)

	t_srcs = AsciiTable(
		title="SOURCE FILES",
		headers=["STATUS", "FILE", "TYPE", "INFO"],
	)

	for file in rtl_files:
		t_srcs.add_row(
			theme_cfg.green("OK") if os.path.exists(file) else theme_cfg.error("NOT FOUND"),
			file,
			"RTL",
			"",
		)

	if rtl_files:
		if xdc_files:
			t_srcs.add_divider()

	for file in xdc_files:
		t_srcs.add_row(theme_cfg.green("OK") if os.path.exists(file) else theme_cfg.error("NOT FOUND"), file, "XDC", "")

	t_srcs.print()

	t_options = AsciiTable(
		title="CONFIGURATION",
		headers=["STAGE", "OPTION", "VALUE"],
	)

	for stage_idx, stage in enumerate(["synth", "opt", "place", "phys_opt", "route"]):
		if stage_idx != 0:
			t_options.add_divider()
		for option_idx, option in enumerate(["directive", "mode", "flatten_hierarchy", "fsm_extraction"]):
			if val := getattr(synth_cfg, f"{stage}_{option}", None):
				t_options.add_row(stage if option_idx == 0 else "", option, val)

	t_options.print()

	if params.io:
		linter = XDCLinter(
			xdc_parser.port_constraints,
			rtl_extractor.ports,
			xdc_parser.clocks,
		)
		linter.run()

		print_io_report(linter, rtl_extractor, xdc_parser, xdc_paths=xdc_files, rtl_paths=rtl_files, error_only=(params.io == "error"))
