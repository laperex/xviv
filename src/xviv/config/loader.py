
import json
import os
import subprocess
import sys

import tomllib

from xviv.config import model
from xviv.config.project import XvivConfig
from xviv.utils.tools import find_vivado_dir_path


def resolve_config_completer(prefix, parsed_args, **kwargs) -> str:
	return resolve_config(getattr(parsed_args, "config", ""))

def resolve_config(explicit: str) -> str:
	if os.path.exists(explicit):
		return explicit
	for candidate in ("project.cue", "project.toml"):
		if os.path.exists(candidate):
			return candidate
	sys.exit("ERROR: neither project.cue nor project.toml found in current directory.")

def load_config(path: str) -> XvivConfig:
    with open(path, 'rb') as f:
        data = tomllib.load(f)

    cfg = XvivConfig(
        path,
        data['project']['build_dir'],
        data['project']['board_repo_paths']
    ).add_vivado_cfg(path=find_vivado_dir_path())

    for section, method in [
        ('fpga',    cfg.add_fpga_cfg),
        ('ip',      cfg.add_ip_cfg),
        ('wrapper', cfg.add_wrapper_cfg),
        ('core',    cfg.add_core_cfg),
        ('bd',      cfg.add_bd_cfg),
        ('synth',   cfg.add_synth_cfg),
    ]:
        for entry in data.get(section, []):
            method(**entry)

    return cfg
