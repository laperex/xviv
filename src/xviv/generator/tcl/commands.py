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


	def synthesis(self, top: str, srcs: list[str], constrs: str):
		# tcl begin
		if self.current_project is None:
			self._create_project(None)

		# add sources
		for src_file in srcs:
			self._add_files(src_file, fileset='sources_1', scan_for_includes=True)

		for constr_file in constrs:
			self._add_files(constr_file, fileset='constrs_1')

		self._update_compile_order(fileset='constrs_1')
		self._update_compile_order(fileset='sources_1')
		
		

		
