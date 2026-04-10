"""
bd_deps.py
Parse a Vivado .bd JSON to find custom IP instances, then read each
instance's Vivado-generated <xci_name>.xml (IP-XACT, from the bd ip/ dir)
to extract everything needed for OOC synthesis.

The original RTL sources from project.toml are deliberately NOT used —
Vivado copies sources into ipshared when the BD is generated, and those
copies are the ground truth for what will actually be synthesised.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# IP-XACT XML namespaces present in Vivado component xml files
_NS = {
    "spirit": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009",
    "xilinx":  "http://www.xilinx.com",
}

# Vendors that identify Xilinx stock IPs — skip for OOC (Vivado handles them)
_STOCK_VENDORS = {"xilinx.com"}


@dataclass
class IpOocInfo:
    """All information needed to run OOC synthesis for one custom IP."""
    instance_name:  str        # BD instance name,  e.g. "ip_rgb_to_hsv_0"
    xci_name:       str        # e.g. "bd_image_processing_ip_rgb_to_hsv_0_0"
    vlnv:           str        # e.g. "laperex.org:custom_axi_ip:ip_rgb_to_hsv:1.0"
    top_module:     str        # synthesis modelName, e.g. "ip_rgb_to_hsv_wrapper"
    rtl_files:      list[str]  # absolute paths — ipshared copies, non-include
    include_dirs:   list[str]  # unique dirs of isIncludeFile sources
    ooc_xdc_files:  list[str]  # absolute paths from synthesisconstraints fileset
    xml_path:       str        # absolute path to <xci_name>.xml — mtime anchor


# ─────────────────────────────────────────────────────────────────────────────
# BD JSON parsing
# ─────────────────────────────────────────────────────────────────────────────

def _is_custom_ip(vlnv: str) -> bool:
    vendor = vlnv.split(":")[0] if vlnv else ""
    return vendor not in _STOCK_VENDORS


def _collect_custom_instances(bd_path: str) -> list[dict]:
    """
    Walk design.components recursively.
    Return one dict per custom IP leaf instance that has both vlnv and xci_name.
    """
    with open(bd_path) as fh:
        data = json.load(fh)

    results: list[dict] = []

    def _walk(components: dict) -> None:
        for inst_name, cell in components.items():
            if not isinstance(cell, dict):
                continue

            vlnv     = cell.get("vlnv", "")
            xci_name = cell.get("xci_name", "")
            xci_path = cell.get("xci_path", "")

            if vlnv and xci_name and _is_custom_ip(vlnv):
                results.append({
                    "instance_name": inst_name,
                    "vlnv":          vlnv,
                    "xci_name":      xci_name,
                    "xci_path":      xci_path,
                })
                logger.info("Custom IP found: %-30s  %s", inst_name, vlnv)
            elif vlnv:
                logger.debug("Stock IP, skip:  %-30s  %s", inst_name, vlnv)

            # Recurse — handles hierarchical BDs and interconnect sub-components
            sub = cell.get("components", {})
            if sub:
                _walk(sub)

    _walk(data.get("design", {}).get("components", {}))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# IP-XACT XML parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ip_xml(
    xml_path: str,
) -> tuple[str, list[str], list[str], list[str]]:
    """
    Parse a Vivado IP-XACT <xci_name>.xml.

    Returns
    -------
    top_module    : modelName of the xilinx_verilogsynthesis view
    rtl_files     : absolute paths of non-include synthesis sources
    include_dirs  : unique dirs of isIncludeFile=true sources
    ooc_xdc_files : absolute paths from xilinx_synthesisconstraints fileset
    """
    xml_dir = os.path.dirname(xml_path)
    root    = ET.parse(xml_path).getroot()

    # ── 1. Collect all fileSets into a map: name -> list of file entries ──────
    fileset_map: dict[str, list[dict]] = {}

    for fs in root.findall(".//spirit:fileSet", _NS):
        name_el = fs.find("spirit:name", _NS)
        if name_el is None:
            continue
        fs_name  = (name_el.text or "").strip()
        entries: list[dict] = []

        for f_el in fs.findall("spirit:file", _NS):
            path_el  = f_el.find("spirit:name",          _NS)
            inc_el   = f_el.find("spirit:isIncludeFile", _NS)
            type_el  = f_el.find("spirit:fileType",      _NS)
            utype_el = f_el.find("spirit:userFileType",  _NS)

            if path_el is None:
                continue

            abs_path   = os.path.normpath(
                os.path.join(xml_dir, (path_el.text or "").strip())
            )
            is_include = (
                inc_el is not None
                and (inc_el.text or "").strip().lower() == "true"
            )
            file_type  = (
                (type_el.text or "").strip()  if type_el  is not None else
                (utype_el.text or "").strip() if utype_el is not None else ""
            )
            entries.append({
                "abs_path":   abs_path,
                "is_include": is_include,
                "file_type":  file_type,
            })

        fileset_map[fs_name] = entries

    # ── 2. Scan views for synthesis top name and fileset references ───────────
    top_module          = ""
    synth_fileset_name  = ""
    constr_fileset_name = ""

    for view in root.findall(".//spirit:view", _NS):
        name_el = view.find("spirit:name", _NS)
        if name_el is None:
            continue
        view_name = (name_el.text or "").strip()

        if view_name == "xilinx_verilogsynthesis":
            mn = view.find("spirit:modelName", _NS)
            if mn is not None:
                top_module = (mn.text or "").strip()
            ref = view.find(".//spirit:localName", _NS)
            if ref is not None:
                synth_fileset_name = (ref.text or "").strip()

        elif view_name == "xilinx_synthesisconstraints":
            ref = view.find(".//spirit:localName", _NS)
            if ref is not None:
                constr_fileset_name = (ref.text or "").strip()

    if not top_module:
        raise ValueError(
            f"No xilinx_verilogsynthesis view / modelName found in {xml_path}"
        )

    # ── 3. Resolve RTL files and include dirs ─────────────────────────────────
    rtl_files:    list[str] = []
    include_dirs: list[str] = []
    seen_dirs:    set[str]  = set()

    for entry in fileset_map.get(synth_fileset_name, []):
        if entry["is_include"]:
            d = os.path.dirname(entry["abs_path"])
            if d not in seen_dirs:
                include_dirs.append(d)
                seen_dirs.add(d)
                logger.debug("Include dir: %s", d)
        else:
            rtl_files.append(entry["abs_path"])
            logger.debug("RTL file:    %s", entry["abs_path"])

    # ── 4. OOC XDC from synthesisconstraints fileset ──────────────────────────
    ooc_xdc_files: list[str] = [
        e["abs_path"]
        for e in fileset_map.get(constr_fileset_name, [])
        if e["abs_path"].endswith(".xdc")
    ]

    logger.debug(
        "%s: top=%s  rtl=%d  inc_dirs=%d  xdc=%d",
        os.path.basename(xml_path),
        top_module, len(rtl_files), len(include_dirs), len(ooc_xdc_files),
    )
    return top_module, rtl_files, include_dirs, ooc_xdc_files


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _bd_file_path(cfg: dict, base_dir: str, bd_name: str) -> str:
    from xviv.config import DEFAULT_BUILD_BD_DIR
    build_cfg = cfg.get("build", {})
    bd_dir    = os.path.abspath(
        os.path.join(base_dir, build_cfg.get("bd_dir", DEFAULT_BUILD_BD_DIR))
    )
    return os.path.join(bd_dir, bd_name, f"{bd_name}.bd")


def find_ip_ooc_info(cfg: dict, base_dir: str, bd_name: str) -> list[IpOocInfo]:
    """
    Parse the BD file and return one IpOocInfo per unique custom IP
    (deduplicated by xci_name — multiple instances of the same IP share one DCP).

    Requires generate-bd to have been run so that ip/<xci_name>/<xci_name>.xml
    files exist in the BD directory.
    """
    bd_path = _bd_file_path(cfg, base_dir, bd_name)
    if not os.path.exists(bd_path):
        sys.exit(
            f"ERROR: BD file not found: {bd_path}\n"
            f"  Run 'xviv create-bd --bd {bd_name}' first."
        )

    bd_dir    = os.path.dirname(bd_path)   # build/bd/<bd_name>/
    instances = _collect_custom_instances(bd_path)

    if not instances:
        logger.info("No custom IP instances found in BD '%s'", bd_name)
        return []

    results:        list[IpOocInfo] = []
    seen_xci_names: set[str]        = set()

    for inst in instances:
        xci_name = inst["xci_name"]

        # Deduplicate — two instances of the same IP share one OOC DCP
        if xci_name in seen_xci_names:
            logger.debug("Dedup — skipping second instance of %s", xci_name)
            continue
        seen_xci_names.add(xci_name)

        # xci_path in the BD JSON is relative to bd/<bd_name>/
        # e.g. "ip/bd_image_processing_ip_inrange_0_0/bd_image_processing_ip_inrange_0_0.xci"
        xci_abs  = os.path.join(bd_dir, inst["xci_path"])
        xci_dir  = os.path.dirname(xci_abs)

        # ── KEY FIX: Vivado names this <xci_name>.xml, not component.xml ─────
        xml_path = os.path.join(xci_dir, f"{xci_name}.xml")

        if not os.path.exists(xml_path):
            sys.exit(
                f"ERROR: IP XML not found: {xml_path}\n"
                f"  Run 'xviv generate-bd --bd {bd_name}' first."
            )

        try:
            top_module, rtl_files, include_dirs, ooc_xdc = \
                _parse_ip_xml(xml_path)
        except Exception as exc:
            sys.exit(f"ERROR: parsing {xml_path}:\n  {exc}")

        logger.info(
            "  %-50s  top=%-30s  rtl=%d  inc=%d  xdc=%d",
            xci_name, top_module,
            len(rtl_files), len(include_dirs), len(ooc_xdc),
        )

        results.append(IpOocInfo(
            instance_name = inst["instance_name"],
            xci_name      = xci_name,
            vlnv          = inst["vlnv"],
            top_module    = top_module,
            rtl_files     = rtl_files,
            include_dirs  = include_dirs,
            ooc_xdc_files = ooc_xdc,
            xml_path      = xml_path,
        ))

    return results