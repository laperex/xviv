import logging
import os
import sys
import typing

from xviv.generator.tcl.builder import ConfigTclBuilder, _tcl_list
from xviv.utils.fs import is_stale


logger = logging.getLogger(__name__)


class ConfigTclCommands(ConfigTclBuilder):
	def __init__(self, cfg):
		super().__init__(cfg)

		self.__current_project_name: str | None = None


	def _require_project(self, *,
		fpga_ref: str | None = None,
		exists_ok = False
	) -> bool:
		name = 'xviv_in_memory_project'

		if self.__current_project_name is not None:
			if exists_ok:
				return False

			#! RequireProject - ProjectExistsError
			sys.exit(f'ERROR: attempt to create inmemory project: {name}')

		self.__current_project_name = name

		fpga_cfg = self._cfg.get_fpga(fpga_ref)

		self._set_param('general.maxThreads', str(self._cfg.get_vivado().max_threads))
		
		if self._cfg.board_repo_list:
			self._set_param('board.repoPaths', _tcl_list(self._cfg.board_repo_list))

		self._create_project(name=name, in_memory=True, part=fpga_cfg.fpga_part)

		if self._cfg.ip_repo_list:
			self._set_property_current_project('ip_repo_paths', _tcl_list(self._cfg.ip_repo_list))

		if fpga_cfg.board_part:
			self._set_property_current_project('board_part', fpga_cfg.board_part)

		return True


	@ConfigTclBuilder._fn_def
	def _override_save_bd_design(self, bd_name: str, bd_state_tcl_file: str):
		if not bd_state_tcl_file:
			sys.exit("ERROR: bd_state_tcl_file is required")

		self._proc_bd_save_tcl()
		self._override("save_bd_design", post_call=lambda x: x._call_bd_save_tcl(bd_name, bd_state_tcl_file))


	@ConfigTclBuilder._fn_def
	def _proc_bd_save_tcl(self):
		def __bd_save_tcl(x: typing.Self):
			x._set_exec('path_dirname', lambda _: _._file_dirname('$path'))
			x._file_mkdir('$path_dirname')

			x._push(
				# "file mkdir [file dirname $path]\n"

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
	def create_bd(self, bd_name: str, generate: bool = True) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)
		bd_subdir = os.path.join(self._cfg.bd_dir, bd_name)

		# tcl begin

		self._require_project(fpga_ref=bd_cfg.fpga_ref)

		self._file_delete(bd_subdir, force=True)

		self._create_bd_design(bd_name, dir=self._cfg.bd_dir)

		# TODO: add a new flag --import=true flag to make this if explicit
		if os.path.exists(bd_cfg.save_file):
			self._set('parentCell', "")
			self._source(bd_cfg.save_file)
			self._bd_refresh_addresses()
			self._validate_bd_design()
			self._save_bd_design()

			if generate:
				# self.generate_bd(bd_name, check=False, force=True)
				self._generate_target_get_files(bd_cfg.bd_file)
		else:
			self._override_save_bd_design(bd_name, bd_cfg.save_file)

			self._start_gui()

		return self


	def edit_bd(self, bd_name: str, nogui: bool = False) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		if not os.path.exists(bd_cfg.bd_file):
			sys.exit(f"ERROR: BD File does not exist at path: {bd_cfg.bd_file}")

		self._require_project(fpga_ref=bd_cfg.fpga_ref)
		self._read_bd(bd_cfg.bd_file)
		self._open_bd_design(bd_cfg.bd_file)

		self._override_save_bd_design(bd_name, bd_cfg.save_file)
		self._call_bd_save_tcl(bd_name, bd_cfg.save_file)

		if not nogui:
			self._start_gui()

		return self


	def generate_bd(self, bd_name: str, *,
		check: bool = True,
		force: bool = False
	) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		if check and not os.path.exists(bd_cfg.bd_file):
			sys.exit(f"ERROR: BD File does not exist at path: {bd_cfg.bd_file}")

		if not force and not is_stale(bd_cfg.bd_file, bd_cfg.bd_wrapper_file):
			logger.info("INFO: Output products are up to date")
			return self

		# tcl begin

		self._require_project(fpga_ref=bd_cfg.fpga_ref)

		self._read_bd(bd_cfg.bd_file)
		self._open_bd_design(bd_cfg.bd_file)

		self._bd_upgrade_ip_cells()
		self._generate_target_get_files(bd_cfg.bd_file)

		return self


	def edit_ip(self, ip_name: str, nogui = False) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_vid = f'{ip_cfg.name}_{ip_cfg.version}'.replace('.', '_')
		ip_dir = os.path.join(ip_cfg.repo, ip_vid)
		ip_component_xml_file = os.path.join(ip_dir, 'component.xml')

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_vid)
		ip_edit_project_name = f'edit_{ip_vid}'

		if not os.path.exists(ip_component_xml_file):
			#! EditIp - IpNotExists
			sys.exit(f'ERROR: Ip - {ip_name}: does not exist')

		# tcl begin

		self._require_project(fpga_ref=ip_cfg.fpga_ref)

		if not nogui:
			self._start_gui()

		self._ipx__edit_ip_in_project(
			ip_component_xml_file, directory=ip_edit_project_dir, name=ip_edit_project_name, upgrade=True
		)
		self._current_project(self.__current_project_name)
		self._close_project()
		self._current_project(ip_edit_project_name)

		return self


	def create_ip(self, ip_name: str) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_vid = f'{ip_cfg.name}_{ip_cfg.version}'.replace('.', '_')
		ip_dir = os.path.join(ip_cfg.repo, ip_vid)
		ip_component_xml_file = os.path.join(ip_dir, 'component.xml')

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_vid)
		ip_edit_project_name = f'edit_{ip_vid}'

		# tcl begin

		self._require_project(fpga_ref=ip_cfg.fpga_ref)

		# _xviv_ip_scaffold
		self._create_peripheral(
			name=ip_name, vendor=ip_cfg.vendor, version=ip_cfg.version, library=ip_cfg.library, dir=ip_cfg.repo
		)
		self._add_peripheral_interface_ipx__find_open_core(
			'S00_AXI', vlnv=ip_cfg.vlnv, interface_mode='slave', axi_type='lite'
		)
		self._generate_peripheral_ipx__find_open_core(vlnv=ip_cfg.vlnv, force=True)
		self._write_peripheral_ipx__find_open_core(vlnv=ip_cfg.vlnv)

		self._ipx__edit_ip_in_project(
			ip_component_xml_file, directory=ip_edit_project_dir, name=ip_edit_project_name, upgrade=True
		)
		self._current_project(self.__current_project_name)
		self._close_project()
		self._current_project(ip_edit_project_name)

		# _xviv_ip_strip_scaffold
		for i in ['S00_AXI', 'S00_AXI_RST', 'S00_AXI_CLK']:
			self._ipx__remove_bus_interface_ipx__current_core(i)

		self._ipx__remove_memory_map_ipx__current_core('S00_AXI')
		self._ipx__remove_user_parameter_ipx__current_core('C_S00_AXI_BASEADDR')
		self._ipx__remove_user_parameter_ipx__current_core('C_S00_AXI_HIGHADDR')

		def __rm_for_body(x: typing.Self):
			x.remove_files('$file')
			x._push('file delete -force "$file"')

		self._foreach('file',
			iter_func=lambda _: _._get_files(filter='{FILE_TYPE == Verilog}'),
			body_func=__rm_for_body
		)

		# add sources
		self._push(f"file delete -force \"{os.path.join(ip_dir, 'hdl')}\"")

		for s in ip_cfg.sources:
			self._add_files(s, scan_for_includes=True)

		self._set_property_current_fileset('TOP', ip_cfg.top)

		self._update_compile_order(fileset='sources_1')

		self._ipx__merge_project_changes_ipx__current_core('ports')
		self._ipx__merge_project_changes_ipx__current_core('files')

		self._update_compile_order(fileset='sources_1')

		# _xviv_ip_infer_interfaces
		for i in ['xilinx.com:interface:axis_rtl:1.0', 'xilinx.com:interface:aximm_rtl:1.0']:
			self._ipx__infer_bus_interfaces_ipx__current_core(i)

		self._update_compile_order(fileset='sources_1')

		ipx_current_core = '[ipx::current_core]'

		# _xviv_ip_expose_params
		def __expose_params_body(x: typing.Self):
			x._set_exec('pname', lambda _: _._get_property('NAME', '$param'))

			x._set_exec('pparent', lambda _: _._ipgui__get_pagespec(
				name='Page 0',
				component=ipx_current_core
			))
			x._set_exec('widget', lambda _: _._ipgui__add_param(
				name='$pname',
				display_name='$pname',
				component=ipx_current_core,
				parent='$pparent'
			))

			x._set_property('TOOLTIP', '"Parameter: $pname"', '$widget')

		self._foreach('param',
			iter_func=lambda x: x._ipx__get_user_parameters(of_objects=ipx_current_core),
			body_func=__expose_params_body
		)

		# _xviv_ip_wire_memory_maps
		def __ip_wire_memory_maps_body(x: typing.Self):
			x._set_exec('ifc_name', lambda m: m._get_property('NAME', '$ifc'))
			x._set_exec('ifc_mode', lambda m: m._get_property('BUS_TYPE_NAME', '$ifc'))
			x._set_exec('ifc_intf', lambda m: m._get_property('INTERFACE_MODE', '$ifc'))

			def __if_body(x: typing.Self):
				x._ipx__add_memory_map_ipx__current_core('$ifc_name')
				x._set_exec('ifc_memmap', lambda m: m._ipx__get_memory_maps(name='$ifc_name', of_objects=ipx_current_core))
				x._set_exec('ifc_addr_block', lambda m: m._ipx__add_address_block('${ifc_name}_reg', '$ifc_memmap'))

				for i in ['OFFSET_HIGH_PARAM', 'OFFSET_BASE_PARAM']:
					x._ipx__add_address_block_parameter(i, '$ifc_addr_block')

				x._set_property('usage', 'register', '$ifc_addr_block')
				x._set_exec('ifc_bus_ifs', lambda m: m._ipx__get_bus_interfaces(name='$ifc_name', of_objects=ipx_current_core))
				x._set_property('slave_memory_map_ref', '$ifc_name', '$ifc_bus_ifs')

			x._if('$ifc_intf eq "slave" && [string match *axi_lite* $ifc_mode]', comm=__if_body)

		self._foreach('ifc',
			iter_func=lambda x: x._ipx__get_bus_interfaces(of_objects=ipx_current_core),
			body_func=__ip_wire_memory_maps_body
		)

		self._update_compile_order(fileset='sources_1')
		self._set_property_current_core('core_revision', f'{2}')
		self._ipx__update_source_project_archive(component=ipx_current_core)
		self._ipx__create_xgui_files_ipx__current_core()
		self._ipx__update_checksums_ipx__current_core()
		self._ipx__check_integrity_ipx__current_core()
		self._ipx__save_core_ipx__current_core()

		return self



	def create_core(self, core_name: str) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		# tcl begin

		self._require_project(fpga_ref=core_cfg.fpga_ref)

		self._create_core(core_name, dir=self._cfg.core_dir, vlnv=core_cfg.vlnv)
		self._generate_target_get_files(core_cfg.xci_file, reset=False)

		return self


	def edit_core(self, core_name: str, nogui: bool = False) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		
		if not os.path.exists(core_cfg.xci_file):
			#! EditCore - CoreNotExists
			sys.exit(f'ERROR: Core - {core_name}: does not exist')

		# tcl begin

		self._require_project(fpga_ref=core_cfg.fpga_ref)

		self._read_ip(core_cfg.xci_file)

		if not nogui:
			self._foreach('{key val}',
				iter_func=lambda _: _._start_ip_gui(f'[get_ips {core_name}]'),
				body_func=lambda _: _._set_property('CONFIG.$key', '[lindex $val 0]', f'[get_ips {core_name}]')
			)

			self._generate_target_get_files(core_cfg.xci_file, reset=False)

		return self


	# def _generate_xci(self, xci_file: str, load_xci=True) -> typing.Self:
	# 	if not self.current_project:
	# 		sys.exit(f'ERROR: current_project: {None}')

	# 	self._generate_target_get_files(xci_file, reset=False)

	# 	return self


	def synth_bd(self, bd_name: str):
		synth_cfg = self._cfg.get_synth(bd_name=bd_name)

		# tcl begin

		self._require_project(fpga_ref=synth_cfg.fpga_ref)

		bd_cfg = self._cfg.get_bd(synth_cfg.bd_name)
		self._read_bd(bd_cfg.bd_file)
		self._add_files(bd_cfg.bd_wrapper_file)

		for i in synth_cfg.constraints:
			self._add_files(i, fileset='constrs_1')
		self._update_compile_order(fileset='sources_1')

		self._set_property_current_fileset('TOP', synth_cfg.top)

		self._synthesis(
			top = synth_cfg.top,

			synth_incremental = synth_cfg.synth_incremental,

			run_synth = synth_cfg.run_synth,
			synth_dcp_file = synth_cfg.synth_dcp_file,

			run_opt = synth_cfg.run_opt,
			impl_incremental = synth_cfg.impl_incremental,
			run_place = synth_cfg.run_place,
			place_dcp_file = synth_cfg.place_dcp_file,

			run_phys_opt = synth_cfg.run_phys_opt,
			run_route = synth_cfg.run_route,

			route_dcp_file = synth_cfg.route_dcp_file,

			bitstream_file = synth_cfg.bitstream_file,
			hw_platform_xsa_file = synth_cfg.hw_platform_xsa_file,
		)

		return self


	# def synth_xci_out_of_context(self, xci_name: str, xci_file: str, *,
	# 	dcp_file: str | None = None,
	# 	stub_file: str | None = None
	# ) -> typing.Self:
	# 	if not os.path.exists(xci_file):
	# 		#! SynthXci - XciFileNotExists
	# 		sys.exit(f'ERROR: xci_file does not exist: {xci_file}')

		

	# 	self._read_ip(xci_file)

	# 	self._generate_xci(xci_file)

	# 	self.synthesis(xci_name,
	# 		run_synth=True,
	# 		synth_mode='out_of_context',
	# 		synth_dcp_file=dcp_file,
	# 		synth_stub_file=stub_file
	# 	)

	# 	return self


	def _synthesis(self, top: str, *,
		synth_incremental: bool = False,

		#* synth
		run_synth: bool = False,
		synth_directive: str = 'default',
		synth_mode: str = 'default',
		synth_flatten_hierarchy: str = 'rebuilt',
		synth_fsm_extraction: str = 'auto',

		synth_report_timing_summary_file: str | None = None,
		synth_report_utilization_file: str | None = None,
		synth_report_incremental_reuse_file: str | None = None,

		synth_dcp_file: str | None = None,
		synth_stub_file: str | None = None,
		synth_functional_netlist_file: str | None = None,
		synth_timing_netlist_file: str | None = None,


		#+ opt
		run_opt: bool = False,
		opt_directive: str = 'default',


		impl_incremental: bool = False,

		#* place
		run_place: bool = False,
		place_directive: str = 'default',
		place_dcp_file: str | None = None,


		#+ phys_opt
		run_phys_opt: bool = False,
		phys_opt_directive: str = 'default',


		#* route
		run_route: bool = False,
		route_directive: str = 'default',
		route_dcp_file: str | None = None,

		route_report_drc_file: str | None = None,
		route_report_methodology_file: str | None = None,
		route_report_power_file: str | None = None,
		route_report_route_status_file: str | None = None,
		route_report_timing_summary_file: str | None = None,

		impl_report_incremental_reuse_file: str | None = None,

		impl_functional_netlist_file: str | None = None,
		impl_timing_netlist_file: str | None = None,


		usr_access_value: int | None = None,

		bitstream_file: str | None = None,

		hw_platform_xsa_file: str | None = None,
	):
		def _incremental(stage: str, dcp_file: str | None):
			if dcp_file:
				if not os.path.exists(dcp_file):
					logger.info(f'dcp does not exist at: {dcp_file} -> skipping incremental {stage}')
				else:
					self._read_checkpoint(dcp_file, incremental=True)

		if self._require_project(exists_ok=True):
			#! Synthesis - ProjectNotCreated
			sys.exit('Error: Project Not Created before calling Synthesis')

		#* synth_design
		if synth_incremental:
			_incremental('synthesis', dcp_file=synth_dcp_file)

		if run_synth:
			self._synth_design(
				top=top,
				mode=synth_mode,
				directive=synth_directive,
				flatten_hierarchy=synth_flatten_hierarchy,
				fsm_extraction=synth_fsm_extraction
			)

		if synth_dcp_file:
			self._write_checkpoint(synth_dcp_file, force=True)

		if synth_report_timing_summary_file:
			self._report('timing_summary', file=synth_report_timing_summary_file)
		if synth_report_utilization_file:
			self._report('utilization', file=synth_report_utilization_file, hierarchical=True)
		if synth_report_incremental_reuse_file:
			self._report('incremental_reuse', file=synth_report_incremental_reuse_file)

		if synth_functional_netlist_file:
			self._write_verilog(synth_functional_netlist_file, mode='funcsim', force=True)
		if synth_timing_netlist_file:
			self._write_verilog(synth_timing_netlist_file, mode='timesim', force=True, sdf_anno=True)
		if synth_stub_file:
			self._write_verilog(synth_stub_file, mode='synth_stub', force=True)

		# opt_design
		if run_opt:
			self._opt_design(directive=opt_directive)


		if impl_incremental:
			_incremental('implementation', dcp_file=route_dcp_file)

		#* place_design
		if run_place:
			self._place_design(directive=place_directive)

		if place_dcp_file:
			self._write_checkpoint(place_dcp_file, force=True)


		# phys_opt
		if run_phys_opt:
			self._phys_opt_design(directive=phys_opt_directive)


		#* route_design
		if run_route:
			self._route_design(directive=route_directive)

		if route_dcp_file:
			self._write_checkpoint(route_dcp_file, force=True)

		if route_report_drc_file:
			self._report('drc', file=route_report_drc_file)
		if route_report_methodology_file:
			self._report('methodology', file=route_report_methodology_file)
		if route_report_power_file:
			self._report('power', file=route_report_power_file)
		if route_report_route_status_file:
			self._report('route_status', file=route_report_route_status_file)
		if route_report_timing_summary_file:
			self._report('timing_summary', file=route_report_timing_summary_file)
		if impl_report_incremental_reuse_file:
			self._report('incremental_reuse', file=impl_report_incremental_reuse_file)

		if impl_functional_netlist_file:
			self._write_verilog(impl_functional_netlist_file, mode='funcsim', force=True)
		if impl_timing_netlist_file:
			self._write_verilog(impl_timing_netlist_file, mode='timesim', force=True, sdf_anno=True)


		# set usr_access_value
		if usr_access_value:
			self._set_property_current_design('BITSTREAM.CONFIG.USR_ACCESS', f'0x{usr_access_value}')

		# bitstream
		if bitstream_file:
			self._write_bitstream(bitstream_file, force=True)

		# hw_platform
		if hw_platform_xsa_file:
			self._write_hw_platform(hw_platform_xsa_file, force=True, include_bit=True, fixed=True)

