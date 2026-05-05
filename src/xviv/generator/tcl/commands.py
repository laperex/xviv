import logging
import os
import sys
import typing

from xviv.generator.tcl.builder import ConfigTclBuilder
from xviv.utils.fs import is_stale


logger = logging.getLogger(__name__)


class ConfigTclCommands(ConfigTclBuilder):
	@ConfigTclBuilder._fn_def
	def _override_save_bd_design(self, bd_name: str, bd_state_tcl_file: str):
		if not bd_state_tcl_file:
			sys.exit("ERROR: bd_state_tcl_file is required")

		self._proc_bd_save_tcl()
		self._override("save_bd_design", post_call=lambda x: x._call_bd_save_tcl(bd_name, bd_state_tcl_file))


	@ConfigTclBuilder._fn_def
	def _proc_bd_save_tcl(self):
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


		return self


	def generate_bd(self, bd_name: str, bd_file_exist_check: bool = True, force: bool = False) -> typing.Self:
		bd_cfg = self._cfg.get_bd(bd_name)

		bd_file = os.path.join(self._cfg.bd_dir, bd_name, f"{bd_name}.bd")
		bd_wrapper = os.path.join(self._cfg.bd_dir, bd_name, 'hdl', f"{bd_name}_wrapper.v")

		if bd_file_exist_check and not os.path.exists(bd_file):
			sys.exit(f"ERROR: BD File does not exist at path: {bd_file}")

		if not is_stale(bd_file, bd_wrapper):
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

		return self


	def create_core(self, core_name: str, nogui = True) -> typing.Self:
		core_cfg = self._cfg.get_core(core_name)

		# tcl begin

		if self.current_project is None:
			self._create_project(None)

		self._create_core(core_name, dir=self._cfg.core_dir, vlnv=self._cfg.get_catalog().lookup(core_cfg.vlnv).vlnv)


		if nogui:
			self.generate_core(core_name)

		return self


	def generate_core(self, core_name: str) -> typing.Self:
		xci_file = os.path.join(self._cfg.core_dir, core_name, f"{core_name}.xci")
		# sim_fileset_path = os.path.join(self._cfg.core_dir, core_name, f'{core_name}.sim.f')

		# tcl begin

		if self.current_project is None:
			self._create_project(None)

		if self.current_core != core_name:
			self._read_ip(xci_file)

			self.current_core = core_name

		self._generate_target_get_files(xci_file, reset=False)

		# self._write_sim_fileset(core_name, sim_fileset_path)

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

		return self


	# def synth_core(self, core_name: str, xci_file: str, target_dir: typing.Optional[str]=None, out_of_context=True):
	# 	if target_dir is None:
	# 		return None

	# 	dcp_file = os.path.join(target_dir, f"{core_name}.dcp")
	# 	stub_file = os.path.join(target_dir, f"{core_name}.v")

	# 	if self.current_project is None:
	# 		self._create_project(None)

	# 	if self.current_core != core_name:
	# 		self._read_ip(xci_file)

	# 		self.current_core = core_name

	# 	if os.path.exists(dcp_file) or os.path.exists(stub_file):
	# 		pass


	def synthesis(self, top: str, srcs: list[str], constrs: str, *,
		synth_incremental: bool = False,

		synth_directive: str = 'default',
		synth_flatten_hierarchy: str = 'rebuilt',
		synth_fsm_extraction: str = 'auto',

		synth_report_timing_summary_file: str | None = None,
		synth_report_utilization_file: str | None = None,
		synth_report_incremental_reuse_file: str | None = None,

		synth_dcp_file: str | None = None,
		synth_functional_netlist_file: str | None = None,
		synth_timing_netlist_file: str | None = None,


		run_opt: bool = False,
		opt_directive: str = 'default',


		impl_incremental: bool = False,

		place_directive: str = 'default',
		place_dcp_file: str | None = None,


		run_phys_opt: bool = False,
		phys_opt_directive: str = 'default',


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
					logger.info(f'dcp does not exist at: {dcp_file}\nskipping incremental {stage}')
				else:
					self._read_checkpoint(dcp_file, incremental=True)

		# tcl begin
		if self.current_project is None:
			self._create_project(None)

		constr_fileset = 'constrs_1'
		source_fileset = 'sources_1'

		#* sources
		for s in srcs:
			self._add_files(s, fileset=source_fileset, scan_for_includes=True)

		for c in constrs:
			self._add_files(c, fileset=constr_fileset)

		self._update_compile_order(fileset=constr_fileset)
		self._update_compile_order(fileset=source_fileset)

		#* synth_design
		if synth_incremental:
			_incremental('synthesis', dcp_file=synth_dcp_file)

		self._synth_design(
			top=top,
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


		# opt_design
		if run_opt:
			self._opt_design(directive=opt_directive)


		if impl_incremental:
			_incremental('implementation', dcp_file=route_dcp_file)

		#* place_design
		self._place_design(directive=place_directive)

		if place_dcp_file:
			self._write_checkpoint(place_dcp_file, force=True)


		# phys_opt
		if run_phys_opt:
			self._phys_opt_design(directive=phys_opt_directive)


		#* route_design
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

