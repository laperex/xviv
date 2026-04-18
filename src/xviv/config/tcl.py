from datetime import datetime, timezone
import logging
import os
import sys
import typing

from xviv.config.model import ProjectConfig
from xviv.catalog import data
from xviv.utils.fs import _tcl_list

logger = logging.getLogger(__name__)

# =============================================================================
# TCL config generator
#
# Produces a self-contained TCL snippet that sets every global variable used
# by scripts/xviv.tcl and its sub-scripts.  All variables are always emitted
# (set to empty / zero by default) so TCL scripts never encounter unset vars.
#
# ip_name / bd_name / top_name select which context-specific block is active.
# =============================================================================

def generate_config_tcl(
	cfg: ProjectConfig,
	*,
	ip_name:  typing.Optional[str] = None,
	bd_name:  typing.Optional[str] = None,
	top_name: typing.Optional[str] = None,

	core_name: typing.Optional[str] = None,
	core_vlnv: typing.Optional[str] = None,
) -> str:
	if sum(arg is not None for arg in (top_name, bd_name, ip_name, core_name)) != 1:
		sys.exit("ERROR: get_synth requires exactly one of 'top_name', 'bd_name', 'ip_name' or 'core_id' to be specified.")

	lines: list[str] = []

	# ---- resolve FPGA target (entry-level fpga = '<name>' override) ------------------
	fpga_ref: str = ""
	if bd_name:
		fpga_ref = cfg.get_bd(bd_name).fpga
	elif top_name:
		fpga_ref = cfg.get_synth(top_name=top_name).fpga

	fpga = cfg.resolve_fpga(fpga_ref or None)
	logger.debug("FPGA target: %s  part=%s", fpga_ref or "<default>", fpga.part)

	# ---- Vivado tuning ----------------------------------------------------------------------------------------------------------------
	lines.append(f"set_param general.maxThreads {cfg.vivado.max_threads}")

	# ---- FPGA ----------------------------------------------------------------------------------------------------------------------------------
	if fpga.board_repo:
		lines.append(f'set_param board.repoPaths [list "{fpga.board_repo}"]')

	lines += [
		f'set xviv_fpga_part  "{fpga.part}"',
		f'set xviv_board_part "{fpga.board_part}"',
		f'set xviv_board_repo "{fpga.board_repo}"',
	]

	# ---- Build paths ----------------------------------------------------------------------------------------------------------------------
	lines += [
		f'set xviv_build_dir   "{cfg.build_dir}"',
		f'set xviv_ip_repo     "{cfg.ip_repo}"',
		f'set xviv_bd_dir      "{cfg.bd_dir}"',
		f'set xviv_wrapper_dir "{cfg.wrapper_dir}"',
	]

	# ---- Synthesis report / netlist flags (defaults off) --------------------------------------------
	lines += [
		"set xviv_synth_report_synth    0",
		"set xviv_synth_report_place    0",
		"set xviv_synth_report_route    0",
		"set xviv_synth_generate_netlist 0",
		'set xviv_synth_hooks           ""',
	]

	# ---- IP variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_ip_name    ""',
		'set xviv_ip_vendor  ""',
		'set xviv_ip_library ""',
		'set xviv_ip_version ""',
		'set xviv_ip_top     ""',
		'set xviv_ip_hooks   ""',
	]

	# ---- BD variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_bd_name       ""',
		'set xviv_bd_hooks      ""',
		'set xviv_bd_state_tcl  ""',
	]

	# ---- Core variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_core_vlnv     ""',
		'set xviv_core_name     ""',
	]
	# =========================================================================
	# Context-specific overrides
	# =========================================================================

	synth	= cfg.get_synth(top_name=top_name, bd_name=bd_name, ip_name=ip_name)

	synth_hooks	= cfg.abs_path(synth.hooks) if synth.hooks else ""

	xdc		= cfg.resolve_globs(synth.xdc) if synth.xdc else []
	rtl		= cfg.resolve_globs(synth.rtl) if synth.rtl else []

	if ip_name:
		ip    = cfg.get_ip(ip_name)
		ip_hooks = cfg.abs_path(ip.hooks) if ip.hooks else ""
		# IP-specific RTL overrides the global source glob; fall back if empty
		rtl = cfg.resolve_globs(ip.rtl)

		if not os.path.exists(ip_hooks):
			ip_hooks = ""

		lines += [
			f'set xviv_ip_name    "{ip.name}"',
			f'set xviv_ip_vendor  "{ip.vendor}"',
			f'set xviv_ip_library "{ip.library}"',
			f'set xviv_ip_version "{ip.version}"',
			f'set xviv_ip_top     "{ip.top}"',
			f'set xviv_ip_hooks   "{ip_hooks}"',
		]

	elif bd_name:
		bd     	= cfg.get_bd(bd_name)
		bd_hooks	= cfg.abs_path(bd.hooks) if bd.hooks else ""

		if not os.path.exists(bd_hooks):
			bd_hooks = ""

		# For BD commands the "RTL" source is the .bd file itself;
		# the synthesised wrapper is the companion .v file.
		bd_file   = os.path.join(cfg.bd_dir, bd_name, f"{bd_name}.bd")
		wrap_file = os.path.join(cfg.wrapper_dir, f"{bd_name}_wrapper.v")

		rtl = [wrap_file, bd_file]

		lines += [
			f'set xviv_bd_name       "{bd.name}"',
			f'set xviv_bd_hooks      "{bd_hooks}"',
			f'set xviv_bd_state_tcl  "{bd.export_tcl}"'
		]
	elif core_name:
		core_entry = data.lookup(cfg.vivado.path, [ cfg.ip_repo ], core_vlnv or "")
		
		core_dir = cfg.core_dir

		lines += [
			f'set xviv_core_vlnv     "{core_entry.vlnv}"',
			f'set xviv_core_name     "{core_name}"',
			f'set xviv_core_dir      "{core_dir}"',
		]

	if not os.path.exists(synth_hooks):
		synth_hooks = ""

	lines += [
		f'set xviv_synth_hooks            "{synth_hooks}"',
		f"set xviv_xdc_files              {_tcl_list(xdc)}",
		f"set xviv_rtl_files              {_tcl_list(rtl)}",
		f"set xviv_synth_report_synth     {int(synth.report_synth)}",
		f"set xviv_synth_report_place     {int(synth.report_place)}",
		f"set xviv_synth_report_route     {int(synth.report_route)}",
		f"set xviv_synth_generate_netlist {int(synth.generate_netlist)}",
	]

	def _fmt_list(name, items):
		if not items:
			return f"{name:<16}: <none>"
		lines = [f"{name:<16}:"]
		lines += [f"  - {x}" for x in items]
		return "\n".join(lines)


	# overview_lines = [
	# 	"\n===============================================================",
	# 	"CONFIGURATION OVERVIEW",
	# 	"===============================================================",
	# 	f"Mode            : {'IP' if ip_name else 'BD' if bd_name else 'TOP'}",
	# 	f"Target Name     : {ip_name or bd_name or top_name}",
	# 	f"FPGA Part       : {fpga.part}",
	# 	f"Board Part      : {fpga.board_part}",
	# 	f"Board Repo      : {fpga.board_repo}",
	# 	f"Build Dir       : {cfg.build_dir}",
	# 	f"IP Repo         : {cfg.ip_repo}",
	# 	f"BD Dir          : {cfg.bd_dir}",
	# 	f"Wrapper Dir     : {cfg.wrapper_dir}",
	# 	f"Max Threads     : {cfg.vivado.max_threads}",
	# 	f"Report Synth    : {synth.report_synth}",
	# 	f"Report Place    : {synth.report_place}",
	# 	f"Report Route    : {synth.report_route}",
	# 	f"Generate Netlist: {synth.generate_netlist}",
	# 	f"Synth Hooks     : {synth_hooks or '<none>'}",
	# 	_fmt_list("XDC Files", xdc),
	# 	_fmt_list("RTL Files", rtl),
	# 	"===============================================================",
	# ]

	# logger.info("\n".join(overview_lines))
	
	lines += [
		f"set xviv_iso_timestamp {datetime.now(timezone.utc).isoformat()}"
	]

	return "\n".join(lines) + "\n"
