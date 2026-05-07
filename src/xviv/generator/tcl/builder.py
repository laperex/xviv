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

		self.current_project: typing.Optional[str] = None
		self.current_bd: typing.Optional[str] = None
		self.current_core: typing.Optional[str] = None

		self.__lines: list[str] = []
		self.__flags: set[str] = set()
		self.__root = True
		self.__indent = 0

		self.__read_bd_list: list[str] = []
		self.__read_ip_list: list[str] = []

	def __inherit(self, i: typing.Self) -> typing.Self:
		self.current_project = i.current_project
		self.current_bd = i.current_bd
		self.current_core = i.current_core

		self.__lines = []
		self.__flags = set(i.__flags)
		self.__root = False
		self.__indent = i.__indent + 1

		return self


	def build(self) -> typing.Optional[str]:
		if len(self.__lines):
			return '\n'.join(self.__lines) + '\n'

		return None

	def _clear(self) -> None:
		self.__lines = []


	def _push(self, text: str):
		self.__lines += [('\t' * self.__indent) + text]


	def _logging(self, text: str, severity: str = 'XVIV_INFO'):
		self._push(f"puts \"{severity}: {text}\"")


	def _create_project(self, fpga_ref: typing.Optional[str] = None, name = "xviv_in_memory"):
		#* set board_repo and board_part
		if self.current_project == name:
			#! TCLCreateProject - ProjectExistsError
			sys.exit(f"ERROR: Attempt to recreate project: {name}")

		fpga = self._cfg.get_fpga(fpga_ref)

		self._set_param('general.maxThreads', str(self._cfg.get_vivado().max_threads))

		if self._cfg.board_repo_list:
			self._push(f'set_param board.repoPaths { _tcl_list(self._cfg.board_repo_list) }')

		self._push(f"create_project -in_memory \"{name}\"" + f" -part {fpga.fpga_part} " if fpga.fpga_part else "")

		if fpga.board_part:
			self._set_property_current_project('board_part', fpga.board_part)

		# TODO: Throw Error when no board and fpga part is selected.
		if self._cfg.ip_repo_list:
			self._set_property_current_project('ip_repo_paths', _tcl_list(self._cfg.ip_repo_list))

		self.current_project = name


	def _set_current_project(self, name: str):
		self._push(f"current_project \"{name}\"")


	def _close_project(self):
		self._push("close_project")


	def _create_bd_design(self, bd_name, *,
		dir: str
	) -> None:
		if self.current_bd == bd_name:
			#! TCLCreateBd - BdExistsError
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
			#! TCLCreateCore - CoreExistsError
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
			self._push(f"file mkdir \"{dir}\"")

		self._push(f"create_ip {' '.join(params)}")

		self.current_core = core_name


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
			f"-name {name}",
			f"-component {component}",
			f"-display_name {display_name}",
			f"-parent {parent}",
		])

		self._push(f"ipx::edit_ip_in_project {' '.join(params)}")
	
	
	def _ipgui__get_pagespec(self, *,
		name: str,
		component: str
	):
		params = filter(None, [
			f"-name {name}",
			f"-component {component}",
		])

		self._push(f"ipx::edit_ip_in_project {' '.join(params)}")


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
	):
		params = filter(None, [
			f"-of_objects {of_objects}"
		])

		self._push(f"ipx::get_bus_interfaces {' '.join(params)}")


	def _ipx__get_memory_maps(self, *,
		of_objects: str,
	):
		params = filter(None, [
			f"-of_objects {of_objects}"
		])

		self._push(f"ipx::get_memory_maps {' '.join(params)}")
		

	def _ipx__update_source_project_archive(self, component: str):
		params = filter(None, [
			f"-component {component}"
		])
		self._push(f"ipx::update_source_project_archive  {' '.join(params)}")


	def _ipx__add_address_block(self, block: str, context: str):
		self._push(f"ipx::add_address_block_parameter {block} {context}")


	def _ipx__add_address_block_parameter(self, param: str, context: str):
		self._push(f"ipx::add_address_block_parameter {param} {context}")


	def _ipx__create_xgui_files(self, context: str):
		self._push(f"ipx::create_xgui_files {context}")

	def _ipx__create_xgui_files_ipx__current_core(self, interface: str):
		self._ipx__create_xgui_files('[ipx::current_core]')


	def _ipx__update_checksums(self, context: str):
		self._push(f"ipx::update_checksums {context}")

	def _ipx__update_checksums_ipx__current_core(self, interface: str):
		self._ipx__update_checksums('[ipx::current_core]')	


	def _ipx__check_integrity(self, context: str):
		self._push(f"ipx::check_integrity {context}")

	def _ipx__check_integrity_ipx__current_core(self, interface: str):
		self._ipx__check_integrity('[ipx::current_core]')	


	def _ipx__save_core(self, context: str):
		self._push(f"ipx::save_core {context}")

	def _ipx__save_core_ipx__current_core(self, interface: str):
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
		self._push(f"ipx::add_memory_map {map} {context}")

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
		fileset: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-fileset {fileset}" if fileset else None,
		])
		self._push(f"update_compile_order {' '.join(params)}")


	# read_bd
	def _read_bd(self, file) -> bool:
		if file in self.__read_bd_list:
			logger.warning(f'skipping read_bd for already loaded file: {file}')
			return False

		self.__read_bd_list.append(file)
		self._push(f"read_bd \"{file}\"")
		
		return True


	# read_ip
	def _read_ip(self, file) -> bool:
		if file in self.__read_ip_list:
			logger.warning(f'skipping read_ip for already loaded file: {file}')
			return False

		self.__read_ip_list.append(file)
		self._push(f"read_ip \"{file}\"")
		
		return True


	# add_files
	def _add_files(self, file: str, *,
		norecurse = False,
		scan_for_includes: bool = False,
		fileset: typing.Optional[str] = None,
	) -> bool:
		if file in self.__read_bd_list:
			logger.warning(f'skipping add_files for already loaded file: {file}')
			return False

		params = filter(None, [
			"-scan_for_includes"  if scan_for_includes else None,
			f"-fileset {fileset}" if fileset else None,
			"-norecurse"          if norecurse else None,
		])
		self._push(f"add_files {' '.join(params)} \"{file}\"")

		return True


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

	def _set_property_current_project(self, name: str, val: str):
		self._set_property(name, val, "[current_project]")

	def _set_property_current_fileset(self, name: str, val: str):
		self._set_property(name, val, "[current_fileset]")


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
		cell: typing.Optional[str] = None
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
		self._push(f"write_bistream {' '.join(params)} \"{file}\"")


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
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"opt_design {' '.join(params)}")


	# phys_opt_design
	def _phys_opt_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"phys_opt_design {' '.join(params)}")


	# place_design
	def _place_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"place_design {' '.join(params)}")


	# route_design
	def _route_design(self, *,
		directive: typing.Optional[str] = None
	):
		params = filter(None, [
			f"-directive \"{directive}\"" if directive else None,
		])
		self._push(f"route_design {' '.join(params)}")


	# synth_design
	def _synth_design(self, top: str, *,
		prefix: str = 'synth',
		mode: typing.Optional[str] = None,
		directive: typing.Optional[str] = None,
		flatten_hierarchy: typing.Optional[str] = None,
		fsm_extraction: typing.Optional[str] = None
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
		max_paths: typing.Optional[int] = None,
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


	def _proc(self, name: str, args: str, comm = None):
		child = type(self)(self._cfg).__inherit(self)
		comm(child)
		self._push(f'proc {name} {{{args}}} {{\n{ child.build() }}}')


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