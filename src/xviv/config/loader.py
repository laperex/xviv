from __future__ import annotations

import os
import tomllib

from xviv.config.project import XvivConfig
from xviv.utils import error
from xviv.utils.tools import find_vitis_dir_path, find_vivado_dir_path


def resolve_config_completer(prefix, parsed_args, **kwargs) -> str:
	return resolve_config(getattr(parsed_args, "config", None))


def resolve_config(explicit: str | None = None) -> str:
	if explicit:
		if os.path.exists(explicit):
			return explicit
	else:
		for candidate in ["project.toml"]:
			if os.path.exists(candidate):
				return candidate

	raise error.ProjectConfigTomlFileMissingError()


def load_config(path: str) -> XvivConfig:
	with open(path, "rb") as f:
		data = tomllib.load(f)

	cfg = XvivConfig(project_file=path, **data.get("project", {}))
	cfg = cfg.add_vivado_cfg(path=find_vivado_dir_path(False)).add_vitis_cfg(path=find_vitis_dir_path(False))

	fpga_list = data.get("fpga", [])
	core_list = data.get("core", [])
	ip_list = data.get("ip", [])
	wrapper_list = data.get("wrapper", [])
	subcore_list = data.get("subcore", [])
	synth_list = data.get("synth", [])
	bd_list = data.get("bd", [])
	design_list = data.get("design", [])
	platform_list = data.get("platform", [])
	app_list = data.get("app", [])
	sim_list = data.get("simulation", [])
	uvm_list = data.get("uvm", [])
	formal_list = data.get("formal", [])

	# 1. fpga
	for entry in fpga_list:
		cfg.add_fpga_cfg(**entry)

	# 2. ip
	for entry in ip_list:
		cfg.add_ip_cfg(**entry)

	# 3. wrapper
	for entry in wrapper_list:
		cfg.add_wrapper_cfg(**entry)

	# 4. core
	for entry in core_list:
		cfg.add_core_cfg(**entry)

	# 5. subcore (bd only)
	for entry in subcore_list:
		if entry.get("bd") is not None:
			cfg.add_subcore_cfg(**entry)

	# 6. synth (core only)
	for entry in synth_list:
		if entry.get("core") is not None:
			cfg.add_synth_cfg(**entry)

	# 7. bd
	for entry in bd_list:
		cfg.add_bd_cfg(**entry)

	# 8. design
	for entry in design_list:
		cfg.add_design_cfg(**entry)

	# 9. subcore (design only, bd is None)
	for entry in subcore_list:
		if entry.get("bd") is None:
			cfg.add_subcore_cfg(**entry)

	# 10. synth (bd/design only, core is None)
	for entry in synth_list:
		if entry.get("core") is None:
			cfg.add_synth_cfg(**entry)

	# 11. platform
	for entry in platform_list:
		cfg.add_platform_cfg(**entry)

	# 12. app
	for entry in app_list:
		cfg.add_app_cfg(**entry)

	# 13. simulation
	for entry in sim_list:
		cfg.add_sim_cfg(**entry)

	# 14. uvm
	for entry in uvm_list:
		cfg.add_uvm_cfg(**entry)

	# 15. formal
	for entry in formal_list:
		cfg.add_formal_cfg(**entry)

	unknown_keys = set(data.keys()) - {
		"project",
		"fpga",
		"core",
		"ip",
		"wrapper",
		"subcore",
		"synth",
		"bd",
		"design",
		"platform",
		"app",
		"simulation",
		"uvm",
		"formal",
	}
	for key in unknown_keys:
		raise error.ProjectConfigUnknownKeyError(key, path)

	return cfg
