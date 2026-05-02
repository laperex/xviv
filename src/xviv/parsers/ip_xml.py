from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

from xviv.catalog.model import CoreEntry

logger = logging.getLogger(__name__)

_SPIRIT_NS = "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"
_XILINX_NS = "http://www.xilinx.com"


def parse_vv_index(xml_path: str) -> dict[str, CoreEntry]:
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

		def _val(tag: str, default: str = "") -> str:
			el = ip_el.find(tag)
			if el is None:
				return default
			return (el.get("value") or el.text or default).strip()

		hide_el = ip_el.find("HideInGui")
		hidden = hide_el is not None and hide_el.get("value", "").lower() == "true"

		board_el = ip_el.find("BoardDependent")
		board_dependent = board_el is not None and board_el.get("value", "").lower() == "true"

		tools = {el.get("value", "") for el in ip_el.findall("DesignToolContexts/DesignTool")}
		ipi_only = bool(tools) and tools == {"IPI"}

		unsupported: set[str] = set()
		for fam_el in ip_el.findall("Families/Family"):
			for part_el in fam_el.findall("Part"):
				if part_el.get("status", "") == "Not-Supported":
					unsupported.add(fam_el.get("name", ""))

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

	logger.debug("vv_index.xml: parsed %d entries from %s", len(catalog), xml_path)
	return catalog


def parse_component_xml(xml_path: str) -> Optional[CoreEntry]:
	try:
		root = ET.parse(xml_path).getroot()

		def _s(tag: str) -> str:
			el = root.find(f"{{{_SPIRIT_NS}}}{tag}")
			return el.text.strip() if el is not None and el.text else ""

		vendor  = _s("vendor")
		library = _s("library")
		name    = _s("name")
		version = _s("version")
		if not all([vendor, library, name, version]):
			return None
		vlnv = f"{vendor}:{library}:{name}:{version}"

		description = _s("description")

		display_name_el = root.find(
			f"{{{_SPIRIT_NS}}}vendorExtensions"
			f"/{{{_XILINX_NS}}}coreExtensions"
			f"/{{{_XILINX_NS}}}displayName"
		)
		display_name = (
			display_name_el.text.strip()
			if display_name_el is not None and display_name_el.text
			else name
		)

		return CoreEntry(
			vlnv=vlnv, vendor=vendor, library=library,
			name=name, version=version,
			display_name=display_name,
			description=description,
			hidden=False, board_dependent=False, ipi_only=False,
			unsupported_families=frozenset(), upgrades_from=(),
		)
	except Exception as exc:
		logger.debug("Failed to parse component.xml at %s: %s", xml_path, exc)
		return None