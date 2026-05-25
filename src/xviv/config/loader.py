from __future__ import annotations

import os
import sys
import tomllib

from xviv.config.project import XvivConfig
from xviv.utils import error
from xviv.utils.tools import find_vitis_dir_path, find_vivado_dir_path


def resolve_config_completer(prefix, parsed_args, **kwargs) -> str:
	return resolve_config(getattr(parsed_args, "config", ""))


def resolve_config(explicit: str) -> str:
	if os.path.exists(explicit):
		return explicit

	for candidate in ["project.toml"]:
		if os.path.exists(candidate):
			return candidate

	raise error.ProjectConfigTomlFileMissingError()


def load_config(path: str) -> XvivConfig:
	with open(path, "rb") as f:
		data = tomllib.load(f)

	cfg = XvivConfig(
		path,
		data["project"].get("build_dir", None),
		data["project"].get("board_repo_paths", []),
	)

	cfg = (
		cfg.add_vivado_cfg(path=find_vivado_dir_path(False))
		.add_vitis_cfg(path=find_vitis_dir_path(False))
	)

	for key, entries in data.items():
		if key == "project":
			continue

		if not isinstance(entries, list):
			entries = [entries]

		for entry in entries:
			match key:
				case "fpga":
					cfg.add_fpga_cfg(**entry)
				case "ip":
					cfg.add_ip_cfg(**entry)
				case "wrapper":
					cfg.add_wrapper_cfg(**entry)
				case "core":
					cfg.add_core_cfg(**entry)
				case "bd":
					cfg.add_bd_cfg(**entry)
				case "design":
					cfg.add_design_cfg(**entry)
				case "simulation":
					cfg.add_sim_cfg(**entry)
				case "subcore":
					cfg.add_subcore_cfg(**entry)
				case "synth":
					cfg.add_synth_cfg(**entry)
				case "platform":
					cfg.add_platform_cfg(**entry)
				case "app":
					cfg.add_app_cfg(**entry)
				case "formal":
					cfg.add_formal_cfg(**entry)
				case "uvm":
					cfg.add_uvm_cfg(**entry)
				case _:
					raise error.ProjectConfigUnknownKeyError(key, path)

	return cfg
