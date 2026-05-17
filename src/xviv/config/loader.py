
import json
import os
import subprocess
import sys

import tomllib

from xviv.config import model
from xviv.config.project import XvivConfig
from xviv.config.sections import get_sections
from xviv.utils.tools import find_vitis_dir_path, find_vivado_dir_path


def resolve_config_completer(prefix, parsed_args, **kwargs) -> str:
	return resolve_config(getattr(parsed_args, "config", ""))

def resolve_config(explicit: str) -> str:
	if os.path.exists(explicit):
		return explicit
	for candidate in ["project.toml"]:
		if os.path.exists(candidate):
			return candidate

	#! ConfigTomlNotFound
	raise RuntimeError("ERROR: project.toml not found in current directory.")

def load_config(path: str) -> XvivConfig:
    with open(path, 'rb') as f:
        data = tomllib.load(f)

    cfg = (
        XvivConfig(
			path,
			data['project'].get('build_dir', None),
			data['project'].get('board_repo_paths', []),
		)
        .add_vivado_cfg(path=find_vivado_dir_path())
        .add_vitis_cfg(path=find_vitis_dir_path())
    )

    for spec in get_sections():
        method = getattr(cfg, spec.add_method)
        for entry in data.get(spec.toml_key, []):
            method(**entry)

    return cfg