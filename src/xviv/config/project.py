
import logging
import os
import typing

from xviv.config.catalog import Catalog
from xviv.config.model import (
	AppConfig,
	BdConfig,
	CoreConfig,
	DesignConfig,
	FpgaConfig,
	IpConfig,
	IpWrapperConfig,
	PlatformConfig,
	SimulationConfig,
	SourceFile,
	SubCoreConfig,
	SynthConfig,
	VitisConfig,
	VivadoConfig,
)
from xviv.generator.wrapper import SystemVerilogWrapper
from xviv.parsers.bd_json import get_bd_core_list
from xviv.utils import error
from xviv.utils.fs import resolve_globs

logger = logging.getLogger(__name__)


class XvivConfig:

	def __init__(self, config_file_path: str, work_dir: str | None, board_repo_list: list[str] = [], ip_repo_list: list[str] = []):
		self.base_dir = os.path.abspath(os.path.dirname(config_file_path))

		if work_dir is None:
			work_dir = 'build'

		self.work_dir = os.path.join(self.base_dir, work_dir)

		self.board_repo_list: list[str] = []
		for path in board_repo_list:
			if os.path.isdir(path):
				self.board_repo_list.append(path)

		ip_repo_list.append(self._get_ip_repo_default)

		self.ip_repo_list: list[str] = []
		for path in ip_repo_list:
			if os.path.isdir(path) and path not in self.ip_repo_list:
				self.ip_repo_list.append(path)

		# lists
		self._fpga_list: list[FpgaConfig] = []

		self._ip_list: list[IpConfig] = []
		self._wrapper_list: list[IpWrapperConfig] = []

		self._bd_list: list[BdConfig] = []

		self._core_list: list[CoreConfig] = []
		self._subcore_list: list[SubCoreConfig] = []

		self._design_list: list[DesignConfig] = []

		self._synth_list: list[SynthConfig] = []
		self._sim_list: list[SimulationConfig] = []
		self._platform_list: list[PlatformConfig] = []
		self._app_list: list[AppConfig] = []

		self._vivado_cfg: VivadoConfig | None = None
		self._vitis_cfg: VitisConfig | None = None

		self._catalog_cfg: Catalog | None = None

	def build(self) -> typing.Self:
		os.makedirs(self.work_dir, exist_ok=True)

		if not os.path.exists(self._vivado_cfg.path):
			raise error.InvalidPathError(self._vivado_cfg.path, 'Vivado')

		if not os.path.exists(self._vitis_cfg.path):
			raise error.InvalidPathError(self._vitis_cfg.path, 'Vitis')

		for i in self._core_list:
			try:
				i.vlnv = self._resolve_core_vlnv(i.vlnv)
			except error.VlnvResolveError:
				raise error.CoreVlnvResolveError(name=i.name, vlnv=i.vlnv)

		return self

	def _resolve_core_vlnv(self, vlnv: str) -> str:
		for i in self._ip_list:
			if vlnv in i.vlnv:
				return i.vlnv

		entry = self.get_catalog().lookup_optional(vlnv)
		if entry is not None:
			return entry.vlnv

		raise error.VlnvResolveError(vlnv)

	# -------------------------------------------------------------------------
	# Build methods
	# -------------------------------------------------------------------------

	def validate_design(self, design_name: str):
		design_cfg = self.get_design(design_name)

		for i in design_cfg.sources:
			if not os.path.exists(i.file):
				raise error.DesignSourcesMissingError(design_name, i.file)

	def validate_sim(self, sim_name: str):
		sim_cfg = self.get_sim(sim_name)




	def validate_app(self, app_name: str, check_sources: bool = True):
		app_cfg = self.get_app(app_name)

		if not os.path.exists(app_cfg.elf_file):
			raise error.AppElfMissingError(app_name, app_cfg.elf_file)

		if check_sources:
			for i in app_cfg.sources:
				if not os.path.exists(i.file):
					raise error.AppSourcesMissingError

			if app_cfg.sources:
				raise error.AppSourcesEmptyError

	def validate_platform(self, platform_name: str):
		platform_cfg = self.get_platform(platform_name)

		if not os.path.exists(platform_cfg.xsa_file):
			raise error.PlatformXsaMissingError(platform_name, platform_cfg.xsa_file)

		if not os.path.exists(platform_cfg.bitstream_file):
			raise error.PlatformBitstreamMissingError(platform_name, platform_cfg.bitstream_file)

	def validate_synth(self, *,
		design: str | None = None,
		core: str | None = None,
		bd: str | None = None
	):
		synth_cfg = self.get_synth(design_name=design, core_name=core, bd_name=bd)

		for i in synth_cfg.constraints:
			if not os.path.exists(i):
				if bd:
					raise error.SynthConstraintsMissingError(bd, 'BD', i)
				if design:
					raise error.SynthConstraintsMissingError(design, 'Design', i)
				if core:
					raise error.SynthConstraintsMissingError(core, 'Core', i)

	def validate_ip(self, ip_name: str):
		ip_cfg = self.get_ip(ip_name)

		for i in ip_cfg.sources:
			if not os.path.exists(i.file):
				raise error.IpSourcesMissingError(ip_name, i.file)

		if not ip_cfg.sources:
			raise error.IpSourcesEmptyError(ip_name)

	def validate_wrapper(self, ip_name: str):
		wrapper_cfg = self.get_wrapper(ip_name)

		for i in wrapper_cfg.sources:
			if not os.path.exists(i.file):
				raise error.WrapperSourceMissingError(ip_name, i)

		if not wrapper_cfg.sources:
			raise error.WrapperSourcesEmptyError(ip_name)

	def build_attach_ip_wrapper(self, ip_name: str) -> None:
		ip_cfg = self.get_ip(ip_name)

		if wrapper_cfg := self._get_wrapper_cfg_optional(ip_name):
			self.validate_wrapper(ip_name=ip_name)

			ip_cfg.top = wrapper_cfg.wrapper_top
			ip_cfg.sources += self._resolve_sources([wrapper_cfg.wrapper_file])

			SystemVerilogWrapper(
				top=wrapper_cfg.ip_top,
				wrapper_top=wrapper_cfg.wrapper_top,
				wrapper_file=wrapper_cfg.wrapper_file,
				sources=[i.file for i in wrapper_cfg.sources]
			)

	# -------------------------------------------------------------------------
	# Add methods
	# -------------------------------------------------------------------------

	def add_vivado_cfg(self,
		path: str,
		mode: str = 'batch',
		max_threads: int = 10,
		hw_server: str = 'localhost:3121'
	) -> typing.Self:
		if self._vivado_cfg is not None:
			raise error.VivadoAlreadySpecifiedError()

		if self._catalog_cfg is not None:
			raise error.CoreCatalogAlreadySpecifiedError()

		self._vivado_cfg = VivadoConfig(
			path=path,
			mode=mode,
			max_threads=max_threads,
			hw_server=hw_server,
			dry_run=False
		)

		self._catalog_cfg = Catalog(
			vivado_path=path,
			ip_repos=self.ip_repo_list
		)

		return self

	def add_vitis_cfg(self,
		path: str,
	) -> typing.Self:
		if self._vitis_cfg is not None:
			raise error.VitisAlreadySpecifiedError()

		self._vitis_cfg = VitisConfig(
			path=path
		)

		return self

	def add_fpga_cfg(self, name: str, *,
		fpga_part: str | None = None,
		board_part: str | None = None
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_fpga_cfg_optional(name) is not None:
			raise error.FpgaAlreadyExistsError(name)

		if fpga_part is None and board_part is None:
			raise error.FpgaPartUnspecifiedError(name)

		self._fpga_list.append(
			FpgaConfig(
				name=name,
				fpga_part=fpga_part,
				board_part=board_part
			)
		)

		return self

	def add_ip_cfg(self, name: str, *,
		vendor: str = 'xviv.org',
		library: str = 'xviv',
		version: str = '1.0',

		top: str | None = None,
		sources: list[typing.Any] = [],

		fpga: str | None = None,
		vlnv: str | None = None,
		repo: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_ip_cfg_optional(name) is not None:
			raise error.IpAlreadyExistsError(name)

		fpga = self._resolve_fpga(fpga)

		if vlnv is None:
			vlnv = f"{vendor}:{library}:{name}:{version}"

		if repo is None:
			repo = self._get_ip_repo_default

		if repo not in self.ip_repo_list:
			if os.path.isdir(repo):
				self.ip_repo_list.append(repo)

		if top is None:
			top = name

		self._ip_list.append(
			IpConfig(
				vendor=vendor,
				library=library,
				name=name,
				version=version,
				vlnv=vlnv,
				repo=repo,
				top=top,
				fpga_ref=fpga,
				sources=self._resolve_sources(sources)
			)
		)

		return self

	def add_wrapper_cfg(self, *,
		ip: str,
		sources: list[typing.Any],
		wrapper_top: str | None = None,
		wrapper_file: str | None = None
	) -> typing.Self:
		if self._get_wrapper_cfg_optional(ip) is not None:
			raise error.WrapperAlreadyExistsError(ip)

		try:
			ip_cfg = self.get_ip(ip)
		except error.IpDoesNotExistError:
			raise error.WrapperIpMissing(ip_name=ip)

		if wrapper_top is None:
			wrapper_top = f'{ip_cfg.top}_wrapper'

		if wrapper_file is None:
			wrapper_file = os.path.join(self.wrapper_dir, f"{wrapper_top}.sv")

		self._wrapper_list.append(
			IpWrapperConfig(
				ip_name=ip,
				ip_top=ip_cfg.top,
				wrapper_top=wrapper_top,
				wrapper_file=wrapper_file,
				sources=self._resolve_sources(sources)
			)
		)

		return self

	def add_bd_cfg(self, name: str, *,
		save_file: str | None = None,
		bd_file: str | None = None,
		fpga: str | None = None,
		bd_wrapper_file: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_bd_cfg_optional(name) is not None:
			raise error.BdAlreadyExistsError(name)

		fpga = self._resolve_fpga(fpga)

		if save_file is None:
			save_file = os.path.join(self.scripts_dir, 'bd', f'{name}.tcl')

		if bd_file is None:
			bd_file = os.path.join(self.bd_dir, name, f'{name}.bd')

		if bd_wrapper_file is None:
			bd_wrapper_file = os.path.join(self.bd_dir, name, 'hdl', f"{name}_wrapper.v")

		if os.path.exists(bd_file):
			for xci_name, xci_file, vlnv, inst_hier_path in get_bd_core_list(bd_file):
				self.add_core_cfg(
					name=xci_name,
					vlnv=vlnv,
					xci_file=xci_file,
					fpga=fpga
				)

				self.add_subcore_cfg(
					bd=name,
					inst_hier_path=inst_hier_path,
					core=xci_name
				)

				self.add_synth_cfg(
					core=xci_name,

					run_place=False,
					place_dcp=False,

					run_route=False,
					route_dcp=False,

					run_phys_opt=False,
					run_opt=False,
				)

		self._bd_list.append(
			BdConfig(
				name=name,
				save_file=save_file,
				fpga_ref=fpga,
				bd_file=bd_file,

				bd_wrapper_file=bd_wrapper_file,
			)
		)

		return self


	def add_subcore_cfg(self, *,
		core: str,
		inst_hier_path: str,

		bd: str | None = None,
		design: str | None = None,
	) -> typing.Self:
		for entry in self.get_subcore_list(bd_name=bd, design_name=design):
			if entry.inst_hier_path == inst_hier_path:
				if bd:
					raise error.SubCoreBdAlreadyExistsError(inst_hier_path, core, bd)
				if design:
					raise error.SubCoreDesignAlreadyExistsError(inst_hier_path, core, design)

		if bd is None and design is None:
			raise error.SubCoreIdentifierUnspecifiedError(inst_hier_path, core)

		if bd is not None and design is not None:
			raise error.SubCoreIdentifierMultipleError(inst_hier_path, core, bd, design)

		self._subcore_list.append(
			SubCoreConfig(
				inst_hier_path=inst_hier_path,
				bd=bd,
				design=design,
				core=core
			)
		)

		return self


	def add_core_cfg(self, name: str, *,
		ip: str | None = None,
		vlnv: str | None = None,
		xci_file: str | None = None,
		fpga: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_core_cfg_optional(name) is not None:
			raise error.CoreAlreadyExistsError(name)

		if xci_file is None:
			xci_file = os.path.join(self.core_dir, name, f'{name}.xci')

		fpga = self._resolve_fpga(fpga)

		if ip is None and vlnv is None:
			raise error.CoreIdentifierUnspecifiedError(name)

		if ip is not None and vlnv is not None:
			raise error.CoreIdentifierMultipleError(name, ip, vlnv)

		if ip:
			vlnv = self.get_ip().vlnv

		if vlnv is None:
			raise error.CoreVlnvUnspecifiedError(name)

		self._core_list.append(
			CoreConfig(
				name=name,
				vlnv=vlnv,
				xci_file=xci_file,
				fpga_ref=fpga
			)
		)

		return self

	def add_design_cfg(self, name: str, *,
		sources: list[typing.Any],
		top: str | None = None,
		fpga: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_design_cfg_optional(name) is not None:
			raise error.DesignAlreadyExistsError(name)

		fpga = self._resolve_fpga(fpga)

		if top is None:
			top = name

		self._design_list.append(
			DesignConfig(
				name=name,
				top=top,
				# sources=resolve_globs(sources, self.base_dir),
				sources=self._resolve_sources(sources),
				fpga_ref=fpga
			)
		)

		return self

	def add_synth_cfg(self, *,
		design: str | None = None,
		core: str | None = None,
		bd: str | None = None,
		fpga: str | None = None,

		out_of_context_subcores: bool = False,

		top: str | None = None,

		sources: list[typing.Any] = [],

		run_synth: bool = True,
		run_place: bool = True,
		run_route: bool = True,

		synth_incremental: bool = True,
		run_opt: bool = True,
		impl_incremental: bool = True,
		run_phys_opt: bool = True,

		synth_dcp: bool | str | None = True,
		place_dcp: bool | str | None = True,
		route_dcp: bool | str | None = True,

		bitstream: bool | str | None = None,
		hw_platform: bool | str | None = None,

		synth_report_timing_summary: bool | str | None = False,
		synth_report_utilization: bool | str | None = False,

		route_report_drc: bool | str | None = False,
		route_report_methodology: bool | str | None = False,
		route_report_power: bool | str | None = False,
		route_report_route_status: bool | str | None = False,
		route_report_timing_summary: bool | str | None = False,

		synth_report_incremental_reuse: bool | str | None = False,
		impl_report_incremental_reuse: bool | str | None = False,

		synth_functional_netlist: bool | str | None = False,
		synth_timing_netlist: bool | str | None = False,
		impl_functional_netlist: bool | str | None = False,
		impl_timing_netlist: bool | str | None = False,

		impl_timing_sdf: bool | str | None = None,

		synth_stub: bool | str | None = False,

		synth_directive: str = 'default',
		synth_mode: str | None = None,
		synth_flatten_hierarchy: str = 'rebuilt',
		synth_fsm_extraction: str = 'auto',

		opt_directive: str = 'default',

		place_directive: str = 'default',

		phys_opt_directive: str = 'default',

		route_directive: str = 'default',

		usr_access_value: int | None = None,
	) -> typing.Self:
		param_ids = [i for i in [design, core, bd] if i]

		if self._get_synth_cfg_optional(design_name=design, core_name=core, bd_name=bd) is not None:
			raise error.SynthAlreadyExistsError(name=param_ids[0])

		id_name = param_ids[0]

		if bd:
			bd_cfg = self.get_bd(bd)

			fpga = self._resolve_fpga(fpga, bd_cfg.fpga_ref, 'BD', bd_cfg.name)

			if top is None:
				top = f'{bd}_wrapper'

		if core:
			core_cfg = self.get_core(core)
			fpga = self._resolve_fpga(fpga, core_cfg.fpga_ref, 'Core', core_cfg.name)

			if top is None:
				top = core

			if synth_mode is None:
				synth_mode = 'out_of_context'

			if not isinstance(synth_stub, str):
				synth_stub = True

			if not isinstance(synth_dcp, str):
				synth_dcp = True

		if design:
			design_cfg = self.get_design(design)
			fpga = self._resolve_fpga(fpga, design_cfg.fpga_ref, 'Design', design_cfg.name)

			if top is None:
				top = design_cfg.top

			if hw_platform is None:
				hw_platform = False

		constraints_list: list[str] = []

		if synth_mode == 'out_of_context':
			bitstream = False
			hw_platform = False
			usr_access_value = None

		# print(sources)

		for i in self._resolve_sources(sources,
			# used_in_ooc=False,
			used_in_sim=False,
			used_in_impl=True,
			used_in_synth=True
		):
			print(i, i.is_constraint_file, i.used_in_ooc)
			if i.is_constraint_file:
				if synth_mode == 'out_of_context':
					if i.used_in_ooc:
						constraints_list.append(i.file)
				else:
					if not i.used_in_ooc:
						constraints_list.append(i.file)

		if synth_mode is None:
			synth_mode = 'default'

		if bitstream is None:
			bitstream = True

		if hw_platform is None:
			hw_platform = True

		if impl_timing_sdf is None:
			impl_timing_sdf = True if impl_timing_netlist else False

		assert top is not None
		assert fpga is not None

		synth_subdir = os.path.join(self.synth_dir, id_name)
		synth_reports_subdir = os.path.join(synth_subdir, 'reports')
		synth_netlists_subdir = os.path.join(synth_subdir, 'netlists')
		synth_checkpoints_subdir = os.path.join(synth_subdir, 'checkpoints')

		self._synth_list.append(
			SynthConfig(
				design_name=design,
				core_name=core,
				bd_name=bd,
				fpga_ref=fpga,
				top=top,

				out_of_context_subcores=out_of_context_subcores,

				constraints=constraints_list,

				synth_incremental=synth_incremental,
				run_synth=run_synth,
				run_opt=run_opt,

				impl_incremental=impl_incremental,
				run_place=run_place,
				run_phys_opt=run_phys_opt,
				run_route=run_route,

				synth_dcp_file=_resolve_val(synth_dcp, os.path.join(synth_checkpoints_subdir, 'synth.dcp')),
				place_dcp_file=_resolve_val(place_dcp, os.path.join(synth_checkpoints_subdir, 'place.dcp')),
				route_dcp_file=_resolve_val(route_dcp, os.path.join(synth_checkpoints_subdir, 'route.dcp')),

				bitstream_file=_resolve_val(bitstream, os.path.join(synth_subdir, f'{id_name}.bit')),
				hw_platform_xsa_file=_resolve_val(hw_platform, os.path.join(synth_subdir, f'{id_name}.xsa')),

				synth_report_timing_summary_file=_resolve_val(synth_report_timing_summary, os.path.join(synth_reports_subdir, 'synth_report_timing_summary_file.rpt')),
				synth_report_utilization_file=_resolve_val(synth_report_utilization, os.path.join(synth_reports_subdir, 'synth_report_utilization_file.rpt')),
				synth_report_incremental_reuse_file=_resolve_val(synth_report_incremental_reuse, os.path.join(synth_reports_subdir, 'synth_report_incremental_reuse_file.rpt')),
				route_report_drc_file=_resolve_val(route_report_drc, os.path.join(synth_reports_subdir, 'route_report_drc_file.rpt')),
				route_report_methodology_file=_resolve_val(route_report_methodology, os.path.join(synth_reports_subdir, 'route_report_methodology_file.rpt')),
				route_report_power_file=_resolve_val(route_report_power, os.path.join(synth_reports_subdir, 'route_report_power_file.rpt')),
				route_report_route_status_file=_resolve_val(route_report_route_status, os.path.join(synth_reports_subdir, 'route_report_route_status_file.rpt')),
				route_report_timing_summary_file=_resolve_val(route_report_timing_summary, os.path.join(synth_reports_subdir, 'route_report_timing_summary_file.rpt')),
				impl_report_incremental_reuse_file=_resolve_val(impl_report_incremental_reuse, os.path.join(synth_reports_subdir, 'impl_report_incremental_reuse_file.rpt')),

				synth_functional_netlist_file=_resolve_val(synth_functional_netlist, os.path.join(synth_netlists_subdir, f'{id_name}_synth_functional_netlist.v')),
				synth_timing_netlist_file=_resolve_val(synth_timing_netlist, os.path.join(synth_netlists_subdir, f'{id_name}_synth_timing_netlist.v')),
				impl_functional_netlist_file=_resolve_val(impl_functional_netlist, os.path.join(synth_netlists_subdir, f'{id_name}_impl_functional_netlist.v')),
				impl_timing_netlist_file=_resolve_val(impl_timing_netlist, os.path.join(synth_netlists_subdir, f'{id_name}_impl_timing_netlist.v')),

				impl_timing_sdf_file=_resolve_val(impl_timing_sdf, os.path.join(synth_netlists_subdir, f'{id_name}_impl_timing.sdf')),

				synth_stub_file=_resolve_val(synth_stub, os.path.join(synth_subdir, f'{id_name}_stub.v')),

				synth_directive=synth_directive,
				synth_mode=synth_mode,
				synth_flatten_hierarchy=synth_flatten_hierarchy,
				synth_fsm_extraction=synth_fsm_extraction,
				opt_directive=opt_directive,
				place_directive=place_directive,
				phys_opt_directive=phys_opt_directive,
				route_directive=route_directive,

				usr_access_value=usr_access_value
			)
		)

		return self

	def add_sim_cfg(self, name: str, *,
		sources: list[typing.Any],
		top: str | None = None,
		backend: str = 'xsim',
		sdfmax: list[str] = [],
		timescale: str = '1ns/1ps',

		bd: str | None = None,
		design: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_sim_cfg_optional(name) is not None:
			raise error.SimDoesNotExistError(name)

		if top is None:
			top = name

		sim_subdir = os.path.join(self.work_dir, 'sim', name)

		self._sim_list.append(
			SimulationConfig(
				name=name,
				top=top,
				bd=bd,
				design=design,
				sources=self._resolve_sources(sources),
				backend=backend,
				timescale=timescale,
				work_dir=sim_subdir,
				sdfmax=sdfmax
			)
		)

		return self

	def add_platform_cfg(self, name: str, *,
		bd: str | None = None,
		design: str | None = None,

		xsa: str | None = None,
		bitstream: str | None = None,

		cpu: str = 'microblaze_0',
		os: str = 'standalone',
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_platform_cfg_optional(name) is not None:
			raise error.PlatformDoesNotExistError(name)

		param_ids = [i for i in [bd, design, xsa] if i]

		if len(param_ids) == 0:
			raise error.PlatformIdentifierUnspecifiedError(name)

		if len(param_ids) != 1:
			raise error.PlatformIdentifierMultipleError(name, bd=bd, design=design, xsa=xsa)

		if xsa is None:
			synth_cfg = self.get_synth(design_name=design, bd_name=bd)

			xsa = synth_cfg.hw_platform_xsa_file

		if bitstream is None:
			synth_cfg = self.get_synth(design_name=design, bd_name=bd)

			bitstream = synth_cfg.bitstream_file

		import os as _os
		platform_subdir = _os.path.join(self.work_dir, 'platform', name)

		self._platform_list.append(
			PlatformConfig(
				name=name,
				cpu=cpu,
				os=os,
				xsa_file=xsa,
				bitstream_file=bitstream,
				dir=platform_subdir
			)
		)

		return self

	def add_app_cfg(self, name: str, *,
		platform: str,
		template: str = 'empty_application',
		sources: list[typing.Any] = []
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_app_cfg_optional(name) is not None:
			raise error.AppAlreadyExistsError(name)

		app_subdir = os.path.join(self.work_dir, 'app', name)

		# TODO: Remove Hardcoded - Requires editing generated Makefile
		elf = os.path.join(app_subdir, 'executable.elf')

		self._app_list.append(
			AppConfig(
				name=name,
				platform=platform,
				template=template,
				sources=self._resolve_sources(sources),
				dir=app_subdir,
				elf_file=elf
			)
		)

		return self

	# -------------------------------------------------------------------------
	# Get methods (public)
	# -------------------------------------------------------------------------

	def get_catalog(self) -> Catalog:
		if self._catalog_cfg:
			return self._catalog_cfg

		raise error.UninitializedCoreCatalogError()

	def get_vivado(self) -> VivadoConfig:
		if self._vivado_cfg:
			return self._vivado_cfg

		raise error.UninitializedVivadoError()

	def get_vitis(self) -> VitisConfig:
		if self._vitis_cfg:
			return self._vitis_cfg

		raise error.UninitializedVitisError()

	def get_fpga(self, name: str | None) -> FpgaConfig:
		if name is None:
			return self._get_fpga_cfg_default

		fpga_cfg = self._get_fpga_cfg_optional(name)

		if fpga_cfg is None:
			raise error.FpgaDoesNotExistError(name)

		return fpga_cfg

	def get_ip(self, name: str) -> IpConfig:
		ip_cfg = self._get_ip_cfg_optional(name)

		if ip_cfg is None:
			raise error.IpDoesNotExistError(name)

		return ip_cfg

	def get_wrapper(self, name: str) -> IpWrapperConfig:
		wrapper = self._get_wrapper_cfg_optional(name)

		if wrapper is None:
			raise error.WrapperDoesNotExistError(name)

		return wrapper

	def get_bd(self, name: str) -> BdConfig:
		bd = self._get_bd_cfg_optional(name)

		if bd is None:
			raise error.BdDoesNotExistError(name)

		return bd

	def get_core(self, name: str) -> CoreConfig:
		core = self._get_core_cfg_optional(name)

		if core is None:
			raise error.CoreDoesNotExistError(name)

		return core

	def get_design(self, name: str) -> DesignConfig:
		design = self._get_design_cfg_optional(name)

		if design is None:
			raise error.DesignDoesNotExistError(name)

		return design

	def get_synth(self,
		design_name: str | None = None,
		core_name: str | None = None,
		bd_name: str | None = None
	) -> SynthConfig:
		synth = self._get_synth_cfg_optional(
			design_name=design_name,
			core_name=core_name,
			bd_name=bd_name,
		)

		if synth is None:
			raise error.SynthDoesNotExistError(design=design_name, core=core_name, bd=bd_name)

		return synth

	def get_sim(self, name: str) -> SimulationConfig:
		sim = self._get_sim_cfg_optional(name)

		if sim is None:
			raise error.SimDoesNotExistError(name)

		return sim

	def get_platform(self, name: str) -> PlatformConfig:
		platform = self._get_platform_cfg_optional(name)

		if platform is None:
			raise error.PlatformDoesNotExistError(name)

		return platform

	def get_app(self, name: str) -> AppConfig:
		app = self._get_app_cfg_optional(name)

		if app is None:
			raise error.AppDoesNotExistError(name)

		return app

	def get_subcore_list(self, bd_name: str | None = None, design_name: str | None = None) -> list[SubCoreConfig]:
		subcore_list: list[SubCoreConfig] = []

		if bd_name is None and design_name is None:
			raise error.SubCoreListIdentifierUnspecifiedError()

		if bd_name is not None and design_name is not None:
			raise error.SubCoreListIdentifierMultipleError(bd=bd_name, design=design_name)

		for i in self._subcore_list:
			if design_name:
				if i.design == design_name:
					subcore_list.append(i)

			if bd_name:
				if i.bd == bd_name:
					subcore_list.append(i)

		return subcore_list

	# -------------------------------------------------------------------------
	# Private helpers - optional lookups
	# -------------------------------------------------------------------------

	def _get_fpga_cfg_optional(self, name: str) -> FpgaConfig | None:
		return next((i for i in self._fpga_list if i.name == name), None)

	def _get_ip_cfg_optional(self, name: str) -> IpConfig | None:
		return next((i for i in self._ip_list if i.name == name), None)

	def _get_wrapper_cfg_optional(self, name: str) -> IpWrapperConfig | None:
		return next((i for i in self._wrapper_list if i.ip_name == name), None)

	def _get_bd_cfg_optional(self, name: str) -> BdConfig | None:
		return next((i for i in self._bd_list if i.name == name), None)

	def _get_core_cfg_optional(self, name: str) -> CoreConfig | None:
		return next((i for i in self._core_list if i.name == name), None)

	def _get_design_cfg_optional(self, name: str) -> DesignConfig | None:
		return next((i for i in self._design_list if i.name == name), None)

	def _get_synth_cfg_optional(self,
		design_name: str | None = None,
		core_name: str | None = None,
		bd_name: str | None = None
	) -> SynthConfig | None:
		ids = [
			i for i in [design_name, core_name, bd_name] if i
		]

		if len(ids) == 0:
			raise error.SynthIdentifierUnspecifiedError()
		elif len(ids) != 1:
			raise error.SynthIdentifierMultipleError(design=design_name, core=core_name, bd=bd_name)

		return next((
				i for i in self._synth_list
					if (bd_name is not None and i.bd_name == bd_name) or
						(design_name is not None and i.design_name == design_name) or
						(core_name is not None and i.core_name == core_name)
			),
			None,
		)

	def _get_sim_cfg_optional(self, name: str) -> SimulationConfig | None:
		return next((i for i in self._sim_list if i.name == name), None)

	def _get_platform_cfg_optional(self, name: str) -> PlatformConfig | None:
		return next((i for i in self._platform_list if i.name == name), None)

	def _get_app_cfg_optional(self, name: str) -> AppConfig | None:
		return next((i for i in self._app_list if i.name == name), None)

	# -------------------------------------------------------------------------
	# Private helpers - resolvers
	# -------------------------------------------------------------------------

	def _resolve_fpga(self, fpga_ref: str | None, default_fpga_ref: str | None = None, mismatch_check: str | None = None, mismatch_name: str = '') -> str:
		if fpga_ref is None:
			if default_fpga_ref is None:
				fpga_ref = self._get_fpga_cfg_default.name
			else:
				fpga_ref = default_fpga_ref

		if self._get_fpga_cfg_optional(fpga_ref) is None:
			raise error.FpgaResolveError(fpga_ref)

		if mismatch_check is not None:
			if default_fpga_ref != fpga_ref:
				raise error.FpgaRefMismatchError(mismatch_check, mismatch_name, default_fpga_ref, fpga_ref)

		return fpga_ref

	def _resolve_sources(self, sources: list[typing.Any], *,
		used_in_synth: bool = True,
		used_in_impl: bool = True,
		used_in_ooc: bool = True,
		used_in_sim: bool = True,
	) -> list[SourceFile]:
		is_constraint_file: bool = False

		_VALID_STAGES = frozenset({'synth', 'impl', 'ooc', 'sim'})

		default_stages = {
			s for s, v in (
				('synth', used_in_synth),
				('impl',  used_in_impl),
				('ooc',   used_in_ooc),
				('sim',   used_in_sim),
			) if v
		}

		res: list[SourceFile] = []
		for i in sources:
			if isinstance(i, str):
				files, stages = [i], default_stages
			else:
				stages = set(i.get('used_in', []))
				if unknown := stages - _VALID_STAGES:
					raise ValueError(f"Unknown stages: {unknown}")
				files = i['files']
				is_constraint_file = bool(i.get('constraints', False))

			for k in resolve_globs(files, self.base_dir):
				res.append(SourceFile.from_stages(k, stages, is_constraint_file))

		return res

	# -------------------------------------------------------------------------
	# Properties - default getters
	# -------------------------------------------------------------------------

	@property
	def _get_ip_repo_default(self) -> str:
		return self.__path_from_build_dir('ip')

	@property
	def _get_fpga_cfg_default(self) -> FpgaConfig:
		if not self._fpga_list:
			raise error.NoFpgaError()

		return self._fpga_list[0]

	# -------------------------------------------------------------------------
	# Properties - path helpers
	# -------------------------------------------------------------------------

	@property
	def wrapper_dir(self):
		return self.__path_from_build_dir('wrapper')

	@property
	def core_dir(self):
		return self.__path_from_build_dir('core')

	@property
	def synth_dir(self):
		return self.__path_from_build_dir('synth')

	@property
	def bd_dir(self):
		return self.__path_from_build_dir('bd')

	@property
	def scripts_dir(self):
		return self.__path_from_base_dir(os.path.join('scripts', 'xviv'))

	def __path_from_build_dir(self, path: str):
		return os.path.join(self.work_dir, path)

	def __path_from_base_dir(self, path: str):
		return os.path.join(self.base_dir, path)


def _resolve_val(
	field: bool | str | None,
	default: str
) -> str | None:
	if isinstance(field, str):
		return field
	if field:
		return default
	return None