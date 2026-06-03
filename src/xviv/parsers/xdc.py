from __future__ import annotations

import tkinter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PortConstraint:
	package_pin: Optional[str] = None
	iostandard: Optional[str] = None
	drive: Optional[str] = None
	slew: Optional[str] = None
	pulltype: Optional[str] = None  # PULLUP / PULLDOWN / KEEPER
	diff_term: Optional[str] = None
	is_clock: bool = False
	clock_name: Optional[str] = None
	clock_period_ns: Optional[float] = None
	has_input_delay: bool = False
	has_output_delay: bool = False
	has_false_path: bool = False
	has_max_delay: bool = False
	has_set_logic: bool = False
	extra_props: Dict[str, str] = field(default_factory=dict)

	def merge(self, other: "PortConstraint") -> None:

		for attr in ("package_pin", "iostandard", "drive", "slew", "pulltype", "diff_term", "clock_name"):
			if getattr(self, attr) is None and getattr(other, attr) is not None:
				setattr(self, attr, getattr(other, attr))
		if not self.is_clock:
			self.is_clock = other.is_clock
		if self.clock_period_ns is None:
			self.clock_period_ns = other.clock_period_ns
		self.has_input_delay |= other.has_input_delay
		self.has_output_delay |= other.has_output_delay
		self.has_false_path |= other.has_false_path
		self.has_max_delay |= other.has_max_delay
		self.has_set_logic |= other.has_set_logic
		self.extra_props.update({k: v for k, v in other.extra_props.items() if k not in self.extra_props})

	def is_timing_constrained(self) -> bool:
		return any(
			[
				self.is_clock,
				self.has_input_delay,
				self.has_output_delay,
				self.has_false_path,
				self.has_max_delay,
				self.has_set_logic,
			]
		)

	def is_empty(self) -> bool:
		return self.package_pin is None and self.iostandard is None and not self.is_timing_constrained() and not self.extra_props


# ---------------------------------------------------------------------------
# XDC Parser
# ---------------------------------------------------------------------------


class XDCParser:
	def __init__(self) -> None:
		self.tcl = tkinter.Tcl()
		self.port_constraints: Dict[str, PortConstraint] = {}
		self.clocks: Dict[str, PortConstraint] = {}
		self.parse_warnings: List[str] = []
		self._register_commands()

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	def _clean(self, args: tuple) -> List[str]:
		return [str(a).strip() for a in args]

	def _get_constraint(self, port_pattern: str) -> PortConstraint:
		p = port_pattern.strip()
		if p not in self.port_constraints:
			self.port_constraints[p] = PortConstraint()
		return self.port_constraints[p]

	def _parse_port_targets(self, raw: str) -> List[str]:
		return [t.strip() for t in raw.split() if t.strip()]

	# ------------------------------------------------------------------
	# Tcl command registration
	# ------------------------------------------------------------------

	def _register_commands(self) -> None:
		t = self.tcl

		# Core port query / property commands
		t.createcommand("get_ports", self._stub_get_ports)
		t.createcommand("get_clocks", self._stub_get_clocks)
		t.createcommand("get_property", self._stub_get_property)
		t.createcommand("set_property", self._stub_set_property)

		# Object queries that return empty strings (not needed for lint)
		for cmd in (
			"get_pins",
			"get_nets",
			"get_cells",
			"get_pblocks",
			"get_macros",
			"get_generated_clocks",
			"get_path_groups",
			"get_timing_arcs",
			"get_speed_models",
			"get_iobanks",
			"get_package_pins",
			"get_sites",
			"get_bel_pins",
			"get_bels",
			"get_nodes",
			"get_pips",
			"get_site_pins",
			"get_site_pips",
			"get_slrs",
			"get_tiles",
			"get_wires",
			"get_pkgpin_bytegroups",
			"get_pkgpin_nibbles",
			"all_clocks",
			"all_inputs",
			"all_outputs",
			"all_registers",
			"all_ffs",
			"all_latches",
			"all_cpus",
			"all_dsps",
			"all_rams",
			"all_hsios",
			"all_fanin",
			"all_fanout",
			"get_debug_cores",
			"get_debug_ports",
		):
			t.createcommand(cmd, self._stub_noop_str)

		# Timing constraints
		t.createcommand("create_clock", self._stub_create_clock)
		t.createcommand("create_generated_clock", self._stub_create_generated_clock)
		t.createcommand("set_input_delay", self._stub_input_delay)
		t.createcommand("set_output_delay", self._stub_output_delay)
		t.createcommand("set_false_path", self._stub_false_path)
		t.createcommand("set_max_delay", self._stub_max_delay)
		for cmd in (
			"set_min_delay",
			"set_multicycle_path",
			"set_clock_groups",
			"set_clock_latency",
			"set_clock_uncertainty",
			"set_clock_sense",
			"set_input_jitter",
			"set_system_jitter",
			"set_propagated_clock",
			"set_external_delay",
			"set_max_time_borrow",
			"set_data_check",
			"set_disable_timing",
			"set_case_analysis",
			"set_bus_skew",
			"group_path",
		):
			t.createcommand(cmd, self._stub_flag_noop)

		# Netlist / logic constraints
		for cmd in (
			"set_load",
			"set_logic_one",
			"set_logic_zero",
			"set_logic_dc",
			"set_logic_unconnected",
		):
			t.createcommand(cmd, self._stub_set_logic)
		t.createcommand("make_diff_pair_ports", self._stub_flag_noop)

		# Physical / floorplan
		for cmd in (
			"add_cells_to_pblock",
			"create_pblock",
			"delete_pblock",
			"remove_cells_from_pblock",
			"resize_pblock",
			"create_macro",
			"delete_macros",
			"update_macro",
			"set_package_pin_val",
		):
			t.createcommand(cmd, self._stub_flag_noop)

		# Debug
		for cmd in ("create_debug_core", "create_debug_port", "connect_debug_port"):
			t.createcommand(cmd, self._stub_flag_noop)

		# Power
		for cmd in (
			"set_power_opt",
			"set_switching_activity",
			"reset_switching_activity",
			"set_operating_conditions",
			"reset_operating_conditions",
			"add_to_power_rail",
			"create_power_rail",
			"delete_power_rails",
			"get_power_rails",
			"remove_from_power_rail",
		):
			t.createcommand(cmd, self._stub_flag_noop)

		# Waivers
		t.createcommand("create_waiver", self._stub_flag_noop)

		# General purpose (some are Vivado overloads of built-in Tcl commands)
		for cmd in (
			"current_design",
			"current_instance",
			"get_hierarchy_separator",
			"set_hierarchy_separator",
			"set_units",
			"startgroup",
			"endgroup",
			"create_property",
		):
			t.createcommand(cmd, self._stub_noop_str)

	# ------------------------------------------------------------------
	# Stub implementations
	# ------------------------------------------------------------------

	@staticmethod
	def _stub_noop_str(*_args) -> str:
		return ""

	@staticmethod
	def _stub_flag_noop(*_args) -> str:
		return ""

	def _stub_get_ports(self, *args) -> str:
		a = self._clean(args)
		filtered: List[str] = []
		skip_next = False
		for tok in a:
			if skip_next:
				skip_next = False
				continue
			if tok.startswith("-"):
				skip_next = True
			else:
				filtered.append(tok)
		return " ".join(filtered) if filtered else ""

	def _stub_get_clocks(self, *args) -> str:
		a = self._clean(args)
		return a[-1] if a else ""

	@staticmethod
	def _stub_get_property(*_args) -> str:
		return ""

	# ------------------------------------------------------------------
	# set_property (most important stub)
	# ------------------------------------------------------------------

	def _stub_set_property(self, *raw_args) -> str:

		args = self._clean(raw_args)
		if not args:
			return ""

		if args[0] == "-dict" and len(args) >= 3:
			kv_str = args[1]
			port_raw = " ".join(args[2:])
			kv_tokens = kv_str.split()
			props: Dict[str, str] = {}
			it = iter(kv_tokens)
			for k in it:
				try:
					props[k.upper()] = next(it)
				except StopIteration:
					break
			for port_pat in self._parse_port_targets(port_raw):
				self._apply_props(self._get_constraint(port_pat), props)
			return ""

		if len(args) >= 3:
			prop = args[0].upper()
			value = args[1]
			port_raw = " ".join(args[2:])
			for port_pat in self._parse_port_targets(port_raw):
				self._apply_props(self._get_constraint(port_pat), {prop: value})
		return ""

	@staticmethod
	def _apply_props(c: PortConstraint, props: Dict[str, str]) -> None:
		for k, v in props.items():
			k = k.upper()
			if k == "PACKAGE_PIN":
				c.package_pin = v
			elif k == "IOSTANDARD":
				c.iostandard = v
			elif k == "DRIVE":
				c.drive = v
			elif k in ("SLEW", "SLEWRATE"):
				c.slew = v
			elif k in ("PULLTYPE", "PULLUP", "PULLDOWN", "KEEPER"):
				c.pulltype = k if k != "PULLTYPE" else v
			elif k == "DIFF_TERM":
				c.diff_term = v
			else:
				c.extra_props[k] = v

	# ------------------------------------------------------------------
	# create_clock / create_generated_clock
	# ------------------------------------------------------------------

	def _stub_create_clock(self, *raw_args) -> str:

		args = self._clean(raw_args)
		name = None
		period = None
		port_target: Optional[str] = None

		i = 0
		while i < len(args):
			tok = args[i]
			if tok == "-name" and i + 1 < len(args):
				name = args[i + 1]
				i += 2
			elif tok == "-period" and i + 1 < len(args):
				try:
					period = float(args[i + 1])
				except ValueError:
					pass
				i += 2
			elif tok in ("-add", "-add_delay"):
				i += 1
			elif tok in (
				"-waveform",
				"-edges",
				"-edge_shift",
				"-multiply_by",
				"-divide_by",
				"-invert",
				"-combinational",
				"-source",
			):
				i += 2
			elif not tok.startswith("-"):
				port_target = tok
				i += 1
			else:
				i += 1

		clk_name = name or (port_target or "_unnamed_clk")
		c_clk = PortConstraint(
			is_clock=True,
			clock_name=clk_name,
			clock_period_ns=period,
		)
		self.clocks[clk_name] = c_clk

		if port_target:
			for pat in self._parse_port_targets(port_target):
				pc = self._get_constraint(pat)
				pc.is_clock = True
				pc.clock_name = clk_name
				pc.clock_period_ns = period
		return ""

	def _stub_create_generated_clock(self, *raw_args) -> str:
		return self._stub_create_clock(*raw_args)

	# ------------------------------------------------------------------
	# Timing constraint stubs
	# ------------------------------------------------------------------

	def _stub_input_delay(self, *raw_args) -> str:
		args = self._clean(raw_args)
		target = self._extract_last_non_flag(args)
		if target:
			for pat in self._parse_port_targets(target):
				self._get_constraint(pat).has_input_delay = True
		return ""

	def _stub_output_delay(self, *raw_args) -> str:
		args = self._clean(raw_args)
		target = self._extract_last_non_flag(args)
		if target:
			for pat in self._parse_port_targets(target):
				self._get_constraint(pat).has_output_delay = True
		return ""

	def _stub_false_path(self, *raw_args) -> str:
		args = self._clean(raw_args)
		for flag in ("-to", "-from", "-through"):
			val = self._flag_value(args, flag)
			if val:
				for pat in self._parse_port_targets(val):
					self._get_constraint(pat).has_false_path = True
		return ""

	def _stub_max_delay(self, *raw_args) -> str:
		args = self._clean(raw_args)
		for flag in ("-to", "-from", "-datapath_only"):
			val = self._flag_value(args, flag)
			if val:
				for pat in self._parse_port_targets(val):
					self._get_constraint(pat).has_max_delay = True
		return ""

	def _stub_set_logic(self, *raw_args) -> str:
		args = self._clean(raw_args)
		target = self._extract_last_non_flag(args)
		if target:
			for pat in self._parse_port_targets(target):
				self._get_constraint(pat).has_set_logic = True
		return ""

	# ------------------------------------------------------------------
	# Flag-parsing helpers
	# ------------------------------------------------------------------

	@staticmethod
	def _flag_value(args: List[str], flag: str) -> Optional[str]:
		for i, a in enumerate(args):
			if a == flag and i + 1 < len(args):
				return args[i + 1]
		return None

	@staticmethod
	def _extract_last_non_flag(args: List[str]) -> Optional[str]:
		for tok in reversed(args):
			if not tok.startswith("-") and tok:
				return tok
		return None

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def parse(self, xdc_filepath: str) -> "XDCParser":

		try:
			safe_path = xdc_filepath.replace("\\", "/")
			self.tcl.eval(f'source "{safe_path}"')
		except tkinter.TclError as e:
			msg = str(e)
			if "invalid command name" in msg or "unknown command" in msg:
				self.parse_warnings.append(f"Tcl stub missing: {msg}")
			else:
				self.parse_warnings.append(f"Tcl error in {xdc_filepath}: {msg}")
		return self
