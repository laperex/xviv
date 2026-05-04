from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import sys
import typing

from xviv.catalog.catalog import get_catalog
from xviv.config.model import CoreConfig, ProjectConfig
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


class ConfigTclBuilder:
	def __init__(self, cfg: ProjectConfig):
		self._cfg = cfg
		self.lines: list[str] = []

		self.current_project: typing.Optional[str] = None
		self.current_bd: typing.Optional[str] = None
		self.current_core: typing.Optional[str] = None

		self.flag_override_bd_save_state_tcl = False
		self.flag_proc_save_bd_tcl = False

		self._run_tcl = False
		self.root = True
		
		self.indent = 0

		self._initialize()

	def _proc_inherit(self, i: typing.Self) -> typing.Self:
		self.current_project = i.current_project
		self.current_bd = i.current_bd
		self.current_core = i.current_core
		self.flag_override_bd_save_state_tcl = i.flag_override_bd_save_state_tcl
		self.flag_proc_save_bd_tcl = i.flag_proc_save_bd_tcl

		self.lines = []
		self._run_tcl = True

		self.root = False
		
		self.indent = i.indent + 1

		return self

	def _push(self, text: str):
		self.lines += [('\t' * self.indent) + text]

	def _info(self, text: str, severity: str = 'XVIV_INFO'):
		self._push(f"puts \"{severity}: {text}\"")

	def _initialize(self):
		self._init_max_threads()


	def _init_max_threads(self):
		self._push(f"set_param general.maxThreads {self._cfg.vivado.max_threads}")


	def _create_project(self, fpga_ref: typing.Optional[str] = None, name = "xviv_in_memory"):
		#* resolves fpga part from fpga_ref
		#* set board_repo and board_part
		if self.current_project == name:
			sys.exit(f"ERROR: Attempt to recreate project: {name}")

		fpga = self._cfg.resolve_fpga(fpga_ref)

		if fpga.board_repo:
			self._push(f'set_param board.repoPaths { _tcl_list([fpga.board_repo]) }')

		self._push(f"create_project -in_memory {name}" + f" -part {fpga.part} " if fpga.part else "")

		if fpga.board_part:
			self._set_property_current_project('board_part', fpga.board_part)

		# TODO: Throw Error when no board and fpga part is selected.

		if self._cfg.ip_repo:
			self._set_property_current_project('ip_repo_paths', _tcl_list([self._cfg.ip_repo]))

		self.current_project = name


	def _create_bd_design(self, bd_name, *,
		dir: str
	) -> None:
		if self.current_bd == bd_name:
			sys.exit(f"ERROR: Attempt to recreate BD: {bd_name}")

		params = filter(None, [
			f"-dir \"{dir}\""
		])

		bd_subdir = os.path.join(dir, bd_name)

		if os.path.isdir(bd_subdir):
			self._push(f"file delete -force \"{bd_subdir}\"")

		self._push(f"create_bd_design {' '.join(params)} {bd_name}")

		self.current_bd = bd_name


	def _create_core(self, core_name, *,
		dir: str,
		vlnv: str
	) -> None:
		if self.current_core == core_name:
			sys.exit(f"ERROR: attempt to recreate core: {core_name}")

		params = filter(None, [
			f"-dir \"{dir}\"",
			f"-vlnv {vlnv}"             if vlnv else None,
			f"-module_name {core_name}" if core_name else None,
		])

		core_subdir = os.path.join(dir, core_name)

		if os.path.isdir(core_subdir):
			self._push(f"file delete -force \"{core_subdir}\"")

		if not os.path.isdir(dir):
			self._push(f"file mkdir \"{core_subdir}\"")

		self._push(f"create_ip {' '.join(params)}")

		self.current_core = core_name


	# source any tcl file
	def _source(self, filename: str):
		self._push(f"source \"{filename}\"")


	# start_gui: open project vivado gui
	def _start_gui(self):
		self._push("start_gui")


	# update_ip_catalog
	def _update_ip_catalog(self, *,
		rebuild: bool = False
	):
		params = filter(None, [
			"-rebuild" if rebuild else None
		])

		self._push(f"update_ip_catalog {' '.join(params)}")


	# update_compile_order
	def _update_compile_order(self, *,
		fileset: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-fileset {fileset}" if fileset else None,
		])
		self._push(f"update_compile_order {' '.join(params)}")


	# read_bd
	def _read_bd(self, filename):
		self._push(f'read_bd "{filename}"')


	# read_ip
	def _read_ip(self, filename):
		self._push(f'read_ip "{filename}"')


	# add_files
	def _add_files(self, file: str, *,
		norecurse=False,
		scan_for_includes: bool = False,
		fileset: typing.Optional[str] = None,
	):
		params = filter(None, [
			"-scan_for_includes"  if scan_for_includes else None,
			f"-fileset {fileset}" if fileset else None,
			"-norecurse"          if norecurse else None,
		])
		self._push(f"add_files {' '.join(params)} {file}")


	# set_property
	def _set_property(self, name: str, val: str, context: str):
		self._push(f'set_property {name} {val} {context}')

	def _set_property_get_files(self, name: str, val: str, file: str):
		self._set_property(name, val, f'[get_files "{file}"]')

	def _set_property_current_design(self, name: str, val: str):
		self._set_property(name, val, '[current_design]')

	def _set_property_current_project(self, name: str, val: str):
		self._set_property(name, val, '[current_project]')

	def _set_property_current_fileset(self, name: str, val: str):
		self._set_property(name, val, '[current_fileset]')


	# open bd design
	def _open_bd_design(self, bd_file):
		self._push(f'open_bd_design "{bd_file}"')


	# generate_target
	def _generate_target_get_files(self, file: str, *,
		target="all",
		quiet=False,
		reset=True
	):
		if reset:
			self._push(f'reset_target {target} [get_files "{file}"]')

		params = filter(None, [
			"-quiet" if quiet else None,
		])
		self._push(f'generate_target {target} {' '.join(params)} [get_files "{file}"]')


	# write_checkpoint
	def _write_checkpoint(self, filepath, *,
		force: bool = False
	):
		params = filter(None, [
			"-force" if force else None,
		])
		self._push(f"write_checkpoint {' '.join(params)} {filepath}")


	# read_checkpoint
	def _read_checkpoint(self, filepath, *,
		incremental: bool = False,
		cell: typing.Optional[str] = None
	):
		params = filter(None, [
			"-incremental"  if incremental else None,
			f"-cell {cell}" if cell else None,
		])
		self._push(f"read_checkpoint {' '.join(params)} {filepath}")


	# write_verilog
	def _write_verilog(self, filepath, *,
		mode: str,
		force: bool = False,
		sdf_anno: typing.Optional[bool] = None
	):
		params = filter(None, [
			"-force"                             if force else None,
			f"-mode {mode}"                      if mode else None,
			f"-sdf_anno {str(sdf_anno).lower()}" if sdf_anno is not None else None,
		])
		self._push(f"write_verilog {' '.join(params)} {filepath}")


	# write_verilog
	def _write_bitstream(self, filepath, *,
		force: bool = False,
	):
		params = filter(None, [
			"-force" if force else None,
		])
		self._push(f"write_bistream {' '.join(params)} {filepath}")


	# write_hw_platform
	def _write_hw_platform(self, filepath, *,
		force: bool = False,
		fixed: bool = False,
		include_bit: bool = False
	):
		params = filter(None, [
			"-force"       if force else None,
			"-fixed"       if fixed else None,
			"-include_bit" if include_bit else None,
		])
		self._push(f"write_hw_platform {' '.join(params)} {filepath}")


	# opt_design
	def _opt_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive {directive}" if directive else None,
		])
		self._push(f"opt_design {' '.join(params)}")


	# phys_opt_design
	def _phys_opt_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive {directive}" if directive else None,
		])
		self._push(f"phys_opt_design {' '.join(params)}")


	# place_design
	def _place_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive {directive}" if directive else None,
		])
		self._push(f"place_design {' '.join(params)}")


	# route_design
	def _route_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive {directive}" if directive else None,
		])
		self._push(f"route_design {' '.join(params)}")


	# synth_design
	def _synth_design(self, prefix: str, *,
		top: str,
		mode: typing.Optional[str] = None,
		directive: typing.Optional[str] = None,
		flatten_hierarchy: typing.Optional[str] = None,
		fsm_extraction: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-mode {mode}"                           if mode else None,
			f"-directive {directive}"                 if directive else None,
			f"-flatten_hierarchy {flatten_hierarchy}" if flatten_hierarchy else None,
			f"-fsm_extraction {fsm_extraction}"       if fsm_extraction else None,
			f"-top {top}",
			f"-name {prefix}_{top}",
		])
		self._push(f"synth_design {' '.join(params)}")


	# report
	def _report(self, report_type, *,
		dir: str,
		max_paths: typing.Optional[int] = None,
		report_unconstrained: typing.Optional[bool] = None,
		warn_on_violation: typing.Optional[bool] = None
	):
		params = filter(None, [
			f"-max_paths {max_paths}"                       if max_paths else None,
			f"-report_unconstrained {report_unconstrained}" if report_unconstrained else None,
			f"-warn_on_violation {warn_on_violation}"       if warn_on_violation else None,
			f"-file {os.path.join(dir, report_type)}"       if dir else None,
		])
		
		self._push(f"report_{report_type} {' '.join(params)}")
		


	def _save_bd_design(self):
		self._push("save_bd_design")

	def _validate_bd_design(self):
		self._push("validate_bd_design")


	# ------------------------------------------------------
	# PROCS
	# ------------------------------------------------------
	def _proc(self, name, args, comm):
		child = ConfigTclBuilder(self._cfg)._proc_inherit(self)
		comm(child)
		self._push(f'proc {name} {{{args}}} {{\n{ child.build() }}}')

	# ------------------------------------------------------
	# OVERRIDES
	# ------------------------------------------------------
	def _override(self,
		call,
		*,
		pre_call = None,
		post_call = None,
		rename_prefix: str = "_xviv_",
	):
		self._push(
			f"rename {call} {rename_prefix}{call}\n"
			f"proc {call} {{args}} " + "{"
		)

		if pre_call:
			child = ConfigTclBuilder(self._cfg)._proc_inherit(self)
			pre_call(child)
			self._push(f"{child.build()}".rstrip())

		self._push(f"	{rename_prefix}{call} {{*}}$args")

		if post_call:
			child = ConfigTclBuilder(self._cfg)._proc_inherit(self)
			post_call(child)
			self._push(f"{child.build()}".rstrip())

		self._push("}")



	def build(self) -> typing.Optional[str]:
		if self._run_tcl:
			return '\n'.join(self.lines) + '\n'

		return None
	
	# I WANT EVERYTHING UNDER THIS TO BE IN A SEPERATE CLASS. HOW ? with minimal changes. use inheritance or smth

	def _override_save_bd_design(self, bd_name: str, bd_state_tcl_file: str):
		if self.flag_override_bd_save_state_tcl:
			return

		if not bd_state_tcl_file:
			sys.exit("ERROR: bd_state_tcl_file is required")

		self.flag_override_bd_save_state_tcl = True

		self._proc_bd_save_tcl()
		self._override("save_bd_design", post_call=lambda x: x._call_bd_save_tcl(bd_name, bd_state_tcl_file))


	def _proc_bd_save_tcl(self):
		if self.flag_proc_save_bd_tcl:
			return

		self.flag_proc_save_bd_tcl = True

		def __bd_save_tcl(x: typing.Self):
			x._push(
				"file mkdir [file dirname $path]\n"

				"\twrite_bd_tcl -force -no_project_wrapper $path\n"

				"\tset f [open $path r]\n"
				"\tset data [read $f]\n"
				"\tclose $f\n"

				"\tset start [string first \"set bCheckIPsPassed\" $data]\n"
				"\tset end [string first \"save_bd_design\" $data]\n"

				"\tif {$start == -1 || $end == -1} {\n"
				"\t	error \"Could not find expected markers in state BD TCL\"\n"
				"\t}\n"

				"\tset f [open $path w]\n"
				"\tputs $f [join $prefix \"\\n\"]\n"
				"\tputs $f \"\"\n"
				"\tputs $f [string range $data $start [expr {$end - 1}]]\n"
				"\tclose $f"
			)

		self._proc("bd_save_tcl", "path prefix", __bd_save_tcl)


	def _call_bd_save_tcl(self, bd_name, bd_state_tcl_file: str):
		self._proc_bd_save_tcl()

		self._push(rf'bd_save_tcl "{bd_state_tcl_file}" "#{bd_name}\n\n"')


	# ------------------------------------------------------
	# BD Functions
	# ------------------------------------------------------

	def _bd_refresh_addresses(self):
		self._push("delete_bd_objs [get_bd_addr_segs] [get_bd_addr_segs -excluded]")
		self._push("assign_bd_address")

	def _bd_upgrade_ip_cells(self):
		self._push(
			"set stale_cells [get_bd_cells -hierarchical -filter {TYPE == ip}]\n"
			"if {[llength $stale_cells] > 0} {\n"
			"	if {[catch {upgrade_ip $stale_cells} err]} {\n"
			"		puts \"IP upgrade failed during generate_bd: $err\";\n"
			"	}\n"
			"}"
		)

	def _write_sim_fileset(self, core_name: str, filename: str):
		self._push(
			f"set fd [open \"{filename}\" w]\n"
			f"foreach f [get_files -of_objects [get_ips {core_name}] -filter {{USED_IN =~ \"*simulation*\"}}] {{\n"
			"	puts $fd [file normalize $f]\n"
			"}\n"
			"close $fd\n"
		)

	# ------------------------------------------------------
	# functions
	# ------------------------------------------------------
	def create_bd(self, bd_name: str, generate=True) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)
		bd_subdir = os.path.join(self._cfg.bd_dir, bd_name)

		# tcl begin

		self._create_project(bd_cfg.fpga_ref)

		self._push(f"file delete -force \"{bd_subdir}\"")

		self._create_bd_design(bd_name, dir=self._cfg.bd_dir)

		# TODO: add a new flag --import=true flag to make this if explicit
		if os.path.exists(bd_cfg.state_tcl):
			self._push('set parentCell ""')

			self._source(bd_cfg.state_tcl)
			self._bd_refresh_addresses()
			self._validate_bd_design()
			self._save_bd_design()

			if generate:
				self.generate_bd(bd_name, bd_file_exist_check=False, force=True)
		else:
			self._override_save_bd_design(bd_name, bd_cfg.state_tcl)

			self._start_gui()

		self._run_tcl = True

		return self


	def edit_bd(self, bd_name: str, nogui=False) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)
		bd_file = os.path.join(self._cfg.bd_dir, bd_name, f"{bd_name}.bd")

		if not os.path.exists(bd_file):
			sys.exit(f"ERROR: BD File does not exist at path: {bd_file}")

		# tcl begin

		if self.current_project is None:
			self._create_project(bd_cfg.fpga_ref)

		if self.current_bd != bd_name:
			self._read_bd(bd_file)
			self._open_bd_design(bd_file)

			self.current_bd = bd_name

		# if not os.path.exists(bd_cfg.state_tcl):
		# 	self._bd_save_tcl(bd_name, bd_cfg.state_tcl)
		self._override_save_bd_design(bd_name, bd_cfg.state_tcl)

		self._call_bd_save_tcl(bd_name, bd_cfg.state_tcl)

		if not nogui:
			self._start_gui()

		self._run_tcl = True

		return self


	def generate_bd(self, bd_name: str, bd_file_exist_check: bool = True, force: bool = False) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		bd_file = os.path.join(self._cfg.bd_dir, bd_name, f"{bd_name}.bd")
		bd_wrapper = os.path.join(self._cfg.bd_dir, bd_name, 'hdl', f"{bd_name}_wrapper.v")

		if bd_file_exist_check and not os.path.exists(bd_file):
			sys.exit(f"ERROR: BD File does not exist at path: {bd_file}")

		if not force and os.path.exists(bd_wrapper) and os.path.exists(bd_file):
			if os.path.getmtime(bd_wrapper) > os.path.getmtime(bd_file):
				logger.info("INFO: Output products are up to date")

				return self

		# tcl begin

		if self.current_project is None:
			self._create_project(bd_cfg.fpga_ref)

		if self.current_bd != bd_name:
			self._read_bd(bd_file)
			self._open_bd_design(bd_file)

			self.current_bd = bd_name

		self._bd_upgrade_ip_cells()
		self._generate_target_get_files(bd_file)

		self._run_tcl = True

		return self

	def create_core(self, core_name: str, nogui = True) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		# tcl begin

		if self.current_project is None:
			self._create_project(None)

		self._create_core(core_name, dir=self._cfg.core_dir, vlnv=self._cfg.get_catalog().lookup(core_cfg.vlnv).vlnv)

		self._run_tcl = True

		if nogui:
			self.generate_core(core_name)

		return self

	def generate_core(self, core_name: str) -> typing.Self:
		xci_file = os.path.join(self._cfg.core_dir, core_name, f"{core_name}.xci")
		sim_fileset_path = os.path.join(self._cfg.core_dir, core_name, f'{core_name}.sim.f')

		# tcl begin

		if self.current_project is None:
			self._create_project(None)

		if self.current_core != core_name:
			self._read_ip(xci_file)

			self.current_core = core_name

		self._generate_target_get_files(xci_file, reset=False)

		# self._write_sim_fileset(core_name, sim_fileset_path)

		self._run_tcl = True

		return self

	def edit_core(self, core_name: str, nogui=False) -> typing.Self:
		xci_file = os.path.join(self._cfg.core_dir, core_name, f"{core_name}.xci")

		# tcl begin

		if self.current_project is None:
			self._create_project(None)

		if self.current_core != core_name:
			self._read_ip(xci_file)

			self.current_core = core_name

		if not nogui:
			self._push(
				f'foreach {{key val}} [start_ip_gui -ip [get_ips {core_name}]] {{\n'
				'	puts "INFO: CONFIG.$key = [lindex $val 0]"\n'
				f'	set_property CONFIG.$key [lindex $val 0] [get_ips {core_name}]\n'
				'}'
			)

			self.generate_core(core_name)

		self._run_tcl = True

		return self

	def synth_core(self, core_name: str, xci_file: str, target_dir: typing.Optional[str]=None, out_of_context=True):
		if target_dir is None:
			return None

		dcp_file = os.path.join(target_dir, f"{core_name}.dcp")
		stub_file = os.path.join(target_dir, f"{core_name}.v")

		if self.current_project is None:
			self._create_project(None)

		if self.current_core != core_name:
			self._read_ip(xci_file)

			self.current_core = core_name
		
			

		if os.path.exists(dcp_file) or os.path.exists(stub_file):
			pass

		# self._push(f"set_property TOP {xci_name} [current_fileset]")
		# self._update_compile_order(fileset='sources_1')
		# set_property TOP $xci_name [current_fileset]
		# update_compile_order -fileset sources_1
		# file mkdir $target_dir
		# synth_design -mode out_of_context -top $xci_name -name "ooc_$xci_name"
		# write_checkpoint -force $dcp_path
		# write_verilog -force -mode synth_stub $stub_path

