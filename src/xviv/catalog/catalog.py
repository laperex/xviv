from __future__ import annotations

from collections.abc import ValuesView
import logging
import os
from typing import Iterator

from xviv.catalog.model import CoreEntry
from xviv.catalog.parsers import load_ip_repo, parse_vv_index

logger = logging.getLogger(__name__)


class CoreNotFound(KeyError):
	def __init__(self, id: str) -> None:
		self.id = id
		super().__init__(f"Unable to resolve core: {id!r}")


class Catalog:
	"""
	Read-only view of all IP cores available to a Vivado installation.
	"""

	def __init__(self, vivado_path: str, ip_repos: list[str] | None = None) -> None:
		self._cores: dict[str, CoreEntry] = {}
		self._load(vivado_path, ip_repos or [])

	# ------------------------------------------------------------------
	# Construction
	# ------------------------------------------------------------------

	def _load(self, vivado_path: str, ip_repos: list[str]) -> None:
		xml_path = os.path.join(vivado_path, "data", "ip", "vv_index.xml")
		self._cores.update(parse_vv_index(xml_path))
		for repo in ip_repos:
			merged = load_ip_repo(repo)
			if merged:
				logger.debug("ip_repo %s: loaded %d cores", repo, len(merged))
			self._cores.update(merged)
		logger.debug("Catalog: %d total cores", len(self._cores))

	# ------------------------------------------------------------------
	# Iteration
	# ------------------------------------------------------------------

	def __len__(self) -> int:
		return len(self._cores)

	def __iter__(self) -> Iterator[CoreEntry]:
		return iter(self._cores.values())

	def __contains__(self, vlnv: str) -> bool:
		return vlnv in self._cores

	# ------------------------------------------------------------------
	# Lookups
	# ------------------------------------------------------------------

	def get(self, vlnv: str) -> CoreEntry | None:
		"""Exact VLNV match, returns None if not found."""
		return self._cores.get(vlnv)

	def lookup(self, id: str) -> CoreEntry:
		"""
		Resolve a core by exact VLNV or unambiguous partial match
		"""
		# Exact hit first
		entry = self._cores.get(id)
		if entry is not None:
			return entry

		# Partial substring match
		matches = [e for key, e in self._cores.items() if id in key]
		if len(matches) == 1:
			logger.info("Resolved %r → %s", id, matches[0].vlnv)
			return matches[0]
		if len(matches) > 1:
			candidates = ", ".join(e.vlnv for e in matches[:5])
			raise CoreNotFound(f"{id!r} is ambiguous: {candidates}...")

		raise CoreNotFound(id)

	def find_by_name(self, ip_name: str) -> list[CoreEntry]:
		"""All cores whose `name` field equals ip_name (any version)."""
		return [e for e in self._cores.values() if e.name == ip_name]

	# ------------------------------------------------------------------
	# Filtered views
	# ------------------------------------------------------------------

	def user_visible(self) -> list[CoreEntry]:
		return [e for e in self._cores.values() if not e.hidden]

	def search(
		self,
		prefix: str,
		*,
		include_hidden: bool = False,
	) -> list[CoreEntry]:
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

	def items(self) -> Iterator[tuple[str, CoreEntry]]:
		return iter(self._cores.items())

	def values(self) -> ValuesView[CoreEntry]:
		return self._cores.values()


# ------------------------------------------------------------------
# Process-level cache
# Keyed on (vivado_path, sorted ip_repos) so different repo
# combinations never collide.
# ------------------------------------------------------------------

_CACHE: dict[tuple[str, tuple[str, ...]], Catalog] = {}


def get_catalog(vivado_path: str, ip_repos: list[str] | None = None) -> Catalog:
	"""
	Return a cached Catalog for the given vivado_path + ip_repos combo.
	Completers and subcommands that don't hold a long-lived context can
	call this instead of constructing Catalog directly.
	"""
	key = (vivado_path, tuple(sorted(ip_repos or [])))
	if key not in _CACHE:
		_CACHE[key] = Catalog(vivado_path, ip_repos)
	return _CACHE[key]