"""
config.py  -  Project configuration for xviv
=============================================

Architecture
------------
The TOML file is parsed ONCE in load_config() into a ProjectConfig dataclass
tree.  Every raw dict key access (i.e., every reference to the TOML schema)
is confined to the _parse_* functions below.  If a TOML key is renamed or
restructured, only those functions need to change.

Callers receive a ProjectConfig and work with typed attributes:
	cfg.vivado.path
	cfg.get_ip("my_ip").vendor
	cfg.build_dir          # resolved absolute path property
	...

generate_config_tcl() is the only place that maps Python config -> TCL globals.
If a new TCL variable is needed, add it there (and nowhere else).
"""

from __future__ import annotations

import dataclasses
import glob
import json
import logging
import os
import subprocess
import sys
import tomllib
import typing

logger = logging.getLogger(__name__)








# =============================================================================
# Public entry-point
# =============================================================================






# =============================================================================
# Internal helpers
# =============================================================================
