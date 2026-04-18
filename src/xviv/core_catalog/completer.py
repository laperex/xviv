"""
completers.py  (additions to xviv.py)
======================================
Tab completion for the --core argument.

argcomplete dict protocol
--------------------------
When a completer returns a dict instead of a list, argcomplete passes it
to the shell with descriptions:

	zsh   → shows  "vlnv  --  description"  in the menu
	fish  → shows  "vlnv\tdescription"  inline
	bash  → shows vlnv only (bash has no native description support)

The dict format is:  { completion_value: description_string }

Two completers are provided:

_core_instance_completer
	Completes the --core NAME argument from [[core]] entries already
	defined in project.toml.  Enriches each name with its vlnv and
	display_name from vv_index.xml.

	Example output during tab:
		pixel_fifo     xilinx.com:ip:fifo_generator:13.2  FIFO Generator
		clk_wiz_0      xilinx.com:ip:clk_wiz:6.0          Clocking Wizard

_core_vlnv_completer
	Used when a new [[core]] is being defined and the user is completing
	the vlnv= value.  Scans vv_index.xml and shows display names and
	descriptions.  Filters by the typed prefix.

	Example output during tab of  "xilinx.com:ip:fifo<TAB>":
		xilinx.com:ip:fifo_generator:13.2   FIFO Generator  [xilinx.com/ip]
		xilinx.com:ip:axis_data_fifo:2.0    AXI4-Stream Data FIFO  [xilinx.com/ip]
"""

from __future__ import annotations

import logging
import os

from xviv.core_catalog import parser

logger = logging.getLogger(__name__)

# Maximum description width in terminal (characters)
_TERM_DESC_WIDTH = 80


# =============================================================================
# Completer 1: --core NAME  (completes configured instance names)
# =============================================================================

def _core_instance_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
	"""
	Complete configured [[core]] instance names from project.toml.

	For each name, the description shown is:
		<vlnv>   <DisplayName from vv_index.xml>

	Example (zsh menu):
		pixel_fifo   -- xilinx.com:ip:fifo_generator:13.2  FIFO Generator
		clk_wiz_0    -- xilinx.com:ip:clk_wiz:6.0  Clocking Wizard
	"""

	try:
		vivado_path = os.environ.get('XVIV_VIVADO_DIR') or ""
		catalog = parser.load(vivado_path)

		completions: dict[str, str] = {}

		for core in catalog.values():
			if not core.name.startswith(prefix):
				continue

			# Look up rich info from vv_index.xml
			entry = catalog.get(core.vlnv)

			if entry:
				desc = _fmt_instance_desc(core.vlnv, entry)
			else:
				# VLNV not in catalog (custom IP or wrong version)
				desc = f"{core.vlnv}  (not found in catalog)"

			completions[f"{core.name}:{core.version}"] = desc

		return completions
	except Exception as exc:
		logger.debug("_core_instance_completer failed: %s", exc)
		return {}


def _fmt_instance_desc(vlnv: str, entry) -> str:
	"""
	Format the description shown next to a configured core instance name.

		xilinx.com:ip:fifo_generator:13.2  FIFO Generator  — Configurable …
	"""
	parts = [vlnv, entry.display_name]

	flags = []
	if entry.hidden:
		flags.append("⚠ internal")
	if entry.board_dependent:
		flags.append("⚠ board-dep")
	if entry.ipi_only:
		flags.append("⚠ IPI-only")

	if flags:
		parts.append("  ".join(flags))

	desc_text = " ".join(entry.description.split())
	avail = _TERM_DESC_WIDTH - sum(len(p) + 2 for p in parts)
	if avail > 10 and desc_text:
		if len(desc_text) > avail:
			desc_text = desc_text[:avail - 1] + "…"
		parts.append(f"— {desc_text}")

	return "  ".join(parts)


# =============================================================================
# Completer 2: vlnv= value  (scans vv_index.xml for a new [[core]] entry)
# =============================================================================

def _core_vlnv_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
	"""
	Complete a VLNV string against vv_index.xml.

	Intended for use when adding a new [[core]] entry to project.toml —
	not for the --core CLI flag (which takes an instance name).

	The prefix is matched against the full VLNV string, the IP short name,
	and the display name, so partial matches work:

		"fifo"        → matches fifo_generator, axis_data_fifo, …
		"xilinx.com:ip:clk"  → matches clk_wiz, clk_in_blk, …
		"Clocking"    → matches via display_name

	The description shown is:
		<DisplayName>  [<vendor>/<library>]  <short description>

	Hidden subcores are excluded unless the prefix explicitly matches
	their VLNV (for power users who know what they're doing).
	"""
	
	return {}

	try:
		vivado_path = os.environ.get('XVIV_VIVADO_DIR') or ""
		catalog = parser.load(vivado_path)

		if not catalog:
			return {}

		needle = prefix.lower()
		completions: dict[str, str] = {}

		for vlnv, entry in sorted(catalog.items()):
			# Filter hidden unless the user has typed enough to be deliberate
			if entry.hidden and not vlnv.lower().startswith(needle):
				continue

			# Match against vlnv, display_name, description
			if not (
				needle in vlnv.lower()
				or needle in entry.display_name.lower()
				or needle in entry.name.lower()
			):
				continue

			completions[vlnv] = _fmt_vlnv_desc(entry)

		return completions

	except Exception as exc:
		logger.debug("_core_vlnv_completer failed: %s", exc)
		return {}


def _fmt_vlnv_desc(entry) -> str:
	"""
	Format the description shown next to a VLNV in completion.

		FIFO Generator  [xilinx.com/ip]  Configurable synchronous and …
	"""
	parts: list[str] = []

	# Display name is the primary identifier
	parts.append(entry.display_name or entry.name)

	# Vendor/library context
	parts.append(f"[{entry.vendor}/{entry.library}]")

	# Warning flags
	flags: list[str] = []
	if entry.hidden:
		flags.append("⚠ internal subcore")
	if entry.board_dependent:
		flags.append("⚠ board-dependent")
	if entry.ipi_only:
		flags.append("⚠ IPI-only")

	if flags:
		parts.append("  ".join(flags))
	else:
		# Short description — truncated to keep the line readable
		desc = " ".join(entry.description.split())
		avail = _TERM_DESC_WIDTH - sum(len(p) + 2 for p in parts)
		if avail > 12 and desc:
			if len(desc) > avail:
				desc = desc[:avail - 1] + "…"
			parts.append(desc)

	return "  ".join(parts)


# =============================================================================
# argparse wiring  (add to build_parser() in xviv.py)
# =============================================================================

"""
In build_parser(), inside the "create" subparser block, replace:

	c.add_argument("--core", metavar="NAME", ...)

with:

	c.add_argument(
		"--core",
		metavar="NAME",
		help="Instantiate an IP from Vivado's IP catalog",
	).completer = _core_instance_completer

The VLNV completer is registered separately on a dedicated search subcommand:

	# ---------------------------------------------------------------------------
	# search-core  (find a VLNV to put in project.toml)
	# ---------------------------------------------------------------------------
	c = sub.add_parser(
		"search-core",
		help="Search Vivado's IP catalog by name, VLNV, or keyword",
	)
	c.add_argument(
		"query",
		metavar="QUERY",
		help="IP name, partial VLNV, or keyword (e.g. 'fifo', 'clk_wiz')",
	).completer = _core_vlnv_completer

This gives the user two distinct workflows:

	# Find the right VLNV to use
	$ xviv search-core fifo<TAB>
	xilinx.com:ip:fifo_generator:13.2   FIFO Generator  [xilinx.com/ip]  …
	xilinx.com:ip:axis_data_fifo:2.0    AXI4-Stream Data FIFO  [xilinx.com/ip]  …

	# After adding [[core]] to project.toml, create it
	$ xviv create --core pixel_fifo<TAB>
	pixel_fifo   xilinx.com:ip:fifo_generator:13.2  FIFO Generator  — Configurable …
"""


# =============================================================================
# search-core command implementation  (add to command.py)
# =============================================================================

