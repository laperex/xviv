from __future__ import annotations

import logging
import os
import shutil

from xviv.config.loader import resolve_config_completer, load_config
from xviv.catalog.catalog import Catalog, get_catalog
from xviv.tools.util import find_vivado_dir_path

logger = logging.getLogger(__name__)

def _term_width() -> int:
	return shutil.get_terminal_size().columns * 2

def _build_catalog(prefix, parsed_args) -> Catalog:
	vivado_path = find_vivado_dir_path()
	ip_repos: list[str] = []
	
	try:
		cfg = load_config(os.path.abspath(resolve_config_completer(prefix, parsed_args)))
		
		if cfg.ip_repo:
			ip_repos = [cfg.ip_repo]
	except Exception as exc:
		logger.debug("ip_repo scan skipped: %s", exc)
	return get_catalog(vivado_path, ip_repos)


# --- Completer 1: --core NAME ---
def core_instance_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
	try:
		comp_line = os.environ.get("COMP_LINE", "")
		comp_point = int(os.environ.get("COMP_POINT", len(comp_line)))
		tokens = comp_line[:comp_point].split()
		real_prefix = tokens[-1] if tokens else prefix

		catalog = _build_catalog(prefix, parsed_args)

		completions: dict[str, str] = {}

		for vlnv, entry in catalog.items():
			name_ver = f"{entry.name}:{entry.version}"
			desc = _fmt_instance_desc(vlnv, entry)

			if name_ver.startswith(real_prefix):
				completions[name_ver] = desc
			else:
				completions[vlnv] = desc
		return completions
	except Exception as exc:
		logger.debug("_core_instance_completer failed: %s", exc)
		return {}


def _fmt_instance_desc(vlnv: str, entry) -> str:
	parts = [vlnv, entry.display_name]
	flags = []
	if entry.hidden:
		flags.append("⚠ internal")
	if entry.board_dependent:
		flags.append("⚠ board-dep")
	if entry.ipi_only:
		flags.append("⚠ IPI-only")
	if flags:
		parts.append("  ".join(flags))
	desc_text = " ".join(entry.description.split())
	avail = _term_width() - sum(len(p) + 2 for p in parts)
	if avail > 10 and desc_text:
		if len(desc_text) > avail:
			desc_text = desc_text[:avail - 1] + "…"
		parts.append(f"— {desc_text}")
	return "  ".join(parts)
