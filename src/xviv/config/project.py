
import dataclasses
import glob
import logging
import os
import re
import sys
import typing
from xviv.config.catalog import Catalog
from xviv.config.model import AppConfig, BdConfig, SubCoreConfig, CoreConfig, DesignConfig, FpgaConfig, IpConfig, PlatformConfig, SimulationConfig, SynthConfig, VitisConfig, VivadoConfig, IpWrapperConfig
from xviv.generator.wrapper import SystemVerilogWrapper
from xviv.parsers.bd_json import get_bd_core_list
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

		for wrapper_cfg in self._wrapper_list:
			ip_cfg = self.get_ip(wrapper_cfg.ip_name)

			SystemVerilogWrapper(
				top=wrapper_cfg.ip_top,
				wrapper_top=ip_cfg.top,
				wrapper_file=wrapper_cfg.wrapper_file,
				sources=wrapper_cfg.sources
			)

		return self

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
			#! VivadoCfg - VivadoCfgAlreadySpecified
			raise RuntimeError('ERROR: Vivado Config Already Specified')

		if not os.path.exists(path):
			#! VivadoCfg - InvalidPath
			raise RuntimeError(f'ERROR: Invadlid Vivado Path: {path}')

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
			#! VitisCfg - VitisCfgAlreadySpecified
			raise RuntimeError('ERROR: Vitis Config Already Specified')

		if not os.path.exists(path):
			#! VitisCfg - InvalidPath
			raise RuntimeError(f'ERROR: Invadlid Vitis Path: {path}')
		
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
			#! FpgaCfg - FpgaCfgAlreadyExists
			raise RuntimeError(f'ERROR: Fpga entry with name: {name} already exists')


		if fpga_part is None and board_part is None:
			#! FpgaCfg - PartUnspecified
			raise RuntimeError(f'ERROR: part unspecified for fpga entry: {name}')

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
		sources: list[str] = [],

		fpga: str | None = None,
		vlnv: str | None = None,
		repo: str | None = None,
	) -> typing.Self:
		if self._get_ip_cfg_optional(name) is not None:
			#! IpCfg - IpCfgAlreadyExistsError
			raise RuntimeError(f'ERROR: IP entry with name: {name} already exists')

		# TODO: throw error for invalid name ''

		fpga = self._resolve_fpga(fpga)

		if vlnv is None:
			vlnv = f"{vendor}:{library}:{name}:{version}"

		if repo is None:
			repo = self._get_ip_repo_default

		if repo not in self.ip_repo_list:
			if os.path.isdir(repo):
				self.ip_repo_list.append(repo)

		if top is None:
			logger.warning(f'Top unspecified for ip_cfg: {name} - defaulting to {name}')
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
				sources=resolve_globs(sources, self.base_dir)
			)
		)

		return self

	def add_wrapper_cfg(self, *,
		ip: str,
		sources: list[str],
		wrapper_file: str | None = None
	) -> typing.Self:
		if self._get_wrapper_cfg_optional(ip) is not None:
			#! WrapperCfg - WrapperCfgAlreadyExistsForIpError
			raise RuntimeError(f'ERROR: Wrapper entry with name: {ip} already exists')

		ip_cfg = self._get_ip_cfg_optional(ip)

		if ip_cfg is None:
			#! WrapperCfg - IpCfgMissingError
			raise RuntimeError(f'ERROR: IP entry with name: {ip} does not exist')

		if not sources:
			#! WrapperCfg - UnspecifiedSourcesError
			raise RuntimeError(f'ERROR: sources not specified, empty: {sources}')

		for i in sources:
			if not os.path.exists(i):
				#! WrapperCfg - SourceMissingError
				raise RuntimeError(f'ERROR: required source does not exist: {i}')

		wrapper_top = f'{ip_cfg.top}_wrapper'
		if wrapper_file is None:
			# TODO: default ip wrapper file
			wrapper_file = os.path.join(self.wrapper_dir, f"{wrapper_top}.sv")

		self._wrapper_list.append(
			IpWrapperConfig(
				ip_name=ip,
				ip_top=ip_cfg.top,
				wrapper_file=wrapper_file,
				sources=resolve_globs(sources, self.base_dir)
			)
		)

		ip_cfg.top = wrapper_top
		if wrapper_file not in ip_cfg.sources:
			ip_cfg.sources.append(wrapper_file)

		return self

	def add_bd_cfg(self, name: str, *,
		save_file: str | None = None,
		bd_file: str | None = None,
		fpga: str | None = None,
		bd_wrapper_file: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_bd_cfg_optional(name) is not None:
			#! BdCfg - BdCfgAlreadyExists
			raise RuntimeError(f'ERROR: BD entry with name: {name} already exists')

		fpga = self._resolve_fpga(fpga)

		if save_file is None:
			save_file = os.path.join(self.scripts_dir, 'bd', f'{name}.tcl')

		if bd_file is None:
			bd_file = os.path.join(self.bd_dir, name, f'{name}.bd')

		bd_core_list: list[SubCoreConfig] = []

		if os.path.exists(bd_file):
			logger.info(f'Loading sub core info from - {bd_file}')
			bd_core_list = get_bd_core_list(bd_file)

		if bd_wrapper_file is None:
			bd_wrapper_file = os.path.join(self.bd_dir, name, 'hdl', f"{name}_wrapper.v")

		self._bd_list.append(
			BdConfig(
				name=name,
				save_file=save_file,
				vlnv_list=self._get_bd_cfg_vlnv_list(save_file),
				fpga_ref=fpga,
				bd_file=bd_file,

				bd_wrapper_file=bd_wrapper_file,

				# TODO
				core_list=bd_core_list
			)
		)

		return self

	def add_core_cfg(self, name: str, *,
		vlnv: str,
		xci_file: str | None = None,
		fpga: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_core_cfg_optional(name) is not None:
			#! CoreCfg - CoreCfgAlreadyExists
			raise RuntimeError(f'ERROR: core entry with name: {name} already exists')

		if xci_file is None:
			xci_file = os.path.join(self.core_dir, name, f'{name}.xci')

		fpga = self._resolve_fpga(fpga)

		prev_vlnv = vlnv
		vlnv = self._resolve_vlnv(vlnv)
		if prev_vlnv != vlnv:
			logger.warning(f'For Core entry with name: {name} - vlnv resolved to: {vlnv}')

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
		sources: list[str],
		top: str | None = None,
		fpga: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_design_cfg_optional(name) is not None:
			#! DesignCfg - DesignCfgAlreadyExists
			raise RuntimeError(f'ERROR: design entry with name: {name} already exists')

		fpga = self._resolve_fpga(fpga)

		if top is None:
			top = name

		self._design_list.append(
			DesignConfig(
				name=name,
				top=top,
				sources=resolve_globs(sources, self.base_dir),
				fpga_ref=fpga
			)
		)

		return self

	def add_synth_cfg(self, *,
		design: str | None = None,
		core: str | None = None,
		bd: str | None = None,
		fpga: str | None = None,

		top: str | None = None,
		
		constraints: list[str] = [],

		run_synth: bool = True,
		run_place: bool = True,
		run_route: bool = True,

		synth_incremental: bool = False,
		run_opt: bool = False,
		impl_incremental: bool = False,
		run_phys_opt: bool = False,

		synth_dcp: bool | str | None = True,
		place_dcp: bool | str | None = True,
		route_dcp: bool | str | None = True,

		bitstream: bool | str | None = True,
		hw_platform: bool | str | None = True,

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
		
		synth_stub: bool | str | None = False,
		
		synth_directive: str = 'default',
		synth_mode: str = 'default',
		synth_flatten_hierarchy: str = 'rebuilt',
		synth_fsm_extraction: str = 'auto',
		
		opt_directive: str = 'default',
		
		place_directive: str = 'default',
		
		phys_opt_directive: str = 'default',
		
		route_directive: str = 'default',
		
		usr_access_value: int | None = None,
	) -> typing.Self:
		list_ids = [i for i in [design, core, bd] if i]

		if len(list_ids) == 0:
			#! SynthCfg - UnspecifiedIdentifier
			raise RuntimeError('ERROR: need to specify at least one - bd, ip, design')

		if len(list_ids) != 1:
			#! SynthCfg - MultipleIdSpecified
			raise RuntimeError(f'ERROR: multiple ids specified: {' '.join(list_ids)}')

		if self._get_synth_cfg_optional(design_name=design, core_name=core, bd_name=bd) is not None:
			#! SynthCfg - SynthCfgAlreadyExists
			raise RuntimeError(f'ERROR: SynthConfig Already Exists for id: {list_ids}')

		id_name = list_ids[0]

		if bd:
			bd_cfg = self.get_bd(bd)

			fpga = self._resolve_fpga(bd_cfg.fpga_ref)

			if top is None:
				top = f'{bd}_wrapper'

		if core:
			pass

		if design:
			design_cfg = self.get_design(design)

			if fpga is None:
				fpga = design_cfg.fpga_ref
			else:
				if fpga != design_cfg.fpga_ref:
					#! SynthCfg - FpgaRefMismatch
					raise RuntimeError(f'ERROR: Mismatch fpga for Design: {design_cfg.fpga_ref} with specified: {fpga}')

			fpga = self._resolve_fpga(design_cfg.fpga_ref)

			if top is None:
				top = design_cfg.top

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
				
				constraints=resolve_globs(constraints, self.base_dir),

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
		sources: list[str],
		top: str | None = None,
		design: str | None = None,
		backend: str = 'xsim',
		timescale: str = '1ns/1ps'
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_sim_cfg_optional(name) is not None:
			#! SimCfg - SimCfgAlreadyExists
			raise RuntimeError(f'ERROR: sim entry with name: {name} already exists')

		if top is None:
			top = name

		assert top is not None
		assert name is not None
		
		sim_subdir = os.path.join(self.work_dir, 'sim', name)

		self._sim_list.append(
			SimulationConfig(
				name=name,
				top=top,
				design=design,
				sources=resolve_globs(sources, self.base_dir),
				backend=backend,
				timescale=timescale,
				work_dir=sim_subdir
			)
		)

		return self

	def add_platform_cfg(self, name: str, *,
		bd: str | None = None,
		design: str | None = None,
		xsa: str | None = None,
		bitstream: str | None = None,
		cpu: str | None = None,
		os: str | None = None,
	) -> typing.Self:
		list_ids = [i for i in [bd, design, xsa] if i]

		if len(list_ids) == 0:
			#! PlatformCfg - UnspecifiedIdentifier
			raise RuntimeError('ERROR: need to specify at least one - bd, design, xsa')

		if len(list_ids) != 1:
			#! PlatformCfg - MultipleIdSpecified
			raise RuntimeError(f'ERROR: multiple ids specified: {' '.join(list_ids)}')

		# TODO: throw error for invalid name ''

		if self._get_platform_cfg_optional(name) is not None:
			#! PlatformCfg - PlatformCfgAlreadyExists
			raise RuntimeError(f'ERROR: platform entry with name: {name} already exists')

		if cpu is None:
			cpu = 'microblaze_0'
		
		if os is None:
			os = 'standalone'
		
		if xsa is None:
			synth_cfg = self.get_synth(design_name=design, bd_name=bd)

			xsa = synth_cfg.hw_platform_xsa_file
		
		if bitstream is None:
			synth_cfg = self.get_synth(design_name=design, bd_name=bd)

			bitstream = synth_cfg.bitstream_file

		import os as _os
		if not _os.path.exists(xsa):
			raise RuntimeError(f'ERROR: xsa file not found: {xsa}')

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
		platform: str | None = None,
		template: str | None = None,
		sources: list[str] = []
	) -> typing.Self:
		if self._get_app_cfg_optional(name) is not None:
			#! AppCfg - appCfgAlreadyExists
			raise RuntimeError(f'ERROR: app entry with name: {name} already exists')

		if platform is None:
			raise RuntimeError('ERROR: platform entry required for app config')

		if template is None:
			template = 'empty_application'

		app_subdir = os.path.join(self.work_dir, 'app', name)

		elf = os.path.join(app_subdir, 'executable.elf')

		self._app_list.append(
			AppConfig(
				name=name,
				platform=platform,
				template=template,
				sources=resolve_globs(sources, self.base_dir),
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

		#! UninitializedCoreCatalog
		raise RuntimeError('ERROR: Catalog is not initialized')

	def get_vivado(self) -> VivadoConfig:
		if self._vivado_cfg:
			return self._vivado_cfg

		#! UninitializedVivadoCfg
		raise RuntimeError('ERROR: VivadoConfig is not initialized')

	def get_vitis(self) -> VitisConfig:
		if self._vitis_cfg:
			return self._vitis_cfg

		#! UninitializedVitisCfg
		raise RuntimeError('ERROR: VitisConfig is not initialized')

	def get_fpga(self, name: str | None) -> FpgaConfig:
		if name is None:
			return self._get_fpga_cfg_default

		fpga_cfg = self._get_fpga_cfg_optional(name)

		if fpga_cfg is None:
			#! FpgaCfg - FpgaCfgDoesNotExist
			raise RuntimeError(f'ERROR: Fpga does not exist for: {name}')

		return fpga_cfg

	def get_ip(self, name: str) -> IpConfig:
		ip_cfg = self._get_ip_cfg_optional(name)

		if ip_cfg is None:
			#! IpCfg - IpCfgDoesNotExist
			raise RuntimeError(f'ERROR: IP does not exist for: {name}')

		return ip_cfg

	def get_wrapper(self, name: str) -> IpWrapperConfig:
		wrapper = self._get_wrapper_cfg_optional(name)

		if wrapper is None:
			#! wrapperCfg - wrapperCfgDoesNotExist
			raise RuntimeError(f'ERROR: wrapper does not exist for: {name}')

		return wrapper

	def get_bd(self, name: str) -> BdConfig:
		bd = self._get_bd_cfg_optional(name)

		if bd is None:
			#! BDCfg - BDCfgDoesNotExist
			raise RuntimeError(f'ERROR: BD does not exist for: {name}')

		return bd

	def get_core(self, name: str) -> CoreConfig:
		core = self._get_core_cfg_optional(name)

		if core is None:
			#! CoreCfg - CoreCfgDoesNotExist
			raise RuntimeError(f'ERROR: Core does not exist for: {name}')

		return core

	def get_design(self, name: str) -> DesignConfig:
		design = self._get_design_cfg_optional(name)

		if design is None:
			#! DesignCfg - DesignCfgDoesNotExist
			raise RuntimeError(f'ERROR: Design does not exist for: {name}')

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
			#! SynthCfg - SynthCfgDoesNotExist
			raise RuntimeError(f'ERROR: Synth does not exist for: [{design_name or ''}{core_name or ''}{bd_name or ''}]')

		return synth

	def get_sim(self, name: str) -> SimulationConfig:
		sim = self._get_sim_cfg_optional(name)

		if sim is None:
			#! SimCfg - SimCfgDoesNotExist
			raise RuntimeError(f'ERROR: sim does not exist for: {name}')

		return sim

	def get_platform(self, name: str) -> PlatformConfig:
		platform = self._get_platform_cfg_optional(name)

		if platform is None:
			#! PlatformCfg - PlatformCfgDoesNotExist
			raise RuntimeError(f'ERROR: platform does not exist for: {name}')

		return platform

	def get_app(self, name: str) -> AppConfig:
		app = self._get_app_cfg_optional(name)

		if app is None:
			#! AppCfg - appCfgDoesNotExist
			raise RuntimeError(f'ERROR: app does not exist for: {name}')

		return app

	# -------------------------------------------------------------------------
	# Other public methods
	# -------------------------------------------------------------------------

	def rebuild_bd(self, name: str) -> None:
		bd_cfg = self._get_bd_cfg_optional(name)

		if bd_cfg is None:
			#! BdCfg - BdCfgAlreadyExists
			raise RuntimeError(f'ERROR: BD entry with name: {name} already exists')

		if os.path.exists(bd_cfg.bd_file):
			bd_cfg.core_list = get_bd_core_list(bd_cfg.bd_file)

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

	def _get_bd_cfg_vlnv_list(self, file: str) -> list[str]:
		if os.path.exists(file):
			with open(file, 'rt') as f:
				match = re.search(r'set\s+list_check_ips\s+"(.*?)"', f.read(), re.DOTALL)

				if match:
					raw = match.group(1)

					return [
						ip for ip in [
							line.strip().rstrip("\\").strip() for line in raw.splitlines()
						] if ip
					]
		return []

	def _get_core_cfg_optional(self, name: str) -> CoreConfig | None:
		return next((i for i in self._core_list if i.name == name), None)

	def _get_design_cfg_optional(self, name: str) -> DesignConfig | None:
		return next((i for i in self._design_list if i.name == name), None)

	def _get_synth_cfg_optional(self,
		design_name: str | None = None,
		core_name: str | None = None,
		bd_name: str | None = None
	) -> SynthConfig | None:
		return next((
				i for i in self._synth_list
				if (bd_name is not None and i.bd_name == bd_name)
				or (design_name is not None and i.design_name == design_name)
				or (core_name is not None and i.core_name == core_name)
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

	def _resolve_fpga(self, fpga_ref: str | None, default_fpga: str | None = None):
		if fpga_ref is None:
			if default_fpga is None:
				fpga_ref = self._get_fpga_cfg_default.name
			else:
				fpga_ref = default_fpga
			# logger.debug(f'fpga is unspecified - using default: {fpga_ref}')
			# logger.debug(f'For Design entry with name: {name} - fpga is unspecified - using default: {fpga_ref}')

		if self._get_fpga_cfg_optional(fpga_ref) is None:
			#! FpgaCfg - FpgaMissing
			raise RuntimeError(f'ERROR: invalid fpga: {fpga_ref}')

		return fpga_ref

	def _resolve_vlnv(self, vlnv: str) -> str:
		for i in self._ip_list:
			if vlnv in i.vlnv:
				return i.vlnv

		entry = self.get_catalog().lookup_optional(vlnv)
		if entry is not None:
			return entry.vlnv

		#! ResolveVLNVFailure
		raise RuntimeError(f'ERROR: unable to resolve VLNV from {vlnv}')

	# -------------------------------------------------------------------------
	# Properties - default getters
	# -------------------------------------------------------------------------

	@property
	def _get_ip_repo_default(self) -> str:
		return self.__path_from_build_dir('ip')

	@property
	def _get_fpga_cfg_default(self) -> FpgaConfig:
		if not self._fpga_list:
			raise RuntimeError('ERROR: No Fpga specified in config')

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