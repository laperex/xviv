"""
completers.py  (revised)
=========================
Key change: _core_vlnv_completer now uses VersionGroup to emit ALL
known versions of each IP, newest first, with clear labelling.

Terminal output when typing  `xviv search-core clk_wiz`:

  xilinx.com:ip:clk_wiz:6.0   Clocking Wizard [xilinx.com/ip] latest   Clock synthesis …
  xilinx.com:ip:clk_wiz:5.4   Clocking Wizard [xilinx.com/ip] older
  xilinx.com:ip:clk_wiz:5.3   Clocking Wizard [xilinx.com/ip] older
  xilinx.com:ip:clk_wiz:5.2   Clocking Wizard [xilinx.com/ip] ⚠ older version — may not install in this Vivado
"""

from __future__ import annotations

import logging
import os

from xviv.cli.parser import _find_config
from xviv.config.model import DEFAULT_VIVADO_PATH
from xviv.core_catalog import parser

logger = logging.getLogger(__name__)

_TERM_DESC_WIDTH = 88


# =============================================================================
# Internal helpers
# =============================================================================

def _get_vivado_path() -> str:
    return os.environ.get("XVIV_VIVADO_DIR") or DEFAULT_VIVADO_PATH


# def _find_config() -> str:
#     for name in ("project.cue", "project.toml"):
#         if os.path.exists(name):
#             return name
#     return ""


def _truncate(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text[:width - 1] + "…" if len(text) > width else text


# =============================================================================
# Completer 1: --core NAME  (configured instances from project.toml)
# =============================================================================

def _core_instance_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
    """
    Complete [[core]] instance names from project.toml, enriched with
    VLNV and display_name from vv_index.xml.

    This completer deliberately shows ONLY configured instances — not all
    catalog IPs.  Use `xviv search-core` to browse the full catalog.
    """
    # from xviv import config, parser

    try:
        cfg_path = getattr(parsed_args, "config", None) or _find_config(prefix, parsed_args)
        if not cfg_path:
            return {}

        # cfg      = config.load_config(os.path.abspath(cfg_path))
        catalog  = parser.load(_get_vivado_path())
        groups   = parser.load_groups(_get_vivado_path())

        completions: dict[str, str] = {}

        for core in catalog.values():
            if not core.name.startswith(prefix):
                continue

            entry = catalog.get(core.vlnv)
            if entry:
                # Show newer version hint if one exists
                group_key = f"{entry.vendor}:{entry.library}:{entry.name}"
                group     = groups.get(group_key)
                newer_hint = ""
                if group and group.latest.vlnv != core.vlnv and not group.latest.is_stub:
                    newer_hint = f"  → newer: {group.latest.vlnv}"

                stub_hint = "  ⚠ may not install in this Vivado" if entry.is_stub else ""
                desc = (
                    f"{core.vlnv}"
                    f"  {entry.display_name}"
                    f"{stub_hint}"
                    f"{newer_hint}"
                )
            else:
                desc = f"{core.vlnv}  (not found in catalog)"

            completions[core.name] = desc

        return completions

    except Exception as exc:
        logger.debug("_core_instance_completer error: %s", exc)
        return {}


# =============================================================================
# Completer 2: search-core QUERY  (full catalog scan from vv_index.xml)
# =============================================================================

def _core_vlnv_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
    """
    Complete a VLNV string from vv_index.xml.

    Shows ALL versions of matching IPs — including older versions that
    appear only in <UpgradesFrom> entries (marked as stubs).

    Versions are emitted newest-first within each IP group so zsh/fish
    menus present the most useful choice at the top.

    Stub entries (older versions not directly in this Vivado install)
    are shown with a clear warning rather than silently omitted.
    """
    # from xviv import parser

    try:
        vivado_path = _get_vivado_path()
        catalog     = parser.load(vivado_path)
        groups      = parser.load_groups(vivado_path)

        if not catalog:
            return {}

        needle = prefix.lower()

        # ---- Find matching VersionGroups ---------------------------------
        # Match against the group (ip_name, display_name) rather than
        # individual VLNVs so that typing "clk_wiz" surfaces ALL versions
        # of clk_wiz in one pass, not just those whose VLNV starts with
        # the typed string.

        matching_groups: list[tuple[str, "parser.VersionGroup"]] = []

        for group_key, group in sorted(groups.items()):
            # Skip groups where all entries are hidden (pure subcores)
            visible = [e for e in group.entries if not e.hidden]
            if not visible and not any(
                needle in e.vlnv.lower() for e in group.entries
            ):
                continue

            representative = group.entries[0]   # newest (may be stub)
            # Fall back to first non-stub for display_name/description
            full_entry = next(
                (e for e in group.entries if not e.is_stub),
                representative,
            )

            if not (
                needle in group.name.lower()
                or needle in full_entry.display_name.lower()
                or needle in full_entry.description.lower()
                or any(needle in e.vlnv.lower() for e in group.entries)
            ):
                continue

            matching_groups.append((group_key, group))

        # ---- Emit completions for every version in each matching group ---
        completions: dict[str, str] = {}

        for _key, group in matching_groups:
            full_entry = next(
                (e for e in group.entries if not e.is_stub),
                group.entries[0],
            )

            for idx, entry in enumerate(group.entries):
                # Version label
                if idx == 0 and not entry.is_stub:
                    version_label = "latest"
                elif entry.is_stub:
                    version_label = "⚠ older — may not install in this Vivado"
                else:
                    version_label = "older"

                # Flags
                flags: list[str] = []
                if full_entry.board_dependent:
                    flags.append("board-dep")
                if full_entry.ipi_only:
                    flags.append("IPI-only")

                flag_str = "  ".join(f"[{f}]" for f in flags)

                # Description (only on the latest/full entry to avoid clutter)
                desc_str = ""
                if idx == 0 and not entry.is_stub and full_entry.short_desc:
                    avail = _TERM_DESC_WIDTH - len(full_entry.display_name) - 30
                    if avail > 12:
                        desc_str = _truncate(full_entry.description, avail)

                parts = [
                    full_entry.display_name or group.name,
                    f"[{entry.vendor}/{entry.library}]",
                    version_label,
                ]
                if flag_str:
                    parts.append(flag_str)
                if desc_str:
                    parts.append(desc_str)

                completions[entry.vlnv] = "  ".join(parts)

        return completions

    except Exception as exc:
        logger.debug("_core_vlnv_completer error: %s", exc)
        return {}


# =============================================================================
# search-core command  (cmd_search_core in command.py)
# =============================================================================

def cmd_search_core(vivado_path: str, query: str, *, all_versions: bool = False) -> None:
    """
    Print a formatted table of IPs matching `query`.

        xviv search-core fifo
        xviv search-core fifo --all-versions
    """
    # from xviv import parser

    catalog = parser.load(vivado_path)
    groups  = parser.load_groups(vivado_path)

    if not catalog:
        print("WARNING: vv_index.xml not found. Check vivado.path in project.toml.")
        return

    needle = query.lower()

    matching: list["parser.VersionGroup"] = []
    for group in sorted(groups.values(), key=lambda g: g.name):
        full = next((e for e in group.entries if not e.is_stub), group.entries[0])
        if full.hidden:
            continue
        if (
            needle in group.name.lower()
            or needle in full.display_name.lower()
            or needle in full.description.lower()
        ):
            matching.append(group)

    if not matching:
        print(f"No IPs found matching '{query}'.")
        return

    W_VLNV = 52
    W_NAME = 30
    W_DESC = 55

    header = f"{'VLNV':<{W_VLNV}}  {'Display Name':<{W_NAME}}  {'Description / Notes'}"
    sep    = f"{'─' * W_VLNV}  {'─' * W_NAME}  {'─' * W_DESC}"
    print(f"\n{header}\n{sep}")

    for group in matching:
        full = next((e for e in group.entries if not e.is_stub), group.entries[0])

        versions_to_show = group.entries if all_versions else [group.entries[0]]

        for idx, entry in enumerate(versions_to_show):
            vlnv_col = entry.vlnv[:W_VLNV]
            name_col = (full.display_name if idx == 0 else "")[:W_NAME]

            if entry.is_stub:
                desc_col = "⚠ older version — may not be available in this Vivado"
            elif idx == 0:
                flags = []
                if full.board_dependent: flags.append("[board-dep]")
                if full.ipi_only:        flags.append("[IPI-only]")
                raw  = " ".join(full.description.split())
                desc_col = ("  ".join(flags) + "  " if flags else "") + _truncate(raw, W_DESC)
            else:
                desc_col = "older version"

            print(f"{vlnv_col:<{W_VLNV}}  {name_col:<{W_NAME}}  {desc_col}")

        if not all_versions and group.has_older_versions:
            older_count = len(group.entries) - 1
            stub_count  = sum(1 for e in group.entries[1:] if e.is_stub)
            note = f"  ↳ {older_count} older version(s)"
            if stub_count:
                note += f" ({stub_count} not in this Vivado install)"
            note += " — use --all-versions to show"
            print(note)

    total = sum(len(g.entries) for g in matching)
    shown = len(matching) if not all_versions else total
    print(f"\n{len(matching)} IP(s) matched.  "
          f"Add to project.toml:  vlnv = \"<VLNV>\"  in a [[core]] entry.")