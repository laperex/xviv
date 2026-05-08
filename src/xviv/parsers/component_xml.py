import logging
import xml.etree.ElementTree as ET

from xviv.config.model import CatalogCoreEntry


logger = logging.getLogger(__name__)


_SPIRIT_NS = "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"
_XILINX_NS = "http://www.xilinx.com"


def parser(xml_path: str) -> CatalogCoreEntry | None:
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

		return CatalogCoreEntry(
			vlnv=vlnv,
			vendor=vendor,
			library=library,
			name=name,
			version=version,
			display_name=display_name,
			description=description,
			hidden=False,
			board_dependent=False,
			ipi_only=False,
			unsupported_families=frozenset(),
			upgrades_from=(),
		)
	except Exception as exc:
		logger.debug("Failed to parse component.xml at %s: %s", xml_path, exc)
		return None