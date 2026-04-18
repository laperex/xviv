"""
core_catalog.py  (revised)
===========================
Changes from previous version:

1. _parse_vv_index now also collects VLNVs that appear ONLY inside
   <UpgradesFrom> elements and creates stub CoreEntry objects for them,
   so older versions are visible in the completer even when they have
   no own <IP> block in the installed Vivado's vv_index.xml.

2. CoreEntry gains an `is_stub` flag to distinguish full entries (own
   <IP> block, can be instantiated) from stub entries (referenced only
   in UpgradesFrom, may not be instantiatable in this Vivado version).

3. load() returns a VersionGroup dict alongside the flat catalog so
   completers can show all versions of an IP grouped together.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)

_DESC_MAX = 72


# =============================================================================
# Data model
# =============================================================================

@dataclasses.dataclass(frozen=True)
class CoreEntry:
    vlnv:                 str
    vendor:               str
    library:              str
    name:                 str                  # short ip name, e.g. "clk_wiz"
    version:              str
    display_name:         str
    description:          str
    hidden:               bool
    board_dependent:      bool
    ipi_only:             bool
    unsupported_families: frozenset[str]
    upgrades_from:        tuple[str, ...]
    is_stub:              bool = False         # True → only seen in UpgradesFrom

    @property
    def short_desc(self) -> str:
        text = " ".join(self.description.split())
        if len(text) > _DESC_MAX:
            text = text[:_DESC_MAX - 1] + "…"
        return text

    @property
    def completion_description(self) -> str:
        """Rich one-line description for terminal tab completion."""
        parts = [self.display_name or self.name]
        parts.append(f"[{self.vendor}/{self.library}]")

        flags: list[str] = []
        if self.is_stub:
            flags.append("⚠ older version — may not install in this Vivado")
        elif self.hidden:
            flags.append("⚠ internal subcore")
        elif self.board_dependent:
            flags.append("⚠ board-dependent")
        elif self.ipi_only:
            flags.append("⚠ IPI-only")

        if flags:
            parts.append("  ".join(flags))
        elif self.short_desc:
            parts.append(self.short_desc)

        return "  ".join(parts)


@dataclasses.dataclass
class VersionGroup:
    """All known versions of a single IP name, newest first."""
    name:    str                   # e.g. "clk_wiz"
    vendor:  str                   # e.g. "xilinx.com"
    library: str                   # e.g. "ip"
    entries: list[CoreEntry]       # sorted newest → oldest

    @property
    def latest(self) -> CoreEntry:
        return self.entries[0]

    @property
    def has_older_versions(self) -> bool:
        return len(self.entries) > 1


# =============================================================================
# Parser
# =============================================================================

def _parse_vv_index(xml_path: str) -> tuple[
    dict[str, CoreEntry],       # vlnv → CoreEntry  (all versions)
    dict[str, VersionGroup],    # "<vendor>:<library>:<name>" → VersionGroup
]:
    """
    Parse vv_index.xml.

    Two-pass strategy:
      Pass 1 — build full CoreEntry for every <IP> block.
      Pass 2 — walk every <UpgradesFrom> and create stub CoreEntry objects
               for any VLNV not already present from Pass 1.

    Returns (catalog, groups).
    """
    if not os.path.isfile(xml_path):
        logger.debug("vv_index.xml not found at %s", xml_path)
        return {}, {}

    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        logger.warning("Failed to parse vv_index.xml: %s", exc)
        return {}, {}

    catalog: dict[str, CoreEntry] = {}

    # ------------------------------------------------------------------
    # Pass 1: full entries from <IP> blocks
    # ------------------------------------------------------------------
    for ip_el in root.findall("IP"):

        def _val(tag: str, default: str = "") -> str:
            el = ip_el.find(tag)
            if el is None:
                return default
            return (el.get("value") or el.text or default).strip()

        vlnv = _val("VLNV")
        if not vlnv:
            continue
        parts = vlnv.split(":")
        if len(parts) != 4:
            continue
        vendor, library, name, version = parts

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
            is_stub              = False,
        )

    # ------------------------------------------------------------------
    # Pass 2: stub entries from <UpgradesFrom> references
    #
    # Example: axis_data_fifo:2.0 lists axis_data_fifo:1.0 in UpgradesFrom.
    # If 1.0 has no own <IP> block, it won't be in catalog yet.
    # We create a stub so the completer can surface it with a warning.
    # ------------------------------------------------------------------
    for entry in list(catalog.values()):
        for older_vlnv in entry.upgrades_from:
            if older_vlnv in catalog:
                continue                    # already has a full entry

            parts = older_vlnv.split(":")
            if len(parts) != 4:
                continue
            vendor, library, name, version = parts

            catalog[older_vlnv] = CoreEntry(
                vlnv                 = older_vlnv,
                vendor               = vendor,
                library              = library,
                name                 = name,
                version              = version,
                # Inherit display_name/description from the newer version
                display_name         = entry.display_name,
                description          = entry.description,
                hidden               = entry.hidden,
                board_dependent      = entry.board_dependent,
                ipi_only             = entry.ipi_only,
                unsupported_families = entry.unsupported_families,
                upgrades_from        = (),
                is_stub              = True,     # ← key flag
            )

    # ------------------------------------------------------------------
    # Build VersionGroup index
    # ------------------------------------------------------------------
    groups: dict[str, VersionGroup] = {}

    for entry in catalog.values():
        group_key = f"{entry.vendor}:{entry.library}:{entry.name}"
        if group_key not in groups:
            groups[group_key] = VersionGroup(
                name    = entry.name,
                vendor  = entry.vendor,
                library = entry.library,
                entries = [],
            )
        groups[group_key].entries.append(entry)

    # Sort each group newest → oldest (simple lexicographic version sort)
    for group in groups.values():
        group.entries.sort(key=lambda e: e.version, reverse=True)

    logger.debug(
        "vv_index.xml: %d entries (%d stubs) across %d IPs from %s",
        len(catalog),
        sum(1 for e in catalog.values() if e.is_stub),
        len(groups),
        xml_path,
    )
    return catalog, groups


# =============================================================================
# Cache
# =============================================================================

_CATALOG_CACHE:  dict[str, dict[str, CoreEntry]]    = {}
_GROUPS_CACHE:   dict[str, dict[str, VersionGroup]] = {}


def _ensure_loaded(vivado_path: str) -> None:
    if vivado_path not in _CATALOG_CACHE:
        xml_path = os.path.join(vivado_path, "data", "ip", "vv_index.xml")
        cat, grps = _parse_vv_index(xml_path)
        _CATALOG_CACHE[vivado_path] = cat
        _GROUPS_CACHE[vivado_path]  = grps


def load(vivado_path: str) -> dict[str, CoreEntry]:
    _ensure_loaded(vivado_path)
    return _CATALOG_CACHE[vivado_path]


def load_groups(vivado_path: str) -> dict[str, VersionGroup]:
    _ensure_loaded(vivado_path)
    return _GROUPS_CACHE[vivado_path]


# =============================================================================
# Public query API
# =============================================================================

def lookup(vivado_path: str, vlnv: str) -> Optional[CoreEntry]:
    return load(vivado_path).get(vlnv)


def find_by_name(vivado_path: str, ip_name: str) -> list[CoreEntry]:
    """All versions of ip_name, newest first."""
    group_key = next(
        (k for k in load_groups(vivado_path) if k.endswith(f":{ip_name}")),
        None,
    )
    if group_key is None:
        return []
    return load_groups(vivado_path)[group_key].entries


def user_visible(vivado_path: str) -> list[CoreEntry]:
    """Non-hidden entries — what the Vivado IP Catalog GUI shows."""
    return [e for e in load(vivado_path).values() if not e.hidden]