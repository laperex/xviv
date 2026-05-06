from __future__ import annotations

from collections.abc import ValuesView
import logging
import os
import sys
from typing import Iterator
import typing

from xviv.config.model import CatalogCoreEntry
from xviv.parsers import vv_index_xml
from xviv.parsers import component_xml

logger = logging.getLogger(__name__)

class Catalog:
	def __init__(self, vivado_path: str, ip_repos: list[str] | None = None) -> None:
		self._cores: dict[str, CatalogCoreEntry] = {}
		self._load(vivado_path, ip_repos or [])

	# ------------------------------------------------------------------
	# Construction
	# ------------------------------------------------------------------

	def _load(self, vivado_path: str, ip_repos: list[str]) -> None:
		xml_path = os.path.join(vivado_path, "data", "ip", "vv_index.xml")
		self._cores.update(vv_index_xml.parser(xml_path))
		for repo in ip_repos:
			merged = _load_ip_repo(repo)
			if merged:
				logger.debug("ip_repo %s: loaded %d cores", repo, len(merged))
			self._cores.update(merged)
		logger.debug("Catalog: %d total cores", len(self._cores))

	# ------------------------------------------------------------------
	# Iteration
	# ------------------------------------------------------------------

	def __len__(self) -> int:
		return len(self._cores)

	def __iter__(self) -> Iterator[CatalogCoreEntry]:
		return iter(self._cores.values())

	def __contains__(self, vlnv: str) -> bool:
		return vlnv in self._cores

	# ------------------------------------------------------------------
	# Lookups
	# ------------------------------------------------------------------

	def get(self, vlnv: str) -> CatalogCoreEntry | None:
		return self._cores.get(vlnv)

	def lookup(self, id: str) -> CatalogCoreEntry:
		entry = self.lookup_none(id)

		if entry:
			return entry

		sys.exit(f"ERROR: Unable to resolve core: {id!r}")

	def lookup_none(self, id: str) -> typing.Optional[CatalogCoreEntry]:
		entry = self._cores.get(id)
		if entry is not None:
			return entry

		matches = [e for key, e in self._cores.items() if id in key]

		if len(matches) == 1:
			logger.info("Resolved %r → %s", id, matches[0].vlnv)
			return matches[0]
		if len(matches) > 1:
			candidates = ", ".join(e.vlnv for e in matches[:5])
			sys.exit(f"ERROR: Unable to resolve core: {id!r} is ambiguous: {candidates}...")

		return None

	def find_by_name(self, ip_name: str) -> list[CatalogCoreEntry]:
		return [e for e in self._cores.values() if e.name == ip_name]

	# ------------------------------------------------------------------
	# Filtered views
	# ------------------------------------------------------------------

	def user_visible(self) -> list[CatalogCoreEntry]:
		return [e for e in self._cores.values() if not e.hidden]

	def search(
		self,
		prefix: str,
		*,
		include_hidden: bool = False,
	) -> list[CatalogCoreEntry]:
		needle = prefix.lower()
		return [
			e for e in self._cores.values()
			if (include_hidden or not e.hidden)
			and (
				needle in e.vlnv.lower()
				or needle in e.display_name.lower()
				or needle in e.description.lower()
			)
		]

	def items(self) -> Iterator[tuple[str, CatalogCoreEntry]]:
		return iter(self._cores.items())

	def values(self) -> ValuesView[CatalogCoreEntry]:
		return self._cores.values()


# ------------------------------------------------------------------
# Process-level cache
# ------------------------------------------------------------------

_CACHE: dict[tuple[str, tuple[str, ...]], Catalog] = {}


def get_catalog(vivado_path: str, ip_repos: list[str] | None = None) -> Catalog:
	key = (vivado_path, tuple(sorted(ip_repos or [])))

	if key not in _CACHE:
		_CACHE[key] = Catalog(vivado_path, ip_repos)

	return _CACHE[key]


def _load_ip_repo(ip_repo_path: str) -> dict[str, CatalogCoreEntry]:
	catalog: dict[str, CatalogCoreEntry] = {}

	if not os.path.isdir(ip_repo_path):
		return catalog

	for entry in os.scandir(ip_repo_path):
		if not entry.is_dir():
			continue
		component_xml_file = os.path.join(entry.path, "component.xml")

		if not os.path.isfile(component_xml_file):
			continue

		core = component_xml.parser(component_xml_file)

		if core:
			catalog[core.vlnv] = core

	return catalog