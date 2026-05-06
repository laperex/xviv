
import dataclasses
import glob
import logging
import os
import re
import sys
import typing
from xviv.config.catalog import Catalog, get_catalog
from xviv.config.model import AppConfig, BdConfig, CoreConfig, DesignConfig, FpgaConfig, IpConfig, PlatformConfig, SimulationConfig, SynthConfig, VitisConfig, VivadoConfig, WrapperConfig
from xviv.utils.fs import resolve_globs

logger = logging.getLogger(__name__)

# =============================================================================
# ProjectConfig  -  root object; all callers work with this
# =====================================
class XvivConfig:
	def __init__(self, config_file_path: str, work_dir: str, board_repo_list: list[str] = [], ip_repo_list: list[str] = []):
		self.base_dir = os.path.abspath(os.path.dirname(config_file_path))
		self.work_dir = os.path.join(self.base_dir, work_dir)

		os.makedirs(self.work_dir, exist_ok=True)

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
		self._wrapper_list: list[WrapperConfig] = []

		self._bd_list: list[BdConfig] = []

		self._core_list: list[CoreConfig] = []

		self._design_list: list[DesignConfig] = []

		self._synth_list: list[SynthConfig] = []

		self._vivado_cfg: VivadoConfig | None = None
		self._vitis_cfg: VitisConfig | None = None

		self._catalog_cfg: Catalog | None = None


	def get_catalog(self) -> Catalog:
		if self._catalog_cfg:
			return self._catalog_cfg

		#! UninitializedCoreCatalog
		sys.exit('ERROR: Catalog is not initialized')

	def get_vivado(self) -> VivadoConfig:
		if self._vivado_cfg:
			return self._vivado_cfg

		#! UninitializedVivadoCfg
		sys.exit('ERROR: VivadoConfig is not initialized')

	def get_vitis(self) -> VitisConfig:
		if self._vitis_cfg:
			return self._vitis_cfg

		#! UninitializedVitisCfg
		sys.exit('ERROR: VitisConfig is not initialized')


	def add_vivado_cfg(self,
		path: str,
		mode: str = 'batch',
		max_threads: int = 10,
		hw_server: str = 'localhost:3121'
	) -> typing.Self:
		if self._vivado_cfg is not None:
			#! VivadoCfg - VivadoCfgAlreadySpecified
			sys.exit('ERROR: Vivado Config Already Specified')

		if not os.path.exists(path):
			#! VivadoCfg - InvalidPath
			sys.exit(f'ERROR: Invadlid Vivado Path: {path}')

		self._vivado_cfg = VivadoConfig(
			path=path,
			mode=mode,
			max_threads=max_threads,
			hw_server=hw_server
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
			sys.exit('ERROR: Vitis Config Already Specified')

		if not os.path.exists(path):
			#! VitisCfg - InvalidPath
			sys.exit(f'ERROR: Invadlid Vitis Path: {path}')

		return self


	def add_ip_cfg(self, name: str, *,
		vendor: str = 'xviv.org',
		library: str = 'xviv',
		version: str = '1.0',

		top: str | None = None,
		sources: list[str] = [],

		vlnv: str | None = None,
		repo: str | None = None,
	) -> typing.Self:
		if self._get_ip_cfg_optional(name) is not None:
			#! IpCfg - IpCfgAlreadyExistsError
			sys.exit(f'ERROR: IP entry with name: {name} already exists')

		# TODO: throw error for invalid name ''

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
				sources=sources
			)
		)

		return self

	@property
	def _get_ip_repo_default(self) -> str:
		return self.__path_from_build_dir('ip')

	def _get_ip_cfg_optional(self, name: str) -> IpConfig | None:
		return next((i for i in self._ip_list if i.name == name), None)

	def get_ip(self, name: str) -> IpConfig:
		ip = self._get_ip_cfg_optional(name)

		if ip is None:
			#! IpCfg - IpCfgDoesNotExist
			sys.exit(f'ERROR: IP does not exist for: {name}')

		return ip


	def add_wrapper_cfg(self, *,
		ip_name: str,
		sources: list[str],
		wrapper_file: str | None = None
	) -> typing.Self:
		if self._get_wrapper_cfg_optional(ip_name) is not None:
			#! WrapperCfg - WrapperCfgAlreadyExistsForIpError
			sys.exit(f'ERROR: Wrapper entry with name: {ip_name} already exists')

		ip_cfg = self._get_ip_cfg_optional(ip_name)

		if ip_cfg is None:
			#! WrapperCfg - IpCfgMissingError
			sys.exit(f'ERROR: IP entry with name: {ip_name} does not exist')

		if not sources:
			#! WrapperCfg - UnspecifiedSourcesError
			sys.exit(f'ERROR: sources not specified, empty: {sources}')

		for i in sources:
			if not os.path.exists(i):
				#! WrapperCfg - SourceMissingError
				sys.exit(f'ERROR: required source does not exist: {i}')

		if wrapper_file is None:
			# TODO: default ip wrapper file
			wrapper_file = os.path.join(self.wrapper_dir, f"{ip_cfg.top}_wrapper.v")

		self._wrapper_list.append(
			WrapperConfig(
				ip_name=ip_name,
				wrapper_file=wrapper_file,
				sources=sources
			)
		)

		return self

	def _get_wrapper_cfg_optional(self, name: str) -> WrapperConfig | None:
		return next((i for i in self._wrapper_list if i.ip_name == name), None)

	def get_wrapper(self, name: str) -> WrapperConfig:
		wrapper = self._get_wrapper_cfg_optional(name)

		if wrapper is None:
			#! wrapperCfg - wrapperCfgDoesNotExist
			sys.exit(f'ERROR: wrapper does not exist for: {name}')

		return wrapper


	def add_fpga_cfg(self, name: str, *,
		fpga_part: str | None = None,
		board_part: str | None = None
	) -> typing.Self:
		if self._get_fpga_cfg_optional(name) is not None:
			#! FpgaCfg - FpgaCfgAlreadyExists
			sys.exit(f'ERROR: Fpga entry with name: {name} already exists')

		# TODO: throw error for invalid name ''

		if fpga_part is None and board_part is None:
			#! FpgaCfg - PartUnspecified
			sys.exit(f'ERROR: part unspecified for fpga entry: {name}')

		self._fpga_list.append(
			FpgaConfig(
				name=name,
				fpga_part=fpga_part,
				board_part=board_part
			)
		)

		return self

	def _get_fpga_cfg_optional(self, name: str) -> FpgaConfig | None:
		return next((i for i in self._fpga_list if i.name == name), None)

	@property
	def _get_fpga_cfg_default(self) -> FpgaConfig:
		if not self._fpga_list:
			sys.exit('ERROR: No Fpga specified in config')

		return self._fpga_list[0]

	def get_fpga(self, name: str | None) -> FpgaConfig:
		if name is None:
			return self._get_fpga_cfg_default

		fpga = self._get_fpga_cfg_optional(name)

		if fpga is None:
			#! FpgaCfg - FpgaCfgDoesNotExist
			sys.exit(f'ERROR: Fpga does not exist for: {name}')

		return fpga


	def add_bd_cfg(self, name: str, *,
		save_tcl_file: str | None = None,
		fpga_ref: str | None = None
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_bd_cfg_optional(name) is not None:
			#! BdCfg - BdCfgAlreadyExists
			sys.exit(f'ERROR: BD entry with name: {name} already exists')


		if fpga_ref is None:
			fpga_ref = self._get_fpga_cfg_default.name
			logger.warning(f'For BD entry with name: {name} - fpga is unspecified - using default: {fpga_ref}')

		if self._get_fpga_cfg_optional(fpga_ref) is None:
			#! BdCfg - BdCfgAlreadyExists
			sys.exit(f'ERROR: for BD entry with name: {name} - invalid fpga: {fpga_ref}')

		if save_tcl_file is None:
			save_tcl_file = os.path.join(self.scripts_dir, f'{name}.tcl')

		self._bd_list.append(
			BdConfig(
				name=name,
				save_tcl_file=save_tcl_file,
				vlnv_list=self._get_bd_cfg_vlnv_list(save_tcl_file),
				fpga_ref=fpga_ref,

				# TODO
				core_list=[]
			)
		)

		return self

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

	def get_bd(self, name: str) -> BdConfig:
		bd = self._get_bd_cfg_optional(name)

		if bd is None:
			#! BDCfg - BDCfgDoesNotExist
			sys.exit(f'ERROR: BD does not exist for: {name}')

		return bd


	def add_design_cfg(self, name: str, *,
		sources: list[str],
		top: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_design_cfg_optional(name) is not None:
			#! DesignCfg - DesignCfgAlreadyExists
			sys.exit(f'ERROR: design entry with name: {name} already exists')

		if top is None:
			top = name

		self._design_list.append(
			DesignConfig(
				name=name,
				top=top,
				sources=sources
			)
		)

		return self

	def _get_design_cfg_optional(self, name: str) -> DesignConfig | None:
		return next((i for i in self._design_list if i.name == name), None)

	def get_design(self, name: str) -> DesignConfig:
		design = self._get_design_cfg_optional(name)

		if design is None:
			#! DesignCfg - DesignCfgDoesNotExist
			sys.exit(f'ERROR: Design does not exist for: {name}')

		return design


	def add_core_cfg(self, name: str, *,
		vlnv: str,
		xci_file: str | None = None,
		fpga_ref: str | None = None,
	) -> typing.Self:
		# TODO: throw error for invalid name ''

		if self._get_core_cfg_optional(name) is not None:
			#! CoreCfg - CoreCfgAlreadyExists
			sys.exit(f'ERROR: core entry with name: {name} already exists')

		if xci_file is None:
			xci_file = os.path.join(self.core_dir, name, f'{name}.xci')

		if fpga_ref is None:
			fpga_ref = self._get_fpga_cfg_default.name
			logger.warning(f'For Core entry with name: {name} - fpga is unspecified - using default: {fpga_ref}')

		prev_vlnv = vlnv
		vlnv = self._resolve_vlnv(vlnv)
		if prev_vlnv != vlnv:
			logger.warning(f'For Core entry with name: {name} - vlnv resolved to: {vlnv}')

		self._core_list.append(
			CoreConfig(
				name=name,
				vlnv=vlnv,
				xci_file=xci_file,
				fpga_ref=fpga_ref
			)
		)

		return self

	def _get_core_cfg_optional(self, name: str) -> CoreConfig | None:
		return next((i for i in self._core_list if i.name == name), None)

	def get_core(self, name: str) -> CoreConfig:
		core = self._get_core_cfg_optional(name)

		if core is None:
			#! CoreCfg - CoreCfgDoesNotExist
			sys.exit(f'ERROR: Core does not exist for: {name}')

		return core


	def add_synth_cfg(self, *,
		design_name: str | None = None,
		core_name: str | None = None,
		bd_name: str | None = None,
		fpga_ref: str | None = None,
		constraints: list[str] = []
	) -> typing.Self:
		available_ids = [i for i in [design_name, core_name, bd_name] if i]

		if len(available_ids) == 0:
			#! SynthCfg - UnspecifiedIdentifier
			sys.exit('ERROR: need to specify at least one - bd, ip, design')

		if len(available_ids) != 1:
			#! SynthCfg - MultipleIdSpecified
			sys.exit(f'ERROR: multiple ids specified: {' '.join(available_ids)}')

		if self._get_synth_cfg_optional(design_name=design_name, core_name=core_name, bd_name=bd_name) is not None:
			#! SynthCfg - SynthCfgAlreadyExists
			sys.exit(f'ERROR: SynthConfig Already Exists for id: {available_ids}')

		if bd_name:
			bd_cfg = self._get_bd_cfg_optional(bd_name)
			if bd_cfg is None:
				#! SynthCfg - MultipleIdSpecified
				#! SynthCfgCfg - SynthCfgCfgDoesNotExist
				sys.exit(f'ERROR: SynthCfg - BD does not exist for name: {bd_name}')

			if fpga_ref is None:
				fpga_ref = bd_cfg.fpga_ref
			else:
				if fpga_ref != bd_cfg.fpga_ref:
					#! SynthCfg - FpgaRefMismatch
					sys.exit(f'ERROR: Mismatch fpga for BD: {bd_cfg.fpga_ref} with specified: {fpga_ref}')

		if core_name:
			pass

		if design_name:
			pass

		if fpga_ref is None:
			#! SynthCfg - UnspecifiedFpga
			sys.exit(f'ERROR: unspecified fpga for synth target - {available_ids}')

		self._synth_list.append(
			SynthConfig(
				design_name=design_name,
				core_name=core_name,
				bd_name=bd_name,
				fpga_ref=fpga_ref,
				constraints=constraints
			)
		)

		return self

	def _get_synth_cfg_optional(self,
		design_name: str | None = None,
		core_name: str | None = None,
		bd_name: str | None = None
	) -> SynthConfig | None:
		return next((i for i in self._synth_list if (i.bd_name == bd_name) or (i.design_name == design_name) or (i.core_name == core_name)), None)

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
			sys.exit(f'ERROR: Synth does not exist for: [{design_name or ''}{core_name or ''}{bd_name or ''}]')

		return synth

	# helpers

	def __path_from_build_dir(self, path: str):
		return os.path.join(self.work_dir, path)

	def __path_from_base_dir(self, path: str):
		return os.path.join(self.base_dir, path)

	# @property
	# def build_dir(self):
	# 	return self.work_dir

	@property
	def wrapper_dir(self):
		return self.__path_from_build_dir('wrapper')

	@property
	def core_dir(self):
		return self.__path_from_build_dir('core')

	@property
	def bd_dir(self):
		return self.__path_from_build_dir('bd')

	@property
	def scripts_dir(self):
		return self.__path_from_base_dir(os.path.join('scripts', 'xviv'))

	def _resolve_vlnv(self, vlnv: str) -> str:
		for i in self._ip_list:
			if vlnv in i.vlnv:
				return i.vlnv
		
		entry = self.get_catalog().lookup_optional(vlnv)
		if entry is not None:
			return entry.vlnv
		
		#! ResolveVLNVFailure
		sys.exit(f'ERROR: unable to resolve VLNV from {vlnv}')