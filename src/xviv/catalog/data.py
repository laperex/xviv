from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import sys
import typing
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)


def _term_width() -> int:
	return shutil.get_terminal_size().columns


# --- Data model ---

@dataclasses.dataclass(frozen=True)
class CoreEntry:
	vlnv:                 str
	vendor:               str
	library:              str
	name:                 str
	version:              str
	display_name:         str
	description:          str
	hidden:               bool
	board_dependent:      bool
	ipi_only:             bool
	unsupported_families: frozenset[str]
	upgrades_from:        tuple[str, ...]

	@property
	def short_desc(self) -> str:
		desc_max = _term_width() // 2
		text = " ".join(self.description.split())

		if len(text) > desc_max:
			text = text[:desc_max - 1] + "…"

		return text

	@property
	def completion_description(self) -> str:
		parts = [self.display_name, f"[{self.vendor}/{self.library}]"]
		flags: list[str] = []
		if self.hidden:          flags.append("⚠ internal subcore")
		if self.board_dependent: flags.append("⚠ board-dependent")
		if self.ipi_only:        flags.append("⚠ IPI-only")
		if flags:
			parts.append("  ".join(flags))
		elif self.short_desc:
			parts.append(self.short_desc)
		return "  ".join(parts)


# --- Parser ---

def _parse_vv_index(xml_path: str) -> dict[str, CoreEntry]:
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


# --- Cache + public API ---

_CATALOG_CACHE: dict[str, dict[str, CoreEntry]] = {}


def load(vivado_path: str, ip_repo: list[str] = []) -> dict[str, CoreEntry]:
	if vivado_path not in _CATALOG_CACHE:
		xml_path = os.path.join(vivado_path, "data", "ip", "vv_index.xml")
		_CATALOG_CACHE[vivado_path] = _parse_vv_index(xml_path)

		for repo in ip_repo:
			_CATALOG_CACHE[vivado_path].update(load_ip_repo(repo))

	return _CATALOG_CACHE[vivado_path]


def lookup(vivado_path: str, ip_repo: list[str], id: str) -> CoreEntry:
	catalog = load(vivado_path, ip_repo)

	entry = catalog.get(id, None)
	if entry is None:
		for key in catalog:
			if id in key:
				if entry:
					entry = None
					break

				entry = catalog[key]

	if not entry:
		sys.exit(
			f"ERROR: Unable to resolve vlnv from core_id: {id}"
		)

	print(f"INFO: resolved vlnv {entry.vlnv} from {id}")

	return entry


def find_by_name(vivado_path: str, ip_name: str) -> list[CoreEntry]:
	return [e for e in load(vivado_path).values() if e.name == ip_name]


def user_visible(vivado_path: str) -> list[CoreEntry]:
	return [e for e in load(vivado_path).values() if not e.hidden]


def search(
	vivado_path: str,
	prefix: str,
	*,
	include_hidden: bool = False,
) -> list[CoreEntry]:
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

_SPIRIT_NS = "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"
_XILINX_NS = "http://www.xilinx.com"

def _parse_component_xml(xml_path: str) -> Optional[CoreEntry]:
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

        # spirit:description is at root level
        description = _s("description")

        # display name is under vendorExtensions/coreExtensions
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


def load_ip_repo(ip_repo_path: str) -> dict[str, CoreEntry]:
    catalog: dict[str, CoreEntry] = {}
    if not os.path.isdir(ip_repo_path):
        return catalog
    for entry in os.scandir(ip_repo_path):
        if not entry.is_dir():
            continue
        component_xml = os.path.join(entry.path, "component.xml")
        if not os.path.isfile(component_xml):
            continue
        core = _parse_component_xml(component_xml)
        if core:
            catalog[core.vlnv] = core
    return catalog