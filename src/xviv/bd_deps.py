"""
bd_deps.py
Parse a Vivado BD directory to find every leaf IP instance (all vendors),
then read each instance's Vivado-generated <xci_name>.xml (IP-XACT, from
the bd ip/ dir) to extract everything needed for OOC synthesis.

Leaf IPs are identified by the presence of:
- ip/<xci_name>/<xci_name>.xml   (IP-XACT metadata)
- ip/<xci_name>/synth/           (generated synthesis output product)

Hierarchical BD sub-modules (e.g. axi_mem_intercon_0) have no synth/
directory and are defined inline in synth/bd_image_processing.v — they
are skipped.
"""
from __future__ import annotations

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

@dataclass
class IpOocInfo:
	"""All information needed to run OOC synthesis for one IP."""
	xci_name:     str
	vlnv:         str
	top_module:   str        # = xci_name for all IPs (matches Phase-2 REF_NAME)
	rtl_files:    list[str]  # empty for Xilinx IPs (read_ip handles it)
	include_dirs: list[str]
	ooc_xdc_files:list[str]
	xml_path:     str
	xci_file:     str        # absolute path to <xci_name>.xci
	is_xilinx:    bool       # True  → read_ip flow; False → manual RTL flow


# ─────────────────────────────────────────────────────────────────────────────
# IP-XACT XML parsing  (unchanged from original)
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
# VLNV helper
# ─────────────────────────────────────────────────────────────────────────────

def _read_vlnv(xml_path: str) -> str:
	"""Extract the VLNV string from a component XML, or return '' on failure."""
	try:
		root = ET.parse(xml_path).getroot()
		vendor  = root.find("spirit:vendor",  _NS)
		library = root.find("spirit:library", _NS)
		name    = root.find("spirit:name",    _NS)
		version = root.find("spirit:version", _NS)
		parts = [
			(vendor.text  or "").strip() if vendor  is not None else "",
			(library.text or "").strip() if library is not None else "",
			(name.text    or "").strip() if name    is not None else "",
			(version.text or "").strip() if version is not None else "",
		]
		return ":".join(parts)
	except Exception:
		return ""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _bd_dir(cfg: dict, base_dir: str, bd_name: str) -> str:
	from xviv.config import DEFAULT_BUILD_BD_DIR
	build_cfg = cfg.get("build", {})
	bd_dir    = os.path.abspath(
		os.path.join(base_dir, build_cfg.get("bd_dir", DEFAULT_BUILD_BD_DIR))
	)
	return os.path.join(bd_dir, bd_name)


def find_all_ip_ooc_info(cfg: dict, base_dir: str, bd_name: str) -> list[IpOocInfo]:
	"""
	Scan build/bd/<bd_name>/ip/ and return one IpOocInfo for every leaf IP
	that has both a <xci_name>.xml and a synth/ output directory.

	Hierarchical BD sub-modules (e.g. axi_mem_intercon_0, ps7_0_axi_periph_0)
	have no synth/ directory and are skipped — they are defined inline in the
	BD's top-level synth netlist.

	Requires generate-bd to have been run so that ip/<xci_name>/<xci_name>.xml
	and ip/<xci_name>/synth/ exist.
	"""
	bd_path = os.path.join(_bd_dir(cfg, base_dir, bd_name), f"{bd_name}.bd")
	if not os.path.exists(bd_path):
		sys.exit(
			f"ERROR: BD file not found: {bd_path}\n"
			f"  Run 'xviv create-bd --bd {bd_name}' first."
		)

	ip_root = os.path.join(os.path.dirname(bd_path), "ip")
	if not os.path.isdir(ip_root):
		logger.info("No ip/ directory found in BD '%s'", bd_name)
		return []

	results:      list[IpOocInfo] = []
	seen_xci:     set[str]        = set()

	for xci_name in sorted(os.listdir(ip_root)):
		xci_subdir = os.path.join(ip_root, xci_name)
		if not os.path.isdir(xci_subdir):
			continue

		# Must have an IP-XACT XML
		xml_path = os.path.join(xci_subdir, f"{xci_name}.xml")
		if not os.path.exists(xml_path):
			logger.debug("No XML — skipping hierarchical container: %s", xci_name)
			continue

		# Must have a synth/ output product directory
		synth_dir = os.path.join(xci_subdir, "synth")
		if not os.path.isdir(synth_dir):
			logger.debug("No synth/ — skipping hierarchical container: %s", xci_name)
			continue

		if xci_name in seen_xci:
			logger.debug("Duplicate xci_name — skipping: %s", xci_name)
			continue
		seen_xci.add(xci_name)

		try:
			top_module, rtl_files, include_dirs, ooc_xdc = _parse_ip_xml(xml_path)
		except Exception as exc:
			logger.warning("Skipping %s — XML parse error: %s", xci_name, exc)
			continue

		vlnv = _read_vlnv(xml_path)
		vendor = vlnv.split(":")[0] if vlnv else ""
		is_xilinx = (vendor == "xilinx.com")

		xci_file = os.path.join(xci_subdir, f"{xci_name}.xci")

		if is_xilinx:
			# Vivado resolves all RTL via read_ip + ip catalog.
			# Override top_module to xci_name so Phase-2 REF_NAME lookup
			# matches the BD synth/ wrapper module name.
			top_module = xci_name
			rtl_files  = []
			include_dirs = []
			ooc_xdc = []
		else:
			# Custom IPs: prepend the BD synth/ wrapper file so OOC top =
			# xci_name, which matches REF_NAME in the elaborated BD netlist.
			for ext in (".sv", ".v", ".vhd", ".vhdl"):
				synth_wrapper = os.path.join(synth_dir, f"{xci_name}{ext}")
				if os.path.exists(synth_wrapper):
					if synth_wrapper not in rtl_files:
						rtl_files.insert(0, synth_wrapper)
					break
			top_module = xci_name   # override modelName from XML

		logger.info(
			"  %-55s  top=%-35s  rtl=%d  inc=%d  xdc=%d  xilinx=%s",
			xci_name, top_module,
			len(rtl_files), len(include_dirs), len(ooc_xdc), is_xilinx,
		)

		results.append(IpOocInfo(
			xci_name      = xci_name,
			vlnv          = vlnv,
			top_module    = top_module,
			rtl_files     = rtl_files,
			include_dirs  = include_dirs,
			ooc_xdc_files = ooc_xdc,
			xml_path      = xml_path,
			xci_file      = xci_file,
			is_xilinx     = is_xilinx,
		))

	logger.info("Total leaf IPs found in BD '%s': %d", bd_name, len(results))
	return results