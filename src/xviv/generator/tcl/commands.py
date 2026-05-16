import logging
import os
import sys
import typing

from xviv.generator.tcl.builder import ConfigTclBuilder, _tcl_list
from xviv.utils.fs import assert_file_exists, is_stale, is_stale_list


logger = logging.getLogger(__name__)


class ConfigTclCommands(ConfigTclBuilder):
	def __init__(self, cfg):
		super().__init__(cfg)

		self.__current_project_name: str | None = None


	# ------------------------------------------------------
	# Project
	# ------------------------------------------------------

	def _require_project(self, *,
		fpga_ref: str | None = None,
		exists_ok = False
	) -> bool:
		name = 'xviv_in_memory_project'

		if self.__current_project_name is not None:
			if exists_ok:
				return False

			#! RequireProject - ProjectExistsError
			raise RuntimeError(f'ERROR: attempt to create inmemory project: {name}')

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


	# ------------------------------------------------------
	# DCP
	# ------------------------------------------------------

	def open_dcp(self, dcp_file: str | None, nogui=False) -> typing.Self:
		assert_file_exists(dcp_file)

		dcp_file = os.path.abspath(dcp_file)

		self._open_checkpoint(file=dcp_file)

		if not nogui:
			self._start_gui()

		return self


	# ------------------------------------------------------
	# Waveform / Simulation
	# ------------------------------------------------------

	def waveform_reload(self) -> typing.Self:
		def __after_body(x: typing.Self):
			x._set_exec('_wcfg', lambda m: m._get_property('FILE_PATH', '[current_wave_config]'))
			x._save_wave_config('[current_wave_config]')
			# x._close_sim()
			x._close_wave_config('[current_wave_config]')
			x._open_wave_database('$xsi_sim_wdb_file')
			x.catch(lambda c: c._open_wave_config('$_wcfg'))

		self._after(300, __after_body)

		return self

	def waveform_setup(self, wdb_file: str, wcfg_file: str, top_name: str, fifo_file: str) -> typing.Self:
		if os.path.exists(wcfg_file):
			self.catch(lambda c: c._open_wave_config(wcfg_file))
		else:
			self._add_wave(top_name)
			self._save_wave_config(wcfg_file)

		self._set('xsi_sim_wdb_file', f'"{wdb_file}"')
		self._set('xsi_sim_wcfg_file', f'"{wcfg_file}"')
		self._set('xviv_fifo_path', f'"{fifo_file}"')

		self._set_exec('xviv_fifo_fh', lambda x: x._open('$xviv_fifo_path', 'r+'))
		self._fconfigure('$xviv_fifo_fh', blocking=False, buffering='line')

		def __fifo_reopen(x: typing.Self):
			x._global('xviv_fifo_fh', 'xviv_fifo_path')
			x.catch(lambda c: c._close('$xviv_fifo_fh'))
			x._set_exec('xviv_fifo_fh', lambda m: m._open('$xviv_fifo_path', 'r+'))
			x._fconfigure('$xviv_fifo_fh', blocking=False, buffering='line')
			x._fileevent('$xviv_fifo_fh', 'readable', '_fifo_handle')

		self._proc('_fifo_reopen', '', __fifo_reopen)

		def __fifo_handle(x: typing.Self):
			def __on_eof(c: typing.Self):
				c._fileevent('$xviv_fifo_fh', 'readable', '{}')
				c._call('_fifo_reopen')
				c._return()

			x._global('xviv_fifo_fh')

			x._if('[eof $xviv_fifo_fh]', __on_eof)

			x._set_exec('len', lambda m: m._gets('$xviv_fifo_fh', 'cmd'))
			x._if('$len < 0', lambda c: c._return())

			# accumulate lines until braces/brackets are balanced
			def __accumulate(c: typing.Self):
				c._set_exec('len', lambda m: m._gets('$xviv_fifo_fh', 'line'))
				c._if('$len < 0', lambda d: d._return())
				c._append('cmd', '"\\n"', '$line')

			x._while('![info complete $cmd]', __accumulate)
			x._if('$cmd eq ""', lambda c: c._return())
			x._puts('"xviv: $cmd"')
			x.catch(lambda c: c._uplevel('#0', '$cmd'), result_var='result')
			x._puts('"xviv: -> $result"')

		self._proc('_fifo_handle', '', __fifo_handle)

		self._fileevent('$xviv_fifo_fh', 'readable', '_fifo_handle')
		self._puts('"xviv: FIFO ready at $xviv_fifo_path"')

		return self


	# ------------------------------------------------------
	# JTAG / Hardware
	# ------------------------------------------------------

	def _select_fpga(self):
		self._set_exec('tlist', lambda x: x._targets())
		self._puts('"INFO: JTAG targets:\\n$tlist"')

		def __no_fpga(c: typing.Self):
			c._puts('"No FPGA target found on JTAG.\\n  $err\\n  Is the FPGA powered and connected?"')
			c._exit(1)

		self._if('[catch {targets -set -filter {name =~ "xc*"}} err]', __no_fpga)

		self._puts('"INFO: FPGA target selected"')
		self._puts_exec(lambda x: x._targets())

	def _select_mb(self):
		self._if('[catch {targets -set -filter {name =~ "MicroBlaze #0*"}} err]',
			lambda c: (
				c._puts('"No MicroBlaze target found.\\n  $err\\n  Is the FPGA programmed?"'),
				c._exit(1)
			)
		)

		self._puts('"INFO: MicroBlaze target selected"')
		self._puts_exec(lambda x: x._targets())

	def _processor_status(self):
		self._puts('"\\n=== JTAG Targets ==="')
		self._puts_exec(lambda x: x._targets())

		# non-fatal: catch only the filter, which is the only fallible part
		def __no_mb(c: typing.Self):
			c._puts('"WARN: Could not select MicroBlaze target: $err"')
			c._disconnect()
			c._exit(0)

		self._if('[catch {targets -set -filter {name =~ "MicroBlaze #0*"}} err]', __no_mb)

		self._puts('"\\n=== Processor State ==="')
		self._if('[catch {puts [state]} err]',
			lambda c: c._puts('"  (could not read state: $err)"'))

		self._puts('"\\n=== General-Purpose Registers ==="')

		def __no_regs(c: typing.Self):
			c._puts('"  (registers unavailable - processor may be running)"')
			c._puts('"  Hint: use \'xviv processor --reset\' to halt and inspect."')

		self._if('[catch {puts [rrd]} err]', __no_regs)

	def program(self, bitstream_file: str, elf_file: str | None = None) -> typing.Self:
		self._connect()

		self._select_fpga()

		if not os.path.exists(bitstream_file):
			raise RuntimeError(f'ERROR: bistream file does not exist: {bitstream_file}')

		self._fpga(bitstream_file)

		if elf_file is not None:
			if not os.path.exists(elf_file):
				raise RuntimeError(f'ERROR: elf file does not exist: {elf_file}')

			self._after(500)

			self._select_mb()
			self._rst(processor=True)
			self._dow(elf_file)
			self._con()

		self._disconnect()

		return self

	def processor_cntrl(self, reset: bool | None, status: bool | None) -> typing.Self:
		self._connect()

		if reset:
			self._select_mb()

			self._rst(processor=True)
			self._puts('INFO: processor reset')
			self._con()
			self._puts('INFO: processor running')

		if status:
			self._processor_status()

		self._disconnect()

		return self


	# ------------------------------------------------------
	# Platform / App
	# ------------------------------------------------------

	def create_platform(self, platform_name: str) -> typing.Self:
		platform_cfg = self._cfg.get_platform(platform_name)

		assert_file_exists(platform_cfg.xsa_file)

		self._file_delete(platform_cfg.dir, force=True)
		self._file_mkdir(platform_cfg.dir)

		self._set_exec('hw', lambda _: _._hsi__open_hw_design(platform_cfg.xsa_file))

		self._hsi__create_sw_design('bsp_design', proc=platform_cfg.cpu, os=platform_cfg.os)

		self._hsi__set_property_hsi__get_os('CONFIG.stdout', 'mdm_1')
		self._hsi__set_property_hsi__get_os('CONFIG.stdin', 'mdm_1')

		self._hsi__generate_bsp(dir=platform_cfg.dir)

		self._hsi__close_hw_design('$hw')

		return self


	def create_app(self, app_name: str) -> typing.Self:
		app_cfg = self._cfg.get_app(app_name)
		platform_cfg = self._cfg.get_platform(app_cfg.platform)
		
		assert_file_exists(platform_cfg.xsa_file)

		self._file_delete(app_cfg.dir, force=True)
		self._file_mkdir(app_cfg.dir)

		self._set_exec('hw', lambda _: _._hsi__open_hw_design(platform_cfg.xsa_file))

		self._hsi__generate_app(
			hw='$hw',
			os=platform_cfg.os,
			proc=platform_cfg.cpu,
			app=app_cfg.template,
			dir=app_cfg.dir
		)

		self._hsi__close_hw_design('$hw')

		return self


	# ------------------------------------------------------
	# Block Design (BD)
	# ------------------------------------------------------

	@ConfigTclBuilder._fn_def
	def _override_save_bd_design(self, bd_name: str, bd_state_tcl_file: str):
		if not bd_state_tcl_file:
			raise RuntimeError("ERROR: bd_state_tcl_file is required")

		self._proc_bd_save_tcl()
		self._override("save_bd_design", post_call=lambda x: x._call_bd_save_tcl(bd_name, bd_state_tcl_file))


	@ConfigTclBuilder._fn_def
	def _proc_bd_save_tcl(self):
		def __bd_save_tcl(x: typing.Self):
			x._set_exec('path_dirname', lambda _: _._file_dirname('$path'))
			x._file_mkdir('$path_dirname')

			x._write_bd_tcl('$path', force=True, no_project_wrapper=True)

			x._set_exec('f', lambda m: m._open('$path', 'r'))
			x._set_exec('data', lambda m: m._read_file('$f'))
			x._close('$f')

			x._set_exec('start', lambda m: m._string_first('"set bCheckIPsPassed"', '$data'))
			x._set_exec('end', lambda m: m._string_first('"save_bd_design"',      '$data'))

			x._if('$start == -1 || $end == -1', lambda c: c._error('"Could not find expected markers in state BD TCL"'))

			x._set_exec('f', lambda m: m._open('$path', 'w'))
			x._puts_exec(lambda m: m._join('$prefix', '"\\n"'), channel='$f')
			x._puts('""', channel='$f')
			x._puts_exec(lambda m: m._string_range('$data', '$start', '[expr {$end - 1}]'), channel='$f')
			x._close('$f')

		self._proc("bd_save_tcl", "path prefix", __bd_save_tcl)


	def _call_bd_save_tcl(self, bd_name, bd_state_tcl_file: str):
		self._proc_bd_save_tcl()

		self._call('bd_save_tcl', [
			f'"{bd_state_tcl_file}"', rf'"#{bd_name}\n\n"'
		])

	def _bd_refresh_addresses(self):
		self._delete_bd_objs('[get_bd_addr_segs]', '[get_bd_addr_segs -excluded]')
		self._assign_bd_address()

	def _bd_upgrade_ip_cells(self):
		self._set_exec('stale_cells', lambda x: x._get_bd_cells(hierarchical=True, filter='{TYPE == ip}'))

		def __if_stale(x: typing.Self):
			x._if('[catch {upgrade_ip $stale_cells} err]', lambda c: c._puts('"IP upgrade failed during generate_bd: $err"'))

		self._if('[llength $stale_cells] > 0', __if_stale)

	def _write_sim_fileset(self, core_name: str, filename: str):
		self._set_exec('fd', lambda x: x._open(f'"{filename}"', 'w'))

		self._foreach('f',
			iter_lambda=lambda x: x._get_files(
				of_objects=f'[get_ips {core_name}]',
				filter='{USED_IN =~ "*simulation*"}'
			),
			body_func=lambda x: x._puts_exec(lambda m: m._file_normalize('$f'), channel='$fd')
		)

		self._close('$fd')

	def create_bd(self, bd_name: str, generate: bool = True) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)
		bd_subdir = os.path.join(self._cfg.bd_dir, bd_name)
		

		self._require_project(fpga_ref=bd_cfg.fpga_ref)

		if os.path.isdir(bd_subdir):
			self._file_delete(bd_subdir, force=True)
		
		if not os.path.isdir(self._cfg.bd_dir):
			self._file_mkdir(self._cfg.bd_dir)

		self._create_bd_design(bd_name, dir=self._cfg.bd_dir)

		# TODO: add a new flag --import=true flag to make this if explicit
		if os.path.exists(bd_cfg.save_file):
			self._set('parentCell', '""')
			
			self._source(bd_cfg.save_file)
			
			def __body(c: typing.Self):
				c._puts('"ERROR: BD script failed"')
				c._exit(1)

			self._if('[llength [get_bd_cells]] == 0', __body)

			self._bd_refresh_addresses()
			self._validate_bd_design()
			self._save_bd_design()

			if generate:
				self._generate_target_get_files(bd_cfg.bd_file)
		else:
			self._override_save_bd_design(bd_name, bd_cfg.save_file)

			self._start_gui()

		return self


	def edit_bd(self, bd_name: str, nogui: bool = False) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		assert_file_exists(bd_cfg.bd_file)

		self._require_project(fpga_ref=bd_cfg.fpga_ref)
		self._read_bd(bd_cfg.bd_file)
		self._open_bd_design(bd_cfg.bd_file)

		self._override_save_bd_design(bd_name, bd_cfg.save_file)
		self._call_bd_save_tcl(bd_name, bd_cfg.save_file)

		if not nogui:
			self._start_gui()

		return self


	def generate_bd(self, bd_name: str, *,
		force: bool = True
	) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		assert_file_exists(bd_cfg.bd_file)

		if not force and not is_stale(bd_cfg.bd_file, bd_cfg.bd_wrapper_file):
			logger.info("INFO: Output products are up to date")
			self._clear()
			return self
			

		self._require_project(fpga_ref=bd_cfg.fpga_ref)

		self._read_bd(bd_cfg.bd_file)
		self._open_bd_design(bd_cfg.bd_file)

		self._bd_upgrade_ip_cells()
		self._generate_target_get_files(bd_cfg.bd_file)

		return self


	# ------------------------------------------------------
	# IP
	# ------------------------------------------------------

	def create_ip(self, ip_name: str) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_vid = f'{ip_cfg.name}_{ip_cfg.version}'.replace('.', '_')
		ip_dir = os.path.join(ip_cfg.repo, ip_vid)
		ip_component_xml_file = os.path.join(ip_dir, 'component.xml')

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_vid)
		ip_edit_project_name = f'edit_{ip_vid}'
		

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
			x._file_delete('$file', force=True)

		self._foreach('file',
			iter_lambda=lambda _: _._get_files(filter='{FILE_TYPE == Verilog}'),
			body_func=__rm_for_body
		)

		# add sources
		self._file_delete(os.path.join(ip_dir, 'hdl'), force=True)

		for s in ip_cfg.sources:
			self._add_files(s.file, scan_for_includes=True)

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
			iter_lambda=lambda x: x._ipx__get_user_parameters(of_objects=ipx_current_core),
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

			x._if('$ifc_intf eq "slave" && [string match *axi_lite* $ifc_mode]', __if_body)

		self._foreach('ifc',
			iter_lambda=lambda x: x._ipx__get_bus_interfaces(of_objects=ipx_current_core),
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

	def edit_ip(self, ip_name: str, nogui = False) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_vid = f'{ip_cfg.name}_{ip_cfg.version}'.replace('.', '_')
		ip_dir = os.path.join(ip_cfg.repo, ip_vid)
		ip_component_xml_file = os.path.join(ip_dir, 'component.xml')

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_vid)
		ip_edit_project_name = f'edit_{ip_vid}'

		assert_file_exists(ip_component_xml_file)
		

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


	# ------------------------------------------------------
	# Core
	# ------------------------------------------------------

	def create_core(self, core_name: str) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)
		
		if self._cfg.get_catalog().lookup_optional(core_cfg.vlnv) is None:
			raise RuntimeError(f'For core with name: {core_cfg.name} - IP with vlnv {core_cfg.vlnv} does not exist')

		self._require_project(fpga_ref=core_cfg.fpga_ref)

		self._create_core(core_name, dir=self._cfg.core_dir, vlnv=core_cfg.vlnv)
		self._generate_target_get_files(core_cfg.xci_file, reset=False)

		self._push(f'puts [get_files -compile_order sources -used_in simulation -of_objects [get_ips {core_name}]]')

		return self


	def edit_core(self, core_name: str, nogui: bool = False) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		self._require_project(fpga_ref=core_cfg.fpga_ref)

		assert_file_exists(core_cfg.xci_file)
		self._read_ip(core_cfg.xci_file)

		if not nogui:
			self._foreach('{key val}',
				iter_lambda=lambda _: _._start_ip_gui(f'[get_ips {core_name}]'),
				body_func=lambda _: _._set_property('CONFIG.$key', '[lindex $val 0]', f'[get_ips {core_name}]')
			)

			self._generate_target_get_files(core_cfg.xci_file, reset=False)

		return self


	def generate_core(self, core_name: str, *,
		force: bool = False
	) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		assert_file_exists(core_cfg.xci_file)

		self._require_project(fpga_ref=core_cfg.fpga_ref)

		self._read_ip(core_cfg.xci_file)
		self._upgrade_ip_get_ips(core_name)
		self._generate_target_get_files(core_cfg.xci_file)

		return self


	# ------------------------------------------------------
	# Synthesis
	# ------------------------------------------------------

	def _incremental(self, stage: str, dcp_file: str | None):
		if dcp_file:
			if not os.path.exists(dcp_file):
				logger.info(f'dcp does not exist at: {dcp_file} -> skipping incremental {stage}')
			else:
				self._read_checkpoint(dcp_file, incremental=True)
				
	def synth(self, *,
		bd: str | None = None,
		design: str | None = None,
		core: str | None = None,
	) -> typing.Self:
		synth_cfg = self._cfg.get_synth(bd_name=bd, design_name=design, core_name=core)
		
		out_files = [i for i in filter(None, [
			synth_cfg.bitstream_file,
			synth_cfg.hw_platform_xsa_file,
			synth_cfg.synth_dcp_file,
			synth_cfg.place_dcp_file,
			synth_cfg.route_dcp_file,
			synth_cfg.synth_report_timing_summary_file,
			synth_cfg.synth_report_utilization_file,
			synth_cfg.synth_report_incremental_reuse_file,
			synth_cfg.route_report_drc_file,
			synth_cfg.route_report_methodology_file,
			synth_cfg.route_report_power_file,
			synth_cfg.route_report_route_status_file,
			synth_cfg.route_report_timing_summary_file,
			synth_cfg.impl_report_incremental_reuse_file,
			synth_cfg.synth_functional_netlist_file,
			synth_cfg.synth_timing_netlist_file,
			synth_cfg.impl_functional_netlist_file,
			synth_cfg.impl_timing_netlist_file,
			synth_cfg.impl_timing_sdf_file,
			synth_cfg.synth_stub_file,
		])]

		self._require_project(fpga_ref=synth_cfg.fpga_ref)

		out_of_context_hier_dcp_map: dict[str, str] = {}

		if bd:
			bd_cfg = self._cfg.get_bd(synth_cfg.bd_name)

			assert_file_exists(bd_cfg.bd_file)
			self._add_files(bd_cfg.bd_file, scan_for_includes=True)

			assert_file_exists(bd_cfg.bd_wrapper_file)
			self._add_files(bd_cfg.bd_wrapper_file, scan_for_includes=True)

		if design:
			design_cfg = self._cfg.get_design(synth_cfg.design_name)

			for i in design_cfg.sources:
				if i.used_in_impl or i.used_in_ooc or i.used_in_synth:
					assert_file_exists(i.file)
					self._add_files(i.file, scan_for_includes=True)

		if core:
			core_cfg = self._cfg.get_core(synth_cfg.core_name)

			assert_file_exists(core_cfg.xci_file)
			self._read_ip(core_cfg.xci_file)

			#* Exit / STALE Check
			if not is_stale_list(core_cfg.xci_file, out_files):
				logger.info(f'skipping upto date synth targets: {core_cfg.name}')

				self._clear()
				return self


		for i in synth_cfg.constraints:
			assert_file_exists(i)
			self._add_files(i, fileset='constrs_1')

		self._update_compile_order(fileset='sources_1')


		if synth_cfg.out_of_context_subcores:
			for i in self._cfg.get_subcore_list(bd_name=bd, design_name=design):
				subcore_synth_cfg = self._cfg.get_synth(core_name=i.core)

				assert_file_exists(subcore_synth_cfg.synth_stub_file)
				self._add_files(subcore_synth_cfg.synth_stub_file, norecurse=True)

				self._set_property_get_files('USED_IN', '{synthesis implementation out_of_context}', subcore_synth_cfg.synth_stub_file)

				_id = i.inst_hier_path
				if bd:
					_id = f'[get_cells -filter {{IS_PRIMITIVE == 0 && PARENT == ""}}]/{_id}'

				out_of_context_hier_dcp_map[_id] = subcore_synth_cfg.synth_dcp_file

		# self._set_property_current_fileset('TOP', synth_cfg.top)
		# self._update_compile_order(fileset='constsr_1')

		#* tcl synthesis begin

		if self._require_project(exists_ok=True):
			#! Synthesis - ProjectNotCreated
			raise RuntimeError('Error: Project Not Created before calling Synthesis')

		#* synth_design
		if synth_cfg.synth_incremental:
			self._incremental('synthesis', dcp_file=synth_cfg.synth_dcp_file)

		if synth_cfg.run_synth:
			self._synth_design(
				top=synth_cfg.top,
				mode=synth_cfg.synth_mode,
				directive=synth_cfg.synth_directive,
				flatten_hierarchy=synth_cfg.synth_flatten_hierarchy,
				fsm_extraction=synth_cfg.synth_fsm_extraction
			)

		for inst_hier_path, dcp_file in out_of_context_hier_dcp_map.items():
			self._read_checkpoint(dcp_file, cell=inst_hier_path)

		if synth_cfg.synth_dcp_file:
			self._write_checkpoint(synth_cfg.synth_dcp_file, force=True)

		if synth_cfg.synth_report_timing_summary_file:
			self._report('timing_summary', file=synth_cfg.synth_report_timing_summary_file)
		if synth_cfg.synth_report_utilization_file:
			self._report('utilization', file=synth_cfg.synth_report_utilization_file, hierarchical=True)
		if synth_cfg.synth_report_incremental_reuse_file:
			self._report('incremental_reuse', file=synth_cfg.synth_report_incremental_reuse_file)

		if synth_cfg.synth_functional_netlist_file:
			self._write_verilog(synth_cfg.synth_functional_netlist_file, mode='funcsim', force=True)
		if synth_cfg.synth_timing_netlist_file:
			self._write_verilog(synth_cfg.synth_timing_netlist_file, mode='timesim', force=True, sdf_anno=True)
		if synth_cfg.synth_stub_file:
			self._write_verilog(synth_cfg.synth_stub_file, mode='synth_stub', force=True)


		# opt_design
		if synth_cfg.run_opt:
			self._opt_design(directive=synth_cfg.opt_directive)


		if synth_cfg.impl_incremental:
			self._incremental('implementation', dcp_file=synth_cfg.route_dcp_file)

		#* place_design
		if synth_cfg.run_place:
			self._place_design(directive=synth_cfg.place_directive)

		if synth_cfg.place_dcp_file:
			self._write_checkpoint(synth_cfg.place_dcp_file, force=True)


		# phys_opt
		if synth_cfg.run_phys_opt:
			self._phys_opt_design(directive=synth_cfg.phys_opt_directive)


		#* route_design
		if synth_cfg.run_route:
			self._route_design(directive=synth_cfg.route_directive)

		if synth_cfg.route_dcp_file:
			self._write_checkpoint(synth_cfg.route_dcp_file, force=True)

		if synth_cfg.route_report_drc_file:
			self._report('drc', file=synth_cfg.route_report_drc_file)
		if synth_cfg.route_report_methodology_file:
			self._report('methodology', file=synth_cfg.route_report_methodology_file)
		if synth_cfg.route_report_power_file:
			self._report('power', file=synth_cfg.route_report_power_file)
		if synth_cfg.route_report_route_status_file:
			self._report('route_status', file=synth_cfg.route_report_route_status_file)
		if synth_cfg.route_report_timing_summary_file:
			self._report('timing_summary', file=synth_cfg.route_report_timing_summary_file)
		if synth_cfg.impl_report_incremental_reuse_file:
			self._report('incremental_reuse', file=synth_cfg.impl_report_incremental_reuse_file)

		if synth_cfg.impl_functional_netlist_file:
			self._write_verilog(synth_cfg.impl_functional_netlist_file, mode='funcsim', force=True)
		if synth_cfg.impl_timing_netlist_file:
			self._write_verilog(synth_cfg.impl_timing_netlist_file, mode='timesim', force=True, sdf_anno=True)
		if synth_cfg.impl_timing_sdf_file:
			self._write_sdf(synth_cfg.impl_timing_sdf_file, mode='timesim', force=True)

		# set usr_access_value
		if synth_cfg.usr_access_value:
			self._set_property_current_design('BITSTREAM.CONFIG.USR_ACCESS', f'0x{synth_cfg.usr_access_value}')

		# bitstream
		if synth_cfg.bitstream_file:
			self._write_bitstream(synth_cfg.bitstream_file, force=True)

		# hw_platform
		if synth_cfg.hw_platform_xsa_file:
			self._write_hw_platform(synth_cfg.hw_platform_xsa_file, force=True, include_bit=True, fixed=True)

		return self