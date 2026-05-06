from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET

from xviv.config.model import CatalogCoreEntry

logger = logging.getLogger(__name__)


def parser(xml_path: str) -> dict[str, CatalogCoreEntry]:
	if not os.path.isfile(xml_path):
		logger.debug("vv_index.xml not found at %s", xml_path)
		return {}

	try:
		tree = ET.parse(xml_path)
	except ET.ParseError as exc:
		logger.warning("Failed to parse vv_index.xml: %s", exc)
		return {}

	root = tree.getroot()
	catalog: dict[str, CatalogCoreEntry] = {}

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

		catalog[vlnv] = CatalogCoreEntry(
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


