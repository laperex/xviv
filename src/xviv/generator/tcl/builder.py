import functools
import logging
import os
import sys
import typing

from xviv.config.project import XvivConfig

logger = logging.getLogger(__name__)


class ConfigTclBuilder:
	def __init__(self, cfg: XvivConfig):
		self._cfg = cfg

		self.__lines: list[str] = []
		self.__flags: set[str] = set()
		self.__indent = 0

	def __inherit(self, i: typing.Self) -> typing.Self:
		self.__lines = []
		self.__flags = set(i.__flags)
		self.__indent = i.__indent + 1

		return self


	def build(self) -> str | None:
		if len(self.__lines):
			text = '\n'.join(self.__lines) + '\n'
			if self.__indent > 0:
				text += '\t' * (self.__indent - 1)
			return text

		return None

	def _clear(self) -> None:
		self.__lines = []


	def _push(self, text: str):
		self.__lines += [('\t' * self.__indent) + text]


	def _logging(self, text: str, severity: str = 'XVIV_INFO'):
		self._push(f"puts \"{severity}: {text}\"")

	# def _create_project(self, fpga_ref: str | None = None, name = "xviv_in_memory"):
	# 	#* set board_repo and board_part
	# 	if self.current_project == name:
	# 		#! TCLCreateProject - ProjectExistsError
	# 		sys.exit(f"ERROR: Attempt to recreate project: {name}")

	# 	fpga = self._cfg.get_fpga(fpga_ref)

	# 	self._set_param('general.maxThreads', str(self._cfg.get_vivado().max_threads))

	# 	if self._cfg.board_repo_list:
	# 		self._push(f'set_param board.repoPaths { _tcl_list(self._cfg.board_repo_list) }')

	# 	self._push(f"create_project -in_memory \"{name}\"" + f" -part {fpga.fpga_part} " if fpga.fpga_part else "")

	# 	if fpga.board_part:
	# 		self._set_property_current_project('board_part', fpga.board_part)

	# 	# TODO: Throw Error when no board and fpga part is selected.
	# 	if self._cfg.ip_repo_list:
	# 		self._set_property_current_project('ip_repo_paths', _tcl_list(self._cfg.ip_repo_list))

	# 	self.current_project = name

	def _create_project(self, name: str, *,
		part: str | None = None,
		in_memory: bool = False,
	):
		params = filter(None, [
			"-in_memory" if in_memory else None,
			f"-part {part}" if part else None,
		])

		self._push(f"create_project {' '.join(params)} {name}")


	def _current_project(self, name: str):
		self._push(f"current_project \"{name}\"")


	def _close_project(self):
		self._push("close_project")


	def _create_bd_design(self, name: str, *,
		dir: str
	) -> None:
		params = filter(None, [
			f"-dir \"{dir}\""
		])

		bd_subdir = os.path.join(dir, name)

		if os.path.isdir(bd_subdir):
			self._file_delete(bd_subdir, force=True)

		self._push(f"create_bd_design {' '.join(params)} {name}")
	


	def _create_core(self, name: str, *,
		dir: str,
		vlnv: str
	) -> None:
		params = filter(None, [
			f"-dir \"{dir}\"",
			f"-vlnv {vlnv}"        if vlnv else None,
			f"-module_name {name}" if name else None,
		])
		
		core_subdir = os.path.join(dir, name)

		if os.path.isdir(core_subdir):
			self._file_delete(core_subdir, force=True)
		
		if not os.path.isdir(dir):
			self._file_mkdir(dir)

		self._push(f"create_ip {' '.join(params)}")


	def _create_peripheral(self, *,
		vendor: str,
		library: str,
		name: str,
		version: str,
		dir: str
	):
		params = filter(None, [
			f"-dir \"{dir}\""
		])

		self._push(f"create_peripheral \"{vendor}\" \"{library}\" \"{name}\" \"{version}\" {' '.join(params)}")


	def _add_peripheral_interface_ipx__find_open_core(self, interface: str, vlnv: str, *,
		interface_mode: str,
		axi_type: str,
	):
		self._add_peripheral_interface(interface, f'[ipx::find_open_core \"{vlnv}\"]',
			interface_mode=interface_mode,
			axi_type=axi_type
		)

	def _add_peripheral_interface(self, interface: str, context: str, *,
		interface_mode: str,
		axi_type: str,
	):
		params = filter(None, [
			f"-interface_mode {interface_mode}",
			f"-axi_type {axi_type}",
		])

		self._push(f"add_peripheral_interface {interface} {' '.join(params)} {context}")


	def _generate_peripheral_ipx__find_open_core(self, vlnv: str, *,
		force: bool = False
	):
		self._generate_peripheral(f'[ipx::find_open_core \"{vlnv}\"]', force=force)

	def _generate_peripheral(self, context: str, *,
		force: bool = False
	):
		params = filter(None, [
			"-force" if force else None
		])

		self._push(f"generate_peripheral {' '.join(params)} {context}")


	def _write_peripheral_ipx__find_open_core(self, vlnv: str):
		self._write_peripheral(f'[ipx::find_open_core \"{vlnv}\"]')

	def _write_peripheral(self, context: str):
		self._push(f"write_peripheral {context}")


	# ipgui
	def _ipgui__add_param(self, *,
		name: str,
		display_name: str,
		component: str,
		parent: str
	):
		params = filter(None, [
			f"-name \"{name}\"",
			f"-display_name \"{display_name}\"",
			f"-parent {parent}",
			f"-component {component}",
		])

		self._push(f"ipgui::add_param {' '.join(params)}")


	def _ipgui__get_pagespec(self, *,
		name: str,
		component: str
	):
		params = filter(None, [
			f"-name \"{name}\"",
			f"-component {component}",
		])

		self._push(f"ipgui::get_pagespec {' '.join(params)}")


	# ipx
	def _ipx__edit_ip_in_project(self, component_xml_file: str,
		upgrade: bool,
		name: str,
		directory: str
	):
		params = filter(None, [
			f"-directory \"{directory}\"",
			f"-name \"{name}\"",
			f"-upgrade {str(upgrade).lower()}" if upgrade else None
		])

		self._push(f"ipx::edit_ip_in_project {' '.join(params)} \"{component_xml_file}\"")


	def _ipx__get_user_parameters(self, *,
		of_objects: str,
	):
		params = filter(None, [
			f"-of_objects {of_objects}"
		])

		self._push(f"ipx::get_user_parameters {' '.join(params)}")


	def _ipx__get_bus_interfaces(self, *,
		of_objects: str,
		name: str | None = None,
	):
		params = filter(None, [
			f"\"{name}\"" if name else None,
			f"-of_objects {of_objects}"
		])

		self._push(f"ipx::get_bus_interfaces {' '.join(params)}")


	def _ipx__get_memory_maps(self, *,
		of_objects: str,
		name: str | None = None,
	):
		params = filter(None, [
			f"\"{name}\"" if name else None,
			f"-of_objects {of_objects}"
		])

		self._push(f"ipx::get_memory_maps {' '.join(params)}")


	def _ipx__update_source_project_archive(self, component: str):
		params = filter(None, [
			f"-component {component}"
		])
		self._push(f"ipx::update_source_project_archive  {' '.join(params)}")


	def _ipx__add_address_block(self, block: str, context: str):
		self._push(f"ipx::add_address_block \"{block}\" {context}")


	def _ipx__add_address_block_parameter(self, param: str, context: str):
		self._push(f"ipx::add_address_block_parameter {param} {context}")


	def _ipx__create_xgui_files(self, context: str):
		self._push(f"ipx::create_xgui_files {context}")

	def _ipx__create_xgui_files_ipx__current_core(self):
		self._ipx__create_xgui_files('[ipx::current_core]')


	def _ipx__update_checksums(self, context: str):
		self._push(f"ipx::update_checksums {context}")

	def _ipx__update_checksums_ipx__current_core(self):
		self._ipx__update_checksums('[ipx::current_core]')


	def _ipx__check_integrity(self, context: str):
		self._push(f"ipx::check_integrity {context}")

	def _ipx__check_integrity_ipx__current_core(self):
		self._ipx__check_integrity('[ipx::current_core]')


	def _ipx__save_core(self, context: str):
		self._push(f"ipx::save_core {context}")

	def _ipx__save_core_ipx__current_core(self):
		self._ipx__save_core('[ipx::current_core]')


	def _ipx__remove_bus_interface(self, interface: str, context: str):
		self._push(f"ipx::remove_bus_interface {interface} {context}")

	def _ipx__remove_bus_interface_ipx__current_core(self, interface: str):
		self._ipx__remove_bus_interface(interface, '[ipx::current_core]')


	def _ipx__remove_user_parameter(self, param: str, context: str):
		self._push(f"ipx::remove_user_parameter {param} {context}")

	def _ipx__remove_user_parameter_ipx__current_core(self, param: str):
		self._ipx__remove_user_parameter(param, '[ipx::current_core]')


	def _ipx__remove_memory_map(self, map: str, context: str):
		self._push(f"ipx::remove_memory_map {map} {context}")

	def _ipx__remove_memory_map_ipx__current_core(self, map: str):
		self._ipx__remove_memory_map(map, '[ipx::current_core]')


	def _ipx__add_memory_map(self, map: str, context: str):
		self._push(f"ipx::add_memory_map \"{map}\" {context}")

	def _ipx__add_memory_map_ipx__current_core(self, map: str):
		self._ipx__add_memory_map(map, '[ipx::current_core]')


	def _ipx__infer_bus_interfaces(self, interface: str, context: str):
		self._push(f"ipx::infer_bus_interfaces {interface} {context}")

	def _ipx__infer_bus_interfaces_ipx__current_core(self, interface: str):
		self._ipx__infer_bus_interfaces(interface, '[ipx::current_core]')


	def _ipx__merge_project_changes(self, name: str, context: str):
		self._push(f"ipx::merge_project_changes {name} {context}")

	def _ipx__merge_project_changes_ipx__current_core(self, name: str):
		self._ipx__merge_project_changes(name, '[ipx::current_core]')


	# source any tcl file
	def _source(self, filename: str):
		self._push(f"source \"{filename}\"")


	# start_ip_gui:
	def _start_ip_gui(self, ip: str):
		params = filter(None, [
			f"-ip {ip}"  if ip else None,
		])
		self._push(f"start_ip_gui {' '.join(params)}")


	# start_gui: open project vivado gui
	def _start_gui(self):
		self._push("start_gui")


	def _close_gui(self):
		self._push("close_gui")


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
		fileset: str | None = None
	):
		params = filter(None, [
			f"-fileset {fileset}" if fileset else None,
		])
		self._push(f"update_compile_order {' '.join(params)}")


	# read_bd
	def _read_bd(self, file) -> None:
		self._push(f"read_bd \"{file}\"")


	# read_ip
	def _read_ip(self, file) -> None:
		self._push(f"read_ip \"{file}\"")

	# add_files
	def _add_files(self, file: str, *,
		norecurse = False,
		scan_for_includes: bool = False,
		fileset: str | None = None,
	) -> None:
		params = filter(None, [
			"-scan_for_includes"  if scan_for_includes else None,
			f"-fileset {fileset}" if fileset else None,
			"-norecurse"          if norecurse else None,
		])
		self._push(f"add_files {' '.join(params)} \"{file}\"")

	# get_files
	def _get_files(self, *,
		filter: str | None = None,
	) -> None:
		params = [
			f"-filter {filter}" if filter else None,
		]
		self._push(f"get_files {' '.join(params)}")

	# remove_files
	def remove_files(self, file: str):
		self._push(f"remove_files \"{file}\"")


	# set_param
	def _set_param(self, name: str, val: str):
		self._push(f'set_param {name} {val}')


	# set_property
	def _set_property(self, name: str, val: str, context: str):
		self._push(f'set_property {name} {val} {context}')

	def _set_property_get_files(self, name: str, val: str, file: str):
		self._set_property(name, val, f"[get_files \"{file}\"]")

	def _set_property_current_design(self, name: str, val: str):
		self._set_property(name, val, "[current_design]")
	
	def _set_property_current_core(self, name: str, val: str):
		self._set_property(name, val, "[ipx::current_core]")

	def _set_property_current_project(self, name: str, val: str):
		self._set_property(name, val, "[current_project]")

	def _set_property_current_fileset(self, name: str, val: str):
		self._set_property(name, val, "[current_fileset]")


	# get_property
	def _get_property(self, name: str, context: str):
		self._push(f'get_property {name} {context}')

	def _get_property_get_files(self, name: str, file: str):
		self._get_property(name, f"[get_files \"{file}\"]")

	def _get_property_current_design(self, name: str, val: str):
		self._get_property(name, "[current_design]")

	def _get_property_current_project(self, name: str, val: str):
		self._get_property(name, "[current_project]")

	def _get_property_current_fileset(self, name: str, val: str):
		self._get_property(name, "[current_fileset]")


	# open bd design
	def _open_bd_design(self, file: str):
		self._push(f"open_bd_design \"{file}\"")


	# generate_target
	def _generate_target_get_files(self, file: str, *,
		target="all",
		quiet=False,
		reset=True
	):
		if reset:
			self._push(f"reset_target {target} [get_files \"{file}\"]")

		params = filter(None, [
			"-quiet" if quiet else None,
		])
		self._push(f"generate_target {target} {' '.join(params)} [get_files \"{file}\"]")


	# write_checkpoint
	def _write_checkpoint(self, file: str, *,
		force: bool = False
	):
		params = filter(None, [
			"-force" if force else None,
		])
		self._push(f"write_checkpoint {' '.join(params)} \"{file}\"")


	# read_checkpoint
	def _read_checkpoint(self, file: str, *,
		incremental: bool = False,
		cell: str | None = None
	):
		params = filter(None, [
			"-incremental"  if incremental else None,
			f"-cell {cell}" if cell else None,
		])
		self._push(f"read_checkpoint {' '.join(params)} \"{file}\"")


	# open_checkpoint
	def _open_checkpoint(self, file: str):
		self._push(f"open_checkpoint \"{file}\"")


	# write_verilog
	def _write_verilog(self, file: str, *,
		mode: str,
		force: bool = False,
		sdf_anno: bool = False
	):
		params = filter(None, [
			"-force"                             if force else None,
			f"-mode {mode}"                      if mode else None,
			f"-sdf_anno {str(sdf_anno).lower()}" if sdf_anno else None,
		])
		self._push(f"write_verilog {' '.join(params)} \"{file}\"")


	# write_verilog
	def _write_bitstream(self, file: str, *,
		force: bool = False,
	):
		params = filter(None, [
			"-force" if force else None,
		])
		self._push(f"write_bitstream {' '.join(params)} \"{file}\"")


	# write_hw_platform
	def _write_hw_platform(self, file: str, *,
		force: bool = False,
		fixed: bool = False,
		include_bit: bool = False
	):
		params = filter(None, [
			"-force"       if force else None,
			"-fixed"       if fixed else None,
			"-include_bit" if include_bit else None,
		])
		self._push(f"write_hw_platform {' '.join(params)} \"{file}\"")


	# opt_design
	def _opt_design(self, *,
		directive: str | None = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"opt_design {' '.join(params)}")


	# phys_opt_design
	def _phys_opt_design(self, *,
		directive: str | None = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"phys_opt_design {' '.join(params)}")


	# place_design
	def _place_design(self, *,
		directive: str | None = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"place_design {' '.join(params)}")


	# route_design
	def _route_design(self, *,
		directive: str | None = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"route_design {' '.join(params)}")


	# synth_design
	def _synth_design(self, top: str, *,
		prefix: str = 'synth',
		mode: str | None = None,
		directive: str | None = None,
		flatten_hierarchy: str | None = None,
		fsm_extraction: str | None = None
	):
		params = filter(None, [
			f"-mode {mode}"                           if mode else None,
			f"-directive \"{directive}\""             if directive else None,
			f"-flatten_hierarchy {flatten_hierarchy}" if flatten_hierarchy else None,
			f"-fsm_extraction {fsm_extraction}"       if fsm_extraction else None,
			f"-top {top}",
			f"-name {prefix}_{top}",
		])
		self._push(f"synth_design {' '.join(params)}")


	# report
	def _report(self, report_type: str, *,
		file: str,
		max_paths: int | None = None,
		report_unconstrained: bool = False,
		warn_on_violation: bool = False,
		hierarchical: bool = False
	):
		params = filter(None, [
			f"-file \"{file}\"",
			f"-max_paths {max_paths}" if max_paths else None,
			"-report_unconstrained"   if report_unconstrained else None,
			"-warn_on_violation"      if warn_on_violation else None,
			"-hierarchical"           if hierarchical else None,
		])

		self._push(f"report_{report_type} {' '.join(params)}")


	def _save_bd_design(self):
		self._push("save_bd_design")


	def _validate_bd_design(self):
		self._push("validate_bd_design")


	def _file_delete(self, path: str, *,
		force: bool = False
	):
		params = filter(None, [
			"-force" if force else None,
		])

		self._push(f"file delete {' '.join(params)} \"{path}\"")

	def _file_dirname(self, path: str):
		self._push(f"file dirname \"{path}\"")

	def _file_mkdir(self, path: str):
		self._push(f"file mkdir \"{path}\"")
	
	def _file_normalize(self, path: str):
		self._push(f"file normalize \"{path}\"")


	def _proc(self, name: str, args: str, comm = None):
		child = type(self)(self._cfg).__inherit(self)
		comm(child)
		self._push(f'proc {name} {{{args}}} {{\n{ child.build() }}}')

	def _if(self, test_expr: str, comm = None):
		child = type(self)(self._cfg).__inherit(self)
		comm(child)
		self._push(f'if {{{test_expr}}} {{\n{ child.build() }}}')

	def _set_exec(self, name: str, value_func = None):
		child = type(self)(self._cfg).__inherit(self)
		value_func(child)

		self._set(name, f"[{(child.build() or '').strip()}]")

	def _set(self, name: str, value: str):
		self._push(f'set {name} {value}')


	def _foreach(self, args: str, iter_func = None, body_func = None):
		iterator_child = type(self)(self._cfg).__inherit(self)
		iter_func(iterator_child)

		body_child = type(self)(self._cfg).__inherit(self)
		body_func(body_child)

		self._push(f'foreach {args} [{(iterator_child.build() or '').strip()}] {{\n{body_child.build()}}}')

	def _override(self, call, *,
		pre_call = None,
		post_call = None,
		rename_prefix: str = "_xviv_",
	):
		self._push(
			f"rename {call} {rename_prefix}{call}\n"
			f"proc {call} {{args}} " + "{"
		)

		if pre_call:
			child = type(self)(self._cfg).__inherit(self)
			pre_call(child)
			self._push(f"{child.build()}".rstrip())

		self._push(f"	{rename_prefix}{call} {{*}}$args")

		if post_call:
			child = type(self)(self._cfg).__inherit(self)
			post_call(child)
			self._push(f"{child.build()}".rstrip())

		self._push("}")

	@staticmethod
	def _fn_def(fn):
		@functools.wraps(fn)
		def wrapper(self, *args, **kwargs):
			if fn.__name__ in self.__flags:
				logger.warning(f"{fn.__name__} already defined - skipping")
				return
			self.__flags.add(fn.__name__)
			return fn(self, *args, **kwargs)
		return wrapper


def _tcl_list(items: list[str]) -> str:
	if not items:
		return "[list]"
	return "[list " + " ".join(f'"{i}"' for i in items) + "]"