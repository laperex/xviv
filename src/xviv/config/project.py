
import dataclasses
import glob
import logging
import os
import sys
import typing
from xviv.config.catalog import get_catalog
from xviv.config.model import AppConfig, BdConfig, CoreConfig, FpgaConfig, IpConfig, PlatformConfig, SimulationConfig, SynthConfig, VitisConfig, VivadoConfig
from xviv.utils.fs import resolve_globs

logger = logging.getLogger(__name__)

# =============================================================================
# ProjectConfig  -  root object; all callers work with this
# =============================================================================
@dataclasses.dataclass
class ProjectConfig:
	base_dir: str

	fpga_default_ref: str
	fpga_named:   dict[str, FpgaConfig]

	vivado:  VivadoConfig
	vitis:   VitisConfig

	ips:         list[IpConfig]
	bds:         list[BdConfig]
	synths:      list[SynthConfig]
	platforms:   list[PlatformConfig]
	apps:        list[AppConfig]
	cores: 		 list[CoreConfig]
	simulations: list[SimulationConfig]


	@property
	def build_dir(self) -> str:
		return os.path.abspath(os.path.join(self.base_dir, 'build'))

	@property
	def core_dir(self) -> str:
		return os.path.join(self.build_dir, 'core')

	@property
	def bd_dir(self) -> str:
		return os.path.join(self.build_dir, 'bd')

	@property
	def wrapper_dir(self) -> str:
		return os.path.join(self.build_dir, 'wrapper')

	@property
	def synth_dir(self) -> str:
		return os.path.join(self.build_dir, 'synth')


	def get_ip_repos(self) -> list[str]:
		repo_list = []

		for i in self.ips:
			if i.repo not in repo_list:
				repo_list.append(i.repo)

		return repo_list

	# ---- lookup helpers --------------------------------------------------------------------------------------------------------

	def get_ip(self, name: str) -> IpConfig:
		ip = next((i for i in self.ips if i.name == name), None)
		if ip is None:
			sys.exit(
				f"ERROR: IP '{name}' not found in [[ip]] entries.\n"
				f"  Available: {[i.name for i in self.ips]}"
			)
		return ip

	def get_ip_by_vlnv(self, vlnv: str) -> IpConfig:
		ip = next((i for i in self.ips if vlnv in i.vlnv), None)
		if ip is None:
			sys.exit(
				f"ERROR: IP matching vlnv: '{vlnv}' not found in [[ip]] entries.\n"
				f"  Available: {[i.name for i in self.ips]}"
			)
		return ip

	def get_bd(self, name: str) -> BdConfig:
		bd = next((b for b in self.bds if b.name == name), None)
		if bd is None:
			sys.exit(
				f"ERROR: BD '{name}' not found in [[bd]] entries.\n"
				f"  Available: {[b.name for b in self.bds]}"
			)
		return bd

	def get_core(self, name: str) -> CoreConfig:
		core = next((b for b in self.cores if b.name == name), None)
		if core is None:
			sys.exit(
				f"ERROR: Core '{name}' not found in [[core]] entries.\n"
				f"  Available: {[b.name for b in self.cores]}"
			)
		return core

	def get_synth(self, *, top_name: typing.Optional[str] = None, bd_name: typing.Optional[str] = None, ip_name: typing.Optional[str] = None) -> SynthConfig:
		s = next(
			(
				s for s in self.synths
				if (top_name is not None and s.top == top_name) or
				(ip_name is not None and s.ip == ip_name) or
				(bd_name is not None and s.bd == bd_name)
			),
			None
		)

		if bd_name:
			self.get_bd(bd_name)
		elif ip_name:
			self.get_ip(ip_name)

		# Handle the failure cases
		if s is None:
			# If 'top_name' was provided and we failed to find it, throw the error
			if top_name is not None:
				avail_tops = [s.top for s in self.synths if s.top is not None]
				sys.exit(
					f"ERROR: Synthesis top '{top_name}' not found in [[synthesis]] entries.\n"
					f"  Available tops: {avail_tops}"
				)

			return SynthConfig(top="", ip=ip_name or "", bd=bd_name or "")

		return s

	def get_catalog(self):
		return get_catalog(self.vivado.path, self.get_ip_repos())

	def get_simulation(self, top_name: str) -> SimulationConfig:
		p = next((p for p in self.simulations if p.top == top_name), None)
		if p is None:
			sys.exit(
				f"ERROR: simulation '{top_name}' not found in [[simulation]] entries.\n"
				f"  Available: {[p.top for p in self.simulations]}"
			)
		return p

	def get_platform(self, name: str) -> PlatformConfig:
		p = next((p for p in self.platforms if p.name == name), None)
		if p is None:
			sys.exit(
				f"ERROR: Platform '{name}' not found in [[platform]] entries.\n"
				f"  Available: {[p.name for p in self.platforms]}"
			)
		return p

	def get_app(self, name: str) -> AppConfig:
		a = next((a for a in self.apps if a.name == name), None)
		if a is None:
			sys.exit(
				f"ERROR: App '{name}' not found in [[app]] entries.\n"
				f"  Available: {[a.name for a in self.apps]}"
			)
		return a

	def resolve_fpga(self, ref: typing.Optional[str] = None) -> FpgaConfig:
		ref = ref or self.fpga_default_ref

		if ref:
			fpga = self.fpga_named.get(ref)
			if fpga is None:
				sys.exit(
					f"ERROR: FPGA target '{ref}' not found in [fpga.*] tables.\n"
					f"  Available: {list(self.fpga_named.keys())}"
				)
			return fpga

		return list(self.fpga_named.values())[0]

	# ---- path helpers ------------------------------------------------------------------------------------------------------------

	def abs_path(self, rel: str) -> str:
		return os.path.abspath(os.path.join(self.base_dir, rel))

	def resolve_globs(self, patterns: list[str]) -> list[str]:
		return resolve_globs(patterns, self.base_dir)

	def get_dcp_path(self, top: str, dcp_name: str) -> str:
		return os.path.abspath(os.path.join(self.build_dir, "synth", top, f"{dcp_name}.dcp"))

	def get_bd_ooc_targets_dir(self, bd_name: str) -> str:
		return os.path.abspath(os.path.join(self.build_dir, 'synth_ooc', 'bd', bd_name))

	def get_control_fifo_path(self, top: str) -> str:
		return os.path.join(self.build_dir, "xviv", top, "control.fifo")

	def get_xlib_work_dir(self, top: str) -> str:
		return os.path.join(self.build_dir, "elab", top)

	def get_platform_dir(self, name: str) -> str:
		return os.path.join(self.build_dir, "bsp", name)

	def get_app_dir(self, name: str) -> str:
		app_dir = os.path.join(self.build_dir, "app", name)
		if not os.path.isdir(app_dir):
			sys.exit(
				f"ERROR: App directory not found: {app_dir}\n"
				f"  Run: xviv create --app {name}"
			)
		return app_dir

	def get_platform_paths(self, name: str) -> tuple[str, str]:
		"""Return (xsa_path, bitstream_path) for a platform."""
		plat = self.get_platform(name)

		if plat.xsa:
			xsa = self.abs_path(plat.xsa)
			stem = os.path.splitext(xsa)[0]
			bit = stem + ".bit"
			if not os.path.exists(bit):
				candidates = sorted(glob.glob(os.path.join(os.path.dirname(xsa), "*.bit")))
				if candidates:
					bit = candidates[0]
					logger.debug("Bitstream resolved via glob: %s", bit)
			return xsa, bit

		if plat.synth_top:
			synth_dir = os.path.join(self.build_dir, "synth", plat.synth_top)
			return (
				os.path.join(synth_dir, f"{plat.synth_top}.xsa"),
				os.path.join(synth_dir, f"{plat.synth_top}.bit"),
			)

		sys.exit(
			f"ERROR: Platform '{name}' must specify either 'xsa' or 'synth_top' in project.toml."
		)