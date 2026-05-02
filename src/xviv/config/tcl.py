from datetime import datetime, timezone
import logging
import os
import sys
import typing

from xviv.catalog.catalog import get_catalog
from xviv.config.model import ProjectConfig
from xviv.parsers.bd_json import get_bd_core_dict

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
		fpga_ref = cfg.get_bd(bd_name).fpga_ref
	elif top_name:
		fpga_ref = cfg.get_synth(top_name=top_name).fpga_ref

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
		'set xviv_bd_leaf_ooc_synth_dir  ""'
	]

	# ---- Core variables (defaults empty) --------------------------------------------------------------------------------
	lines += [
		'set xviv_core_vlnv     ""',
		'set xviv_core_name     ""',
	]
	# =========================================================================
	# Context-specific overrides
	# =========================================================================

	synth_cfg	= cfg.get_synth(top_name=top_name, bd_name=bd_name, ip_name=ip_name)

	synth_hooks	= cfg.abs_path(synth_cfg.hooks) if synth_cfg.hooks else ""

	xdc		= cfg.resolve_globs(synth_cfg.xdc) if synth_cfg.xdc else []
	rtl		= cfg.resolve_globs(synth_cfg.rtl) if synth_cfg.rtl else []

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

		bd_leaf_ooc_synth_dir = cfg.get_bd_ooc_targets_dir(bd_name)

		lines += [
			f'set xviv_bd_name                "{bd.name}"',
			f'set xviv_bd_hooks               "{bd_hooks}"',
			f'set xviv_bd_state_tcl           "{bd.state_tcl}"',
			f'set xviv_bd_leaf_ooc_synth_dir  "{bd_leaf_ooc_synth_dir}"'
		]
	elif core_name is not None:
		catalog = get_catalog(cfg.vivado.path, [cfg.ip_repo])

		if core_vlnv:
			entry = catalog.lookup(core_vlnv)
			core_vlnv = entry.vlnv

			if not core_name:
				core_name = entry.name
		else:
			core_cfg = cfg.get_core(core_name)
			core_vlnv = catalog.lookup(core_cfg.vlnv).vlnv

		core_dir = cfg.core_dir

		lines += [
			f'set xviv_core_vlnv     "{core_vlnv}"',
			f'set xviv_core_name     "{core_name}"',
			f'set xviv_core_dir      "{core_dir}"',
		]

	if not os.path.exists(synth_hooks):
		synth_hooks = ""

	lines += [
		f'set xviv_synth_hooks            "{synth_hooks}"',
		f"set xviv_xdc_files              {_tcl_list(xdc)}",
		f"set xviv_rtl_files              {_tcl_list(rtl)}",
		f"set xviv_synth_report_synth     {int(synth_cfg.report_synth)}",
		f"set xviv_synth_report_place     {int(synth_cfg.report_place)}",
		f"set xviv_synth_report_route     {int(synth_cfg.report_route)}",
		f"set xviv_synth_generate_netlist {int(synth_cfg.generate_netlist)}",
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


def _tcl_list(items: list[str]) -> str:
	if not items:
		return "[list]"
	return "[list " + " ".join(f'"{i}"' for i in items) + "]"

# proc xviv_create_project {name} {
#     global xviv_fpga_part xviv_board_part xviv_board_repo xviv_ip_repo

#     # get_parts returns an empty list for unknown part strings.
#     # This is the earliest point we can catch a wrong part number.
#     if {[llength [get_parts $xviv_fpga_part]] == 0} {
#         xviv_die "FPGA part '$xviv_fpga_part' is not in the installed Vivado part catalog. Check [fpga] part in project.toml."
#     }

#     create_project -part $xviv_fpga_part -in_memory $name

#     if {[info exists xviv_board_part] && $xviv_board_part ne ""} {
#         if {[info exists xviv_board_repo] && $xviv_board_repo ne ""} {
#             set_param board.repoPaths [list $xviv_board_repo]
#         }
#         set_property board_part $xviv_board_part [current_project]
#     }

#     set_property ip_repo_paths [list $xviv_ip_repo] [current_project]
#     update_ip_catalog -rebuild
# }


class GenerateConfigTclBuilder:
	def __init__(self, cfg: ProjectConfig):
		self._cfg = cfg
		self.lines: list[str] = []

		self._inmemory_project_name = "xviv_in_memory"

		self.curent_project: typing.Optional[str] = None
		
		self.flag_override_bd_save_state_tcl = False

		self.fpga_part = ""

		self._init_max_threads()

	def _push(self, text: str):
		self.lines += [text]


	def _init_max_threads(self):
		self._push(f"set_param general.maxThreads {self._cfg.vivado.max_threads}")

	def _source(self, filename: str):
		self._push(f"source {filename}")
	
	def _start_gui(self):
		self._push("start_gui")

	def _create_project_inmemory(self, fpga_ref: typing.Optional[str] = None):
		#* resolves fpga part from fpga_ref
		#* set board_repo and board_part
		
		if self.curent_project is not None:
			return

		fpga = self._cfg.resolve_fpga(fpga_ref)

		if fpga.board_repo:
			self._push(f'set_param board.repoPaths { _tcl_list([fpga.board_repo]) }]')

		self._push(f"create_project -in_memory {self._inmemory_project_name}" + f" -part {fpga.part} " if fpga.part else "")

		if fpga.board_part:
			self._push(f"set_property board_part {fpga.board_part} [current_project]")

		# TODO: Throw Error when no board and fpga part is selected.

		self.curent_project = self._inmemory_project_name

	def _add_file(self, file: str, *, fileset: typing.Optional[str] = None, norecurse=False, scan_for_includes: bool = False):
		params: list[str] = []

		if scan_for_includes:
			params.append("-scan_for_includes")
		if fileset:
			params.append(f"-fileset {fileset}")
		if norecurse:
			params.append("-norecurse")

		self._push(f"add_files {file} {' '.join(params)}")

	def _override(self, call, *, pre_call = "", post_call = "", rename_prefix="_xviv_"):
		self._push(f'''
proc override_{call} {{}} {{
	rename {call} {rename_prefix}{call}

	proc {call} {{args}} {{
{pre_call}
		{rename_prefix}{call} {{*}}$args
{post_call}
	}}
}}
''')

	def _override_bd_save_state_tcl(self, bd_name: str, bd_state_tcl_file: str):
		if not bd_state_tcl_file:
			sys.exit("ERROR: bd_state_tcl_file is required")
		

		# os.makedirs(os.path.dirname(bd_state_tcl_file), exist_ok=True)
		self.flag_override_bd_save_state_tcl = True

		self._override("save_bd_design", post_call=rf'''
		set path "{bd_state_tcl_file}"
		set prefix "#{bd_name}\n\n"

		file mkdir [file dirname $path]

		write_bd_tcl -force -no_project_wrapper $path

		set f [open $path r]
		set data [read $f]
		close $f

		set start [string first "set bCheckIPsPassed" $data]
		set end [string first "save_bd_design" $data]

		if {{$start == -1 || $end == -1}} {{
			error "Could not find expected markers in state BD TCL: $path\n\
				'set bCheckIPsPassed' found: [expr {{$start != -1}}]\n\
				'save_bd_design'      found: [expr {{$end != -1}}]"
		}}

		set f [open $path w]
		puts $f [join $prefix "\n"]
		puts $f ""
		puts $f [string range $data $start [expr {{$end - 1}}]]
		close $f
		''')

	def _bd_save_design(self):
		self._push("save_bd_design")

	def _bd_validate_design(self):
		self._push("validate_bd_design")

	def _bd_refresh_addresses(self):
		self._push("delete_bd_objs [get_bd_addr_segs] [get_bd_addr_segs -excluded]")
		self._push("assign_bd_address")

	def create_bd(self, bd_name: str) -> None:
		bd_cfg = self._cfg.get_bd(bd_name)
		self._create_project_inmemory(bd_cfg.fpga_ref)

		# TODO: add a new flag --import=true flag to make this if explicit
		if os.path.exists(bd_cfg.state_tcl):
			self._push('set parentCell ""')
			
			self._source(bd_cfg.state_tcl)

			self._bd_refresh_addresses()
			self._bd_validate_design()
			self._bd_save_design()
			
			# self.cmd_generate_bd
		else:
			self._override_bd_save_state_tcl(bd_name, bd_cfg.state_tcl)
			
			self._start_gui()

	# def generate_bd(self):

	def build(self):
		return '\n'.join(self.lines) + '\n'
