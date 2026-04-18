"""
core_catalog.py
===============
Parse Vivado's vv_index.xml into an in-memory catalog.

Used by:
  - _core_vlnv_completer()  → tab completion with rich descriptions
  - _validate_cores()        → pre-flight checks at load_config() time
  - cmd_core_create()        → pre-flight before launching Vivado

The XML lives at:  <vivado_path>/data/ip/vv_index.xml
It is parsed once per process per Vivado installation and cached.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum description length shown in tab completion
_DESC_MAX = 72


# =============================================================================
# Data model
# =============================================================================

@dataclasses.dataclass(frozen=True)
class CoreEntry:
	vlnv:                 str               # "xilinx.com:ip:fifo_generator:13.2"
	vendor:               str               # "xilinx.com"
	library:              str               # "ip"
	name:                 str               # "fifo_generator"
	version:              str               # "13.2"
	display_name:         str               # "FIFO Generator"
	description:          str               # full description text
	hidden:               bool              # HideInGui="true"  → internal subcore
	board_dependent:      bool              # BoardDependent="true"
	ipi_only:             bool              # only DesignTool=IPI listed
	unsupported_families: frozenset[str]    # families with status=Not-Supported
	upgrades_from:        tuple[str, ...]   # older VLNVs this supersedes

	@property
	def short_desc(self) -> str:
		"""
		One-line description suitable for terminal display.
		Truncates long descriptions and strips embedded newlines.
		"""
		text = " ".join(self.description.split())   # collapse whitespace
		if len(text) > _DESC_MAX:
			text = text[:_DESC_MAX - 1] + "…"
		return text

	@property
	def completion_description(self) -> str:
		"""
		Rich description shown alongside a VLNV in tab completion.

		Format:
			<DisplayName>  [<vendor>/<library>]  <short description>

		Example:
			FIFO Generator  [xilinx.com/ip]  Configurable synchronous and …
		"""
		parts = [self.display_name]

		vendor_lib = f"[{self.vendor}/{self.library}]"
		parts.append(vendor_lib)

		# Warn flags visible in the completion list
		flags: list[str] = []
		if self.hidden:
			flags.append("⚠ internal subcore")
		if self.board_dependent:
			flags.append("⚠ board-dependent")
		if self.ipi_only:
			flags.append("⚠ IPI-only")
		if flags:
			parts.append("  ".join(flags))
		elif self.short_desc:
			parts.append(self.short_desc)

		return "  ".join(parts)


# =============================================================================
# Parser
# =============================================================================

def _parse_vv_index(xml_path: str) -> dict[str, CoreEntry]:
	"""
	Parse vv_index.xml → dict keyed by VLNV string.

	Returns an empty dict (not an error) when the file is absent or
	unparseable, so all callers can always proceed gracefully.
	"""
	if not os.path.isfile(xml_path):
		logger.debug("vv_index.xml not found at %s", xml_path)
		return {}

	try:
		tree = ET.parse(xml_path)
	except ET.ParseError as exc:
		logger.warning("Failed to parse vv_index.xml: %s", exc)
		return {}

	root = tree.getroot()
	catalog: dict[str, CoreEntry] = {}

	for ip_el in root.findall("IP"):

		# ---- VLNV --------------------------------------------------------
		vlnv_el = ip_el.find("VLNV")
		if vlnv_el is None:
			continue
		vlnv = (vlnv_el.get("value") or "").strip()
		if not vlnv:
			continue

		parts = vlnv.split(":")
		if len(parts) != 4:
			continue
		vendor, library, name, version = parts

		# ---- Helper: first child element text/value ----------------------
		def _val(tag: str, default: str = "") -> str:
			el = ip_el.find(tag)
			if el is None:
				return default
			return (el.get("value") or el.text or default).strip()

		# ---- HideInGui ---------------------------------------------------
		hide_el = ip_el.find("HideInGui")
		hidden = (
			hide_el is not None
			and hide_el.get("value", "").lower() == "true"
		)

		# ---- BoardDependent ----------------------------------------------
		board_el = ip_el.find("BoardDependent")
		board_dependent = (
			board_el is not None
			and board_el.get("value", "").lower() == "true"
		)

		# ---- IPI-only ----------------------------------------------------
		tool_els = ip_el.findall("DesignToolContexts/DesignTool")
		tools = {el.get("value", "") for el in tool_els}
		ipi_only = bool(tools) and tools == {"IPI"}

		# ---- Unsupported families ----------------------------------------
		unsupported: set[str] = set()
		for fam_el in ip_el.findall("Families/Family"):
			fam_name = fam_el.get("name", "")
			for part_el in fam_el.findall("Part"):
				if part_el.get("status", "") == "Not-Supported":
					unsupported.add(fam_name)

		# ---- UpgradesFrom ------------------------------------------------
		upgrades_from = tuple(
			u.get("value", "")
			for u in ip_el.findall("UpgradesFrom/Upgrade")
			if u.get("value")
		)

		catalog[vlnv] = CoreEntry(
			vlnv                 = vlnv,
			vendor               = vendor,
			library              = library,
			name                 = name,
			version              = version,
			display_name         = _val("DisplayName"),
			description          = _val("Description"),
			hidden               = hidden,
			board_dependent      = board_dependent,
			ipi_only             = ipi_only,
			unsupported_families = frozenset(unsupported),
			upgrades_from        = upgrades_from,
		)

	logger.debug(
		"vv_index.xml: parsed %d entries from %s", len(catalog), xml_path
	)
	return catalog


# =============================================================================
# Cache + public API
# =============================================================================

_CATALOG_CACHE: dict[str, dict[str, CoreEntry]] = {}


def load(vivado_path: str) -> dict[str, CoreEntry]:
	"""
	Load (and cache) the catalog for a Vivado installation.
	Safe to call repeatedly — parses once per process.
	"""
	if vivado_path not in _CATALOG_CACHE:
		xml_path = os.path.join(vivado_path, "data", "ip", "vv_index.xml")
		_CATALOG_CACHE[vivado_path] = _parse_vv_index(xml_path)
	return _CATALOG_CACHE[vivado_path]


def lookup(vivado_path: str, vlnv: str) -> Optional[CoreEntry]:
	"""Return the CoreEntry for an exact VLNV, or None."""
	return load(vivado_path).get(vlnv)


def find_by_name(vivado_path: str, ip_name: str) -> list[CoreEntry]:
	"""
	All entries whose short name matches ip_name.
	Used to suggest correct version when the user writes a bad VLNV.
	"""
	return [e for e in load(vivado_path).values() if e.name == ip_name]


def user_visible(vivado_path: str) -> list[CoreEntry]:
	"""
	Entries a user would see in the Vivado IP Catalog GUI.
	Excludes hidden subcores and IPI-only internal primitives.
	"""
	return [
		e for e in load(vivado_path).values()
		if not e.hidden
	]


def search(
	vivado_path: str,
	prefix: str,
	*,
	include_hidden: bool = False,
) -> list[CoreEntry]:
	"""
	Return entries whose VLNV, display_name, or description contain
	`prefix` (case-insensitive).  Used by the tab completer.
	"""
	needle = prefix.lower()
	results = []
	for entry in load(vivado_path).values():
		if not include_hidden and entry.hidden:
			continue
		if (
			needle in entry.vlnv.lower()
			or needle in entry.display_name.lower()
			or needle in entry.description.lower()
		):
			results.append(entry)
	return results