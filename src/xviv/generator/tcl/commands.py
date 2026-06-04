import logging
import os
import typing
from enum import IntEnum

from xviv.config.params import (
	BdCreateParams,
	CoreCreateParams,
	EditParams,
	GenerateParams,
	IpCreateParams,
	OpenParams,
	ProcessorParams,
	ProgramParams,
	SynthParams,
)
from xviv.generator.tcl.builder import ConfigTclBuilder, _tcl_list
from xviv.utils import error
from xviv.utils.fs import assert_file_exists, is_stale, is_stale_list

logger = logging.getLogger(__name__)


class ConfigTclCommands(ConfigTclBuilder):
	def __init__(self, cfg):
		super().__init__(cfg)

		self.__current_project_name: str | None = None

	# ------------------------------------------------------
	# Project
	# ------------------------------------------------------

	def _require_project(self, *, fpga_ref: str | None = None, exists_ok=False) -> bool:
		name = "xviv_in_memory_project"

		if self.__current_project_name is not None:
			if exists_ok:
				return False

			raise error.InMemoryProjectAlreadyExistsError(name)

		self.__current_project_name = name

		fpga_cfg = self._cfg.get_fpga(fpga_ref)

		self._set_param("general.maxThreads", str(self._cfg.get_vivado().max_threads))

		if self._cfg.board_repo_list:
			self._set_param("board.repoPaths", _tcl_list(self._cfg.board_repo_list))

		self._create_project(name=name, in_memory=True, part=fpga_cfg.fpga_part)

		if self._cfg.ip_repo_list:
			self._set_property_current_project("ip_repo_paths", _tcl_list(self._cfg.ip_repo_list))

		if fpga_cfg.board_part:
			self._set_property_current_project("board_part", fpga_cfg.board_part)

		return True

	# ------------------------------------------------------
	# DCP
	# ------------------------------------------------------

	def open_dcp(self, dcp_file: str | None, params: OpenParams) -> typing.Self:
		assert_file_exists(dcp_file)

		dcp_file = os.path.abspath(dcp_file)

		self._open_checkpoint(file=dcp_file)

		if not params.nogui:
			self._start_gui()

		return self

	# ------------------------------------------------------
	# Waveform / Simulation
	# ------------------------------------------------------

	def waveform_reload(self) -> typing.Self:
		def __after_body(x: typing.Self):
			x._set_exec("_wcfg", lambda m: m._get_property("FILE_PATH", "[current_wave_config]"))
			x._save_wave_config("[current_wave_config]")
			# x._close_sim()
			x._close_wave_config("[current_wave_config]")
			x._open_wave_database("$xsi_sim_wdb_file")
			x.catch(lambda c: c._open_wave_config("$_wcfg"))

		self._after(300, __after_body)

		return self

	def waveform_setup(self, wdb_file: str, wcfg_file: str, top_name: str, fifo_file: str) -> typing.Self:
		if os.path.exists(wcfg_file):
			self.catch(lambda c: c._open_wave_config(wcfg_file))
		else:
			self._add_wave(top_name)
			self._save_wave_config(wcfg_file)

		self._set("xsi_sim_wdb_file", f'"{wdb_file}"')
		self._set("xsi_sim_wcfg_file", f'"{wcfg_file}"')
		self._set("xviv_fifo_path", f'"{fifo_file}"')

		self._set_exec("xviv_fifo_fh", lambda x: x._open("$xviv_fifo_path", "r+"))
		self._fconfigure("$xviv_fifo_fh", blocking=False, buffering="line")

		def __fifo_reopen(x: typing.Self):
			x._global("xviv_fifo_fh", "xviv_fifo_path")
			x.catch(lambda c: c._close("$xviv_fifo_fh"))
			x._set_exec("xviv_fifo_fh", lambda m: m._open("$xviv_fifo_path", "r+"))
			x._fconfigure("$xviv_fifo_fh", blocking=False, buffering="line")
			x._fileevent("$xviv_fifo_fh", "readable", "_fifo_handle")

		self._proc("_fifo_reopen", "", __fifo_reopen)

		def __fifo_handle(x: typing.Self):
			def __on_eof(c: typing.Self):
				c._fileevent("$xviv_fifo_fh", "readable", "{}")
				c._call("_fifo_reopen")
				c._return()

			x._global("xviv_fifo_fh")

			x._if("[eof $xviv_fifo_fh]", __on_eof)

			x._set_exec("len", lambda m: m._gets("$xviv_fifo_fh", "cmd"))
			x._if("$len < 0", lambda c: c._return())

			# accumulate lines until braces/brackets are balanced
			def __accumulate(c: typing.Self):
				c._set_exec("len", lambda m: m._gets("$xviv_fifo_fh", "line"))
				c._if("$len < 0", lambda d: d._return())
				c._append("cmd", '"\\n"', "$line")

			x._while("![info complete $cmd]", __accumulate)
			x._if('$cmd eq ""', lambda c: c._return())
			x._puts('"xviv: $cmd"')
			x.catch(lambda c: c._uplevel("#0", "$cmd"), result_var="result")
			x._puts('"xviv: -> $result"')

		self._proc("_fifo_handle", "", __fifo_handle)

		self._fileevent("$xviv_fifo_fh", "readable", "_fifo_handle")
		self._puts('"xviv: FIFO ready at $xviv_fifo_path"')

		return self

	# ------------------------------------------------------
	# JTAG / Hardware
	# ------------------------------------------------------

	def _select_target(self, filter: str):
		self._if(
			f'[catch {{targets -set -filter {{name =~ "{filter}"}}}} err]',
			lambda c: (
				c._puts(f"\"ERROR: Target '{filter}' not found.\""),
				c._puts('"Available Targets:"'),
				c._puts_exec(lambda x: x._targets()),
				c._exit(1),
			),
		)

		self._puts(f"\"INFO: Target '{filter}' selected\"")

	def _processor_status(
		self,
		*,
		processor_target_filter: str | None = None,
	):
		if processor_target_filter is None:
			raise error.ProcessorTargetFilterUnspecifiedError()

		self._select_target(processor_target_filter)

		self._puts('"\\n=== Processor State ==="')
		self._if(
			"[catch {puts [state]} err]",
			lambda c: c._puts('"  (could not read state: $err)"'),
		)

		self._puts('"\\n=== General-Purpose Registers ==="')

		def __no_regs(c: typing.Self):
			c._puts('"  (registers unavailable - processor may be running)"')
			c._puts("\"  Hint: use 'xviv processor --reset' to halt and inspect.\"")

		self._if("[catch {puts [rrd]} err]", __no_regs)

	def program(self, params: ProgramParams) -> typing.Self:
		self._connect()

		if params.bitstream_file is not None:
			if params.fpga_target_filter is None:
				raise error.FpgaTargetFilterUnspecifiedError()

			self._select_target(params.fpga_target_filter)

			if not os.path.exists(params.bitstream_file):
				raise error.InvalidPathError(params.bitstream_file, "bitstream")

			self._fpga(os.path.abspath(params.bitstream_file))

		if params.elf_file is not None:
			if not os.path.exists(params.elf_file):
				raise error.InvalidPathError(params.elf_file, "ELF")

			if params.bitstream_file is not None:
				if params.processor_reset_duration is None:
					raise error.ResetDurationUnspecifiedError()

				if params.processor_reset_duration:
					self._after(params.processor_reset_duration)

			if params.processor_target_filter is None:
				raise error.ProcessorTargetFilterUnspecifiedError()

			self._select_target(params.processor_target_filter)
			self._rst(processor=True)
			self._dow(os.path.abspath(params.elf_file))
			self._con()

		self._disconnect()

		return self

	def open_jtagterminal(self, params: ProcessorParams) -> typing.Self:
		self._connect()

		if params.processor_target_filter is None:
			raise error.ProcessorTargetFilterUnspecifiedError()

		self._select_target(params.processor_target_filter)
		self._push("jtagterminal")

		# print(self._ConfigTclBuilder__lines)

		return self

	def processor_cntrl(
		self,
		params: ProcessorParams,
	) -> typing.Self:
		self._connect()

		if params.reset:
			if params.processor_target_filter is None:
				raise error.ProcessorTargetFilterUnspecifiedError()

			self._select_target(params.processor_target_filter)

			self._rst(processor=True)
			self._puts("INFO: processor reset")
			self._con()
			self._puts("INFO: processor running")

		if params.status:
			self._processor_status(processor_target_filter=params.processor_target_filter)

		self._disconnect()

		return self

	# ------------------------------------------------------
	# Platform / App
	# ------------------------------------------------------

	def create_platform(self, platform_name: str) -> typing.Self:
		platform_cfg = self._cfg.get_platform(platform_name)

		assert_file_exists(platform_cfg.xsa)

		self._file_delete(os.path.abspath(platform_cfg.work_dir), force=True)
		self._file_mkdir(platform_cfg.work_dir)

		self._set_exec("hw", lambda _: _._hsi__open_hw_design(platform_cfg.xsa))

		self._hsi__create_sw_design("bsp_design", proc=platform_cfg.cpu, os=platform_cfg.os)

		if platform_cfg.properties:
			for key, val in platform_cfg.properties:
				self._hsi__set_property_hsi__get_os(key, val)

		self._hsi__generate_bsp(dir=platform_cfg.work_dir)

		self._hsi__close_hw_design("$hw")

		return self

	def create_app(self, app_name: str) -> typing.Self:
		app_cfg = self._cfg.get_app(app_name)
		platform_cfg = self._cfg.get_platform(app_cfg.platform)

		assert_file_exists(platform_cfg.xsa)

		self._file_delete(os.path.abspath(app_cfg.work_dir), force=True)
		self._file_mkdir(app_cfg.work_dir)

		self._set_exec("hw", lambda _: _._hsi__open_hw_design(platform_cfg.xsa))

		self._hsi__generate_app(
			hw="$hw",
			os=platform_cfg.os,
			proc=platform_cfg.cpu,
			app=app_cfg.template,
			dir=app_cfg.work_dir,
		)

		self._hsi__close_hw_design("$hw")

		return self

	# ------------------------------------------------------
	# Block Design (BD)
	# ------------------------------------------------------

	@ConfigTclBuilder._fn_def
	def _override_save_bd_design(self, bd_state_tcl_file: str):
		self._override(
			"save_bd_design",
			post_call=lambda x: (
				x._file_mkdir(os.path.dirname(bd_state_tcl_file)),
				x._write_bd_tcl(bd_state_tcl_file, force=True, no_project_wrapper=True, make_local=True),
			),
		)

	def _bd_upgrade_ip_cells(self):
		self._set_exec(
			"stale_cells",
			lambda x: x._get_bd_cells(hierarchical=True, filter="{TYPE == ip}"),
		)

		def __if_stale(x: typing.Self):
			x._if(
				"[catch {upgrade_ip $stale_cells} err]",
				lambda c: c._puts('"IP upgrade failed during generate_bd: $err"'),
			)

		self._if("[llength $stale_cells] > 0", __if_stale)

	def _write_sim_fileset(self, core_name: str, filename: str):
		self._set_exec("fd", lambda x: x._open(f'"{filename}"', "w"))

		self._foreach(
			"f",
			iter_lambda=lambda x: x._get_files(
				of_objects=f"[get_ips {core_name}]",
				filter='{USED_IN =~ "*simulation*"}',
			),
			body_func=lambda x: x._puts_exec(lambda m: m._file_normalize("$f"), channel="$fd"),
		)

		self._close("$fd")

	def create_bd(self, bd_name: str, params: BdCreateParams) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)
		bd_subdir = os.path.abspath(os.path.join(self._cfg.bd_dir, bd_name))

		self._require_project(fpga_ref=bd_cfg.fpga)

		if os.path.isdir(bd_subdir):
			self._file_delete(os.path.abspath(bd_subdir), force=True)

		if not os.path.isdir(self._cfg.bd_dir):
			self._file_mkdir(self._cfg.bd_dir)

		self._create_bd_design(bd_name, dir=self._cfg.bd_dir)

		while params.source_file:
			if isinstance(params.source_file, str):
				save_file = os.path.abspath(params.source_file)
				assert_file_exists(save_file)
			else:
				save_file = bd_cfg.save_file

				if not os.path.exists(save_file):
					break

			self._rename("create_bd_design", "_xviv_create_bd_design")
			self._rename("close_bd_design", "_xviv_close_bd_design")
			self._proc("create_bd_design", "args")
			self._proc("close_bd_design", "args")
			self._source(save_file)

			self._set_exec("_cr_bd_proc", lambda x: x._push("lindex [info procs cr_bd_*] 0"))
			self._call("$_cr_bd_proc", ['""'])

			self._rename("create_bd_design", "{}")
			self._rename("close_bd_design", "{}")
			self._rename("_xviv_create_bd_design", "create_bd_design")
			self._rename("_xviv_close_bd_design", "close_bd_design")

			def __body(c: typing.Self):
				c._puts('"ERROR: BD script failed"')
				c._exit(1)

			self._if("[llength [get_bd_cells]] == 0", __body)

			self._save_bd_design()

			self._write_bd_tcl(bd_cfg.save_file, force=True, no_project_wrapper=True, make_local=True)

			if params.generate:
				self._generate_target_get_files(bd_cfg.bd_file, force=True, reset=True)

			if params.edit:
				self.edit_bd(bd_name=bd_name, params=EditParams(nogui=params.nogui))

			return self

		if params.edit:
			self._override_save_bd_design(bd_cfg.save_file)
			self._start_gui()

		return self

	def edit_bd(self, bd_name: str, params: EditParams) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		# can be called directly after create_bd
		if self._require_project(fpga_ref=bd_cfg.fpga, exists_ok=True):
			assert_file_exists(bd_cfg.bd_file)
			self._read_bd(bd_cfg.bd_file)
			self._open_bd_design(bd_cfg.bd_file)

		self._override_save_bd_design(bd_cfg.save_file)
		self._write_bd_tcl(bd_cfg.save_file, force=True, no_project_wrapper=True, make_local=True)

		if not params.nogui:
			self._start_gui()

		return self

	def generate_bd(self, bd_name: str, params: GenerateParams) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		assert_file_exists(bd_cfg.bd_file)

		if not params.force and not is_stale(bd_cfg.bd_file, bd_cfg.bd_wrapper_file):
			logger.info("Output products are up to date")
			self._clear()
			return self

		self._require_project(fpga_ref=bd_cfg.fpga)

		self._read_bd(bd_cfg.bd_file)
		self._open_bd_design(bd_cfg.bd_file)

		self._bd_upgrade_ip_cells()
		self._generate_target_get_files(bd_cfg.bd_file, force=params.force, reset=params.reset)

		return self

	# ------------------------------------------------------
	# IP
	# ------------------------------------------------------

	def create_ip(self, ip_name: str, params: IpCreateParams) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_dir = os.path.dirname(ip_cfg.component_xml_file)

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_cfg.vid)
		ip_edit_project_name = f"edit_{ip_cfg.vid}"

		self._cfg.build_attach_ip_wrapper(ip_name=ip_name)

		self._require_project(fpga_ref=ip_cfg.fpga)

		self._create_peripheral(
			name=ip_name,
			vendor=ip_cfg.vendor,
			version=ip_cfg.version,
			library=ip_cfg.library,
			dir=ip_cfg.repo,
		)
		self._add_peripheral_interface_ipx__find_open_core("S00_AXI", vlnv=ip_cfg.vlnv, interface_mode="slave", axi_type="lite")
		self._generate_peripheral_ipx__find_open_core(vlnv=ip_cfg.vlnv, force=True)
		self._write_peripheral_ipx__find_open_core(vlnv=ip_cfg.vlnv)

		self._ipx__edit_ip_in_project(
			ip_cfg.component_xml_file,
			directory=ip_edit_project_dir,
			name=ip_edit_project_name,
			upgrade=True,
		)

		self._current_project(self.__current_project_name)
		self._close_project()
		self._current_project(ip_edit_project_name)

		for i in ["S00_AXI", "S00_AXI_RST", "S00_AXI_CLK"]:
			self._ipx__remove_bus_interface_ipx__current_core(i)

		self._ipx__remove_memory_map_ipx__current_core("S00_AXI")
		self._ipx__remove_user_parameter_ipx__current_core("C_S00_AXI_BASEADDR")
		self._ipx__remove_user_parameter_ipx__current_core("C_S00_AXI_HIGHADDR")

		def __rm_for_body(x: typing.Self):
			x.remove_files("$file")
			x._file_delete("$file", force=True)

		self._foreach(
			"file",
			iter_lambda=lambda _: _._get_files(filter="{FILE_TYPE == Verilog}"),
			body_func=__rm_for_body,
		)

		self._file_delete(os.path.abspath(os.path.join(ip_dir, "hdl")), force=True)

		for s in ip_cfg.sources:
			self._add_files(s.file, scan_for_includes=True)

		self._set_property_current_fileset("TOP", ip_cfg.top)

		self._update_compile_order(fileset="sources_1")

		self._ipx__merge_project_changes_ipx__current_core("ports")
		self._ipx__merge_project_changes_ipx__current_core("files")

		self._update_compile_order(fileset="sources_1")

		for i in [
			"xilinx.com:interface:axis_rtl:1.0",
			"xilinx.com:interface:aximm_rtl:1.0",
		]:
			self._ipx__infer_bus_interfaces_ipx__current_core(i)

		self._update_compile_order(fileset="sources_1")

		ipx_current_core = "[ipx::current_core]"

		def __expose_params_body(x: typing.Self):
			x._set_exec("pname", lambda _: _._get_property("NAME", "$param"))

			x._set_exec(
				"pparent",
				lambda _: _._ipgui__get_pagespec(name="Page 0", component=ipx_current_core),
			)
			x._set_exec(
				"widget",
				lambda _: _._ipgui__add_param(
					name="$pname",
					display_name="$pname",
					component=ipx_current_core,
					parent="$pparent",
				),
			)

			x._set_property("TOOLTIP", '"Parameter: $pname"', "$widget")

		self._foreach(
			"param",
			iter_lambda=lambda x: x._ipx__get_user_parameters(of_objects=ipx_current_core),
			body_func=__expose_params_body,
		)

		def __ip_wire_memory_maps_body(x: typing.Self):
			x._set_exec("ifc_name", lambda m: m._get_property("NAME", "$ifc"))
			x._set_exec("ifc_mode", lambda m: m._get_property("BUS_TYPE_NAME", "$ifc"))
			x._set_exec("ifc_intf", lambda m: m._get_property("INTERFACE_MODE", "$ifc"))

			def __if_body(x: typing.Self):
				x._ipx__add_memory_map_ipx__current_core("$ifc_name")
				x._set_exec(
					"ifc_memmap",
					lambda m: m._ipx__get_memory_maps(name="$ifc_name", of_objects=ipx_current_core),
				)

				x._ipx__remove_address_block("reg0", "$ifc_memmap")

				x._set_exec(
					"ifc_addr_block",
					lambda m: m._ipx__add_address_block("Reg", "$ifc_memmap"),
				)

				x._set_exec("_awaddr_pm", lambda m: m._ipx__get_port_maps("AWADDR", of_objects="$ifc"))
				x._set_exec("_awaddr_phys", lambda m: m._get_property("PHYSICAL_NAME", "$_awaddr_pm"))
				x._set_exec("_awaddr_port", lambda m: m._ipx__get_ports("$_awaddr_phys", of_objects=ipx_current_core))
				x._set_exec("_addr_width", lambda m: m._expr("[get_property SIZE_LEFT $_awaddr_port] + 1"))

				x._set_exec("_wdata_pm", lambda m: m._ipx__get_port_maps("WDATA", of_objects="$ifc"))
				x._set_exec("_wdata_phys", lambda m: m._get_property("PHYSICAL_NAME", "$_wdata_pm"))
				x._set_exec("_wdata_port", lambda m: m._ipx__get_ports("$_wdata_phys", of_objects=ipx_current_core))
				x._set_exec("_data_width", lambda m: m._expr("[get_property SIZE_LEFT $_wdata_port] + 1"))

				x._set_exec("_range", lambda m: m._expr("1 << $_addr_width"))

				x._set_property("range", "$_range", "$ifc_addr_block")
				x._set_property("width", "$_data_width", "$ifc_addr_block")
				x._set_property("usage", "register", "$ifc_addr_block")
				x._set_exec(
					"ifc_bus_ifs",
					lambda m: m._ipx__get_bus_interfaces(name="$ifc_name", of_objects=ipx_current_core),
				)
				x._set_property("slave_memory_map_ref", "$ifc_name", "$ifc_bus_ifs")

			x._if('$ifc_intf eq "slave" && [string match *aximm* $ifc_mode]', __if_body)

		self._foreach(
			"ifc",
			iter_lambda=lambda x: x._ipx__get_bus_interfaces(of_objects=ipx_current_core),
			body_func=__ip_wire_memory_maps_body,
		)

		self._update_compile_order(fileset="sources_1")
		self._set_property_current_core("core_revision", f"{2}")
		self._ipx__update_source_project_archive(component=ipx_current_core)
		self._ipx__create_xgui_files_ipx__current_core()
		self._ipx__update_checksums_ipx__current_core()
		self._ipx__check_integrity_ipx__current_core()
		self._ipx__save_core_ipx__current_core()

		if params.edit:
			self.edit_ip(ip_name=ip_name, params=EditParams(nogui=params.nogui))

		return self

	def edit_ip(self, ip_name: str, params: EditParams) -> typing.Self:
		ip_cfg = self._cfg.get_ip(ip_name)

		ip_edit_project_dir = os.path.join("/dev/shm/build", ip_cfg.vid)
		ip_edit_project_name = f"edit_{ip_cfg.vid}"

		if self._require_project(fpga_ref=ip_cfg.fpga, exists_ok=True):
			assert_file_exists(ip_cfg.component_xml_file)

		if not params.nogui:
			self._start_gui()

		self._ipx__edit_ip_in_project(
			ip_cfg.component_xml_file,
			directory=ip_edit_project_dir,
			name=ip_edit_project_name,
			upgrade=True,
		)
		self._current_project(self.__current_project_name)
		self._close_project()
		self._current_project(ip_edit_project_name)

		return self

	# ------------------------------------------------------
	# Core
	# ------------------------------------------------------

	def create_core(self, core_name: str, params: CoreCreateParams) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		if core_cfg.is_bd_core:
			return self

		if entry := self._cfg.get_catalog().lookup_optional(core_cfg.vlnv):
			core_cfg.vlnv = entry.vlnv
		else:
			raise error.CoreVlnvNotInCatalogError(core_cfg.name, core_cfg.vlnv)

		self._require_project(fpga_ref=core_cfg.fpga)

		self._create_core(core_name, dir=core_cfg.parent_dir, vlnv=core_cfg.vlnv)

		if params.generate:
			self._generate_target_get_files(core_cfg.xci_file, force=True, reset=False)

			self._push(f"puts [get_files -compile_order sources -used_in simulation -of_objects [get_ips {core_name}]]")

		if params.edit:
			self.edit_core(core_name=core_name, params=EditParams(nogui=params.nogui))

		return self

	def edit_core(self, core_name: str, params: EditParams) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		if self._require_project(fpga_ref=core_cfg.fpga, exists_ok=True):
			assert_file_exists(core_cfg.xci_file)
			self._read_ip(core_cfg.xci_file)

		if not params.nogui:
			self._foreach(
				"{key val}",
				iter_lambda=lambda _: _._start_ip_gui(f"[get_ips {core_name}]"),
				body_func=lambda _: _._set_property("CONFIG.$key", "[lindex $val 0]", f"[get_ips {core_name}]"),
			)

			self._generate_target_get_files(core_cfg.xci_file, force=True, reset=False)

		return self

	def generate_core(self, core_name: str, params: GenerateParams) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		assert_file_exists(core_cfg.xci_file)

		self._require_project(fpga_ref=core_cfg.fpga)

		self._read_ip(core_cfg.xci_file)
		self._upgrade_ip_get_ips(core_name)
		self._generate_target_get_files(core_cfg.xci_file, force=True, reset=params.reset)

		return self

	# ------------------------------------------------------
	# Synthesis
	# ------------------------------------------------------

	def _incremental(self, stage: str, dcp_file: str | None):
		if dcp_file:
			if not os.path.exists(dcp_file):
				logger.warning(f"dcp does not exist at: {dcp_file} -> skipping incremental {stage}")
			else:
				self._read_checkpoint(os.path.abspath(dcp_file), incremental=True)

	def synth(
		self,
		*,
		bd: str | None = None,
		design: str | None = None,
		core: str | None = None,
		params: SynthParams,
	) -> typing.Self:
		# -------------------------------------------------------------------------
		# Validation
		# -------------------------------------------------------------------------

		if not any([bd, design, core]):
			raise error.SynthNoIdentifierError()

		synth_cfg = self._cfg.get_synth(bd_name=bd, design_name=design, core_name=core)

		if synth_cfg.bitstream and not synth_cfg.run_route:
			raise error.SynthBitstreamRequiresRouteError()

		if synth_cfg.hw_platform and not synth_cfg.run_route:
			raise error.SynthXsaRequiresRouteError()

		# -------------------------------------------------------------------------
		# Resume stage resolution
		# -------------------------------------------------------------------------

		class SynthStage(IntEnum):
			SYNTH = 0
			OPT = 1
			PLACE = 2
			PHYS_OPT = 3
			ROUTE = 4
			WRITE = 5

		def _auto_detect_resume_stage() -> SynthStage:
			logger = logging.getLogger(__name__)

			if synth_cfg.route_dcp and os.path.exists(synth_cfg.route_dcp):
				logger.info(f"found route DCP: {synth_cfg.route_dcp}")
				return SynthStage.WRITE
			if synth_cfg.place_dcp and os.path.exists(synth_cfg.place_dcp):
				logger.info(f"found place DCP: {synth_cfg.place_dcp}")
				return SynthStage.PHYS_OPT
			if synth_cfg.synth_dcp and os.path.exists(synth_cfg.synth_dcp):
				logger.info(f"found synth DCP: {synth_cfg.synth_dcp}")
				return SynthStage.OPT
			return SynthStage.SYNTH

		_resume_map = {
			"synth": SynthStage.OPT,
			"place": SynthStage.PHYS_OPT,
			"route": SynthStage.WRITE,
		}

		if params.resume == "auto":
			start_stage = _auto_detect_resume_stage()
		elif params.resume in _resume_map:
			start_stage = _resume_map[params.resume]
		elif params.resume is not None:
			raise error.SynthResumeInvalidError(params.resume)
		else:
			start_stage = SynthStage.SYNTH

		if start_stage > SynthStage.SYNTH:
			logger.info(f"resuming from stage: {start_stage.name}")

		# -------------------------------------------------------------------------
		# Source loading / checkpoint loading
		# -------------------------------------------------------------------------
		resume_dcp: str | None = None

		out_of_context_hier_dcp_map: dict[str, str] = {}

		if start_stage >= SynthStage.WRITE:
			resume_dcp = synth_cfg.route_dcp

			if not resume_dcp or not os.path.exists(resume_dcp):
				raise error.SynthResumeDcpMissingError("route", resume_dcp)

			logger.info(f"loading route checkpoint: {resume_dcp}")
			self._open_checkpoint(resume_dcp)

		elif start_stage >= SynthStage.PHYS_OPT:
			resume_dcp = synth_cfg.place_dcp

			if not resume_dcp or not os.path.exists(resume_dcp):
				raise error.SynthResumeDcpMissingError("place", resume_dcp)

			logger.info(f"loading place checkpoint: {resume_dcp}")
			self._open_checkpoint(resume_dcp)

		elif start_stage >= SynthStage.OPT:
			resume_dcp = synth_cfg.synth_dcp

			if not resume_dcp or not os.path.exists(resume_dcp):
				raise error.SynthResumeDcpMissingError("synth", resume_dcp)

			logger.info(f"loading synth checkpoint: {resume_dcp}")
			self._open_checkpoint(resume_dcp)

		else:
			self._require_project(fpga_ref=synth_cfg.fpga)

			if bd:
				bd_cfg = self._cfg.get_bd(synth_cfg.bd)
				logger.info(f"loading BD: {bd_cfg.bd_file}")
				assert_file_exists(bd_cfg.bd_file)
				self._add_files(bd_cfg.bd_file, scan_for_includes=True)
				assert_file_exists(bd_cfg.bd_wrapper_file)
				self._add_files(bd_cfg.bd_wrapper_file, scan_for_includes=True)

			if design:
				design_cfg = self._cfg.get_design(synth_cfg.design)
				logger.info(f"loading design sources: {synth_cfg.design}")
				for i in design_cfg.sources:
					if i.used_in_impl or i.used_in_ooc or i.used_in_synth:
						assert_file_exists(i.file)
						self._add_files(i.file, scan_for_includes=True)

			if core:
				core_cfg = self._cfg.get_core(synth_cfg.core)
				logger.info(f"loading core: {core_cfg.name}")
				assert_file_exists(core_cfg.xci_file)
				self._read_ip(core_cfg.xci_file)

				if not is_stale_list(core_cfg.xci_file, [synth_cfg.synth_dcp, synth_cfg.synth_stub]):
					logger.info(f"skipping up-to-date synth targets: {core_cfg.name}")
					self._clear()
					return self

			for i in synth_cfg.constraints:
				if synth_cfg.synth_mode == "out_of_context" and i.used_in_ooc:
					assert_file_exists(i.file)
					self._add_files(i.file, fileset="constrs_1")
				elif synth_cfg.synth_mode != "out_of_context" and not i.used_in_ooc:
					if not (i.used_in_impl and not i.used_in_synth):
						assert_file_exists(i.file)
						self._add_files(i.file, fileset="constrs_1")

			self._update_compile_order(fileset="sources_1")

			if params.parallel_subcore_synth:
				for i in self._cfg.get_subcore_list(bd_name=bd, design_name=design):
					subcore_synth_cfg = self._cfg.get_synth(core_name=i.core)

					if not os.path.exists(subcore_synth_cfg.synth_stub):
						if not self._cfg.dry_run:
							raise error.OocStubMissingError(i.core, subcore_synth_cfg.synth_stub)

					self._add_files(subcore_synth_cfg.synth_stub, norecurse=True)
					self._set_property_get_files(
						"USED_IN",
						"{synthesis implementation out_of_context}",
						subcore_synth_cfg.synth_stub,
					)

					_id = i.inst_hier_path
					if bd:
						_id = f"$bd_cell_name/{_id}"

					out_of_context_hier_dcp_map[_id] = subcore_synth_cfg.synth_dcp
					logger.info(f"OOC subcore: {i.core} - {_id}")

		# -------------------------------------------------------------------------
		# Synthesis
		# -------------------------------------------------------------------------

		if start_stage > SynthStage.SYNTH:
			logger.info("skipping synth_design (resuming from checkpoint)")
		else:
			if synth_cfg.synth_incremental:
				self._incremental("synthesis", dcp_file=synth_cfg.synth_dcp)

			if not synth_cfg.run_synth:
				logger.critical("skipping synth_design (run_synth=false)")
			else:
				logger.info(f"synthes: top={synth_cfg.top}")
				self._synth_design(
					top=synth_cfg.top,
					mode=synth_cfg.synth_mode,
					directive=synth_cfg.synth_directive,
					flatten_hierarchy=synth_cfg.synth_flatten_hierarchy,
					fsm_extraction=synth_cfg.synth_fsm_extraction,
				)

			if out_of_context_hier_dcp_map:
				self._set_exec("bd_cell", lambda x: x._get_cells(filter='{IS_PRIMITIVE == 0 && PARENT == ""}'))
				self._set_exec("bd_cell_name", lambda x: x._get_property("NAME", context="$bd_cell"))

			for inst_hier_path, dcp_file in out_of_context_hier_dcp_map.items():
				self._read_checkpoint(dcp_file, cell=inst_hier_path)

			if synth_cfg.synth_dcp:
				self._write_checkpoint(synth_cfg.synth_dcp, force=True)

			if synth_cfg.synth_report_timing_summary:
				self._report("timing_summary", file=synth_cfg.synth_report_timing_summary)
			if synth_cfg.synth_report_utilization:
				self._report(
					"utilization",
					file=synth_cfg.synth_report_utilization,
					hierarchical=True,
				)
			if synth_cfg.synth_report_incremental_reuse:
				self._report(
					"incremental_reuse",
					file=synth_cfg.synth_report_incremental_reuse,
				)

			if synth_cfg.synth_functional_netlist:
				self._write_verilog(synth_cfg.synth_functional_netlist, mode="funcsim", force=True)
			if synth_cfg.synth_timing_netlist:
				self._write_verilog(
					synth_cfg.synth_timing_netlist,
					mode="timesim",
					force=True,
					sdf_anno=True,
				)
			if synth_cfg.synth_stub:
				self._write_verilog(synth_cfg.synth_stub, mode="synth_stub", force=True)

		# Load Impl Only Constraints
		for i in synth_cfg.constraints:
			if i.used_in_impl and not i.used_in_synth:
				assert_file_exists(i.file)
				self._read_xdc(i.file, unmanaged=True)

		# -------------------------------------------------------------------------
		# Opt
		# -------------------------------------------------------------------------

		if start_stage > SynthStage.OPT:
			logger.info("skipping opt_design (resuming from checkpoint)")
		elif not synth_cfg.run_opt:
			logger.warning("skipping opt_design (run_opt=false)")
		else:
			logger.info("run opt_design")
			self._opt_design(directive=synth_cfg.opt_directive)

		# -------------------------------------------------------------------------
		# Place
		# -------------------------------------------------------------------------

		if start_stage > SynthStage.PLACE:
			logger.info("skipping place_design (resuming from checkpoint)")
		else:
			if synth_cfg.impl_incremental:
				self._incremental("implementation", dcp_file=synth_cfg.route_dcp)

			if not synth_cfg.run_place:
				logger.critical("skipping place_design (run_place=false)")
			else:
				logger.info("run place_design")
				self._place_design(directive=synth_cfg.place_directive)

			if synth_cfg.place_dcp:
				self._write_checkpoint(synth_cfg.place_dcp, force=True)

		# -------------------------------------------------------------------------
		# Phys opt
		# -------------------------------------------------------------------------

		if start_stage > SynthStage.PHYS_OPT:
			logger.info("skipping phys_opt_design (resuming from checkpoint)")
		elif not synth_cfg.run_phys_opt:
			logger.warning("skipping phys_opt_design (run_phys_opt=false)")
		elif synth_cfg.run_phys_opt:
			logger.info("run phys_opt_design")
			self._phys_opt_design(directive=synth_cfg.phys_opt_directive)

		# -------------------------------------------------------------------------
		# Route
		# -------------------------------------------------------------------------

		if start_stage >= SynthStage.WRITE:
			logger.info("skipping route_design (resuming from checkpoint)")
		elif not synth_cfg.run_route:
			logger.critical("skipping route_design (run_route=false)")
		else:
			logger.info("run route_design")
			self._route_design(directive=synth_cfg.route_directive)

		if synth_cfg.route_dcp and start_stage < SynthStage.WRITE:
			self._write_checkpoint(synth_cfg.route_dcp, force=True)

		if synth_cfg.route_report_drc:
			self._report("drc", file=synth_cfg.route_report_drc)
		if synth_cfg.route_report_methodology:
			self._report("methodology", file=synth_cfg.route_report_methodology)
		if synth_cfg.route_report_power:
			self._report("power", file=synth_cfg.route_report_power)
		if synth_cfg.route_report_route_status:
			self._report("route_status", file=synth_cfg.route_report_route_status)
		if synth_cfg.route_report_timing_summary:
			self._report("timing_summary", file=synth_cfg.route_report_timing_summary)
		if synth_cfg.impl_report_incremental_reuse:
			self._report("incremental_reuse", file=synth_cfg.impl_report_incremental_reuse)

		if synth_cfg.impl_functional_netlist:
			self._write_verilog(synth_cfg.impl_functional_netlist, mode="funcsim", force=True)
		if synth_cfg.impl_timing_netlist:
			self._write_verilog(
				synth_cfg.impl_timing_netlist,
				mode="timesim",
				force=True,
				sdf_anno=True,
			)
		if synth_cfg.impl_timing_sdf:
			self._write_sdf(synth_cfg.impl_timing_sdf, mode="timesim", force=True)

		# -------------------------------------------------------------------------
		# Bitstream / XSA
		# -------------------------------------------------------------------------

		if synth_cfg.bitstream:
			if synth_cfg.usr_access_value is not None:
				self._set_property_current_design("BITSTREAM.CONFIG.USR_ACCESS", f"0x{synth_cfg.usr_access_value:08X}")

			logger.info(f"write bitstream: {synth_cfg.bitstream}")
			self._write_bitstream(synth_cfg.bitstream, force=True)

		if synth_cfg.hw_platform:
			logger.info(f"write XSA: {synth_cfg.hw_platform}")
			self._write_hw_platform(synth_cfg.hw_platform, force=True, include_bit=True, fixed=True)

		return self
