from __future__ import annotations

import dataclasses
import shutil


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
			text = text[:desc_max - 1] + "..."
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _term_width() -> int:
	return shutil.get_terminal_size().columns