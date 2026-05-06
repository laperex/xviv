
import dataclasses
import glob
import logging
import os
import sys
import typing
from xviv.config.catalog import get_catalog
from xviv.config.model import AppConfig, BdConfig, CoreConfig, FpgaConfig, IpConfig, PlatformConfig, SimulationConfig, SynthConfig, VitisConfig, VivadoConfig, WrapperConfig
from xviv.utils.fs import resolve_globs

logger = logging.getLogger(__name__)

# =============================================================================
# ProjectConfig  -  root object; all callers work with this
# =====================================
class XvivConfig:
	def __init__(self, work_dir: str, board_repo_list: list[str] = []):
		self.work_dir = os.path.abspath(work_dir)

		self.board_repo_list: list[str] = []
		
		os.makedirs(self.work_dir, exist_ok=True)
		
		for path in board_repo_list:
			if os.path.isdir(path):
				self.board_repo_list.append(path)

		# lists
		self._ip_list: list[IpConfig] = []
		self._bd_list: list[BdConfig] = []
		self._wrapper_list: list[WrapperConfig] = []


	def add_ip_cfg(self, name: str, *,
		vendor: str = 'xviv.org',
		library: str = 'xviv',
		version: str = '1.0',

		top: str | None = None, 
		sources: list[str] = [],

		vlnv: str | None = None,
		repo: str | None = None,
	) -> typing.Self:
		if vlnv is None:
			vlnv = f"{vendor}:{library}:{name}:{version}"

		if repo is None:
			repo = self._path_from_build_dir('ip')

		if os.path.exists(repo):
			os.makedirs(repo, exist_ok=True)

		if top is None:
			logger.warning(f'top unspecified for ip_cfg: {name} - defaulting to {name}')
			top = name

		if self._get_ip_cfg_optional(name) is not None:
			#! IpCfg - IpCfgAlreadyExistsError
			sys.exit(f'ERROR: IP entry with name: {name} already exists')

		self._ip_list.append(
			IpConfig(
				name=name,
				repo=repo,
				top=top,
				vendor=vendor,
				library=library,
				version=version,
				sources=sources
			)
		)

		return self

	def _get_ip_cfg_optional(self, name) -> IpConfig | None:
		return next((i for i in self._ip_list if i.name == name), None)


	def add_wrapper_cfg(self, *,
		ip_name: str,
		sources: list[str],
		wrapper_file: str | None = None
	) -> typing.Self:
		if not sources:
			#! WrapperCfg - UnspecifiedSourcesError
			sys.exit(f'ERROR: sources not specified, empty: {sources}')

		for i in sources:
			if not os.path.exists(i):
				#! WrapperCfg - SourceMissingError
				sys.exit(f'ERROR: required source does not exist: {i}')

		ip_cfg = self._get_ip_cfg_optional(ip_name)

		if ip_cfg is None:
			#! WrapperCfg - IpCfgMissingError
			sys.exit(f'ERROR: IP entry with name: {ip_name} does not exist')

		if wrapper_file is None:
			# TODO: default ip wrapper file
			wrapper_file = self.wrapper_dir() / f"{ip_cfg.top}_wrapper.v"

		if self._get_wrapper_cfg_optional(ip_name) is not None:
			#! WrapperCfg - WrapperCfgAlreadyExistsForIpError
			sys.exit(f'ERROR: Wrapper entry with name: {ip_name} already exists')


		self._wrapper_list.append(
			WrapperConfig(
				ip_name=ip_name,
				wrapper_file=wrapper_file,
				sources=sources
			)
		)

		return self

	def _get_wrapper_cfg_optional(self, name) -> WrapperConfig | None:
		return next((i for i in self._wrapper_list if i.ip_name == name), None)


	def _path_from_build_dir(self, path: str):
		return os.path.join(self.work_dir, path)


	@property
	def wrapper_dir(self):
		return self._path_from_build_dir('wrapper')
	
	
	# build_dir: str

	# fpga_named:   dict[str, FpgaConfig]

	# vivado:  VivadoConfig
	# vitis:   VitisConfig

	# ips:         list[IpConfig]
	# bds:         list[BdConfig]
	# cores: 		 list[CoreConfig]
	# synths:      list[SynthConfig]
	# platforms:   list[PlatformConfig]
	# apps:        list[AppConfig]
	# simulations: list[SimulationConfig]

	# def set_build_dir(self, build_dir: str):
	# 	if os.path.isdir(build_dir):
	# 		os.makedirs(build_dir, exist_ok=True)

	# 	self.build_dir = os.path.abspath(build_dir)


	# @property
	# def core_dir(self) -> str:
	# 	return os.path.join(self.build_dir, 'core')

	# @property
	# def bd_dir(self) -> str:
	# 	return os.path.join(self.build_dir, 'bd')

	# @property
	# def wrapper_dir(self) -> str:
	# 	return os.path.join(self.build_dir, 'wrapper')

	# @property
	# def synth_dir(self) -> str:
	# 	return os.path.join(self.build_dir, 'synth')


	# def get_ip_repos(self) -> list[str]:
	# 	repo_list = []

	# 	for i in self.ips:
	# 		if i.repo not in repo_list:
	# 			repo_list.append(i.repo)

	# 	return repo_list

	# # ---- lookup helpers --------------------------------------------------------------------------------------------------------
	# def get_ip(self, name: str) -> IpConfig:
	# 	ip = next((i for i in self.ips if i.name == name), None)
	# 	if ip is None:
	# 		sys.exit(
	# 			f"ERROR: IP '{name}' not found in [[ip]] entries.\n"
	# 			f"  Available: {[i.name for i in self.ips]}"
	# 		)
	# 	return ip

	# def get_ip_by_vlnv(self, vlnv: str) -> IpConfig:
	# 	ip = next((i for i in self.ips if vlnv in i.vlnv), None)
	# 	if ip is None:
	# 		sys.exit(
	# 			f"ERROR: IP matching vlnv: '{vlnv}' not found in [[ip]] entries.\n"
	# 			f"  Available: {[i.name for i in self.ips]}"
	# 		)
	# 	return ip

	# def get_bd(self, name: str) -> BdConfig:
	# 	bd = next((b for b in self.bds if b.name == name), None)
	# 	if bd is None:
	# 		sys.exit(
	# 			f"ERROR: BD '{name}' not found in [[bd]] entries.\n"
	# 			f"  Available: {[b.name for b in self.bds]}"
	# 		)
	# 	return bd

	# def get_core(self, name: str) -> CoreConfig:
	# 	core = next((b for b in self.cores if b.name == name), None)
	# 	if core is None:
	# 		sys.exit(
	# 			f"ERROR: Core '{name}' not found in [[core]] entries.\n"
	# 			f"  Available: {[b.name for b in self.cores]}"
	# 		)
	# 	return core
