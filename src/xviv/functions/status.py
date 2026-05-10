from __future__ import annotations

import argparse
import dataclasses
import os
import time
from enum import Enum
from typing import TYPE_CHECKING

from xviv.config.project import XvivConfig

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------

class State(Enum):
    OK      = "OK"       # artifact exists, sources not newer
    STALE   = "STALE"    # artifact exists but at least one source is newer
    MISSING = "MISSING"  # artifact was never built
    PARTIAL = "PARTIAL"  # some artifacts present, some missing
    NA      = "N/A"      # no build artifact for this entity type


# Colours (disabled automatically when not a tty)
_USE_COLOR = os.isatty(1)

_COLOR = {
    State.OK:      "\033[32m",   # green
    State.STALE:   "\033[33m",   # yellow
    State.MISSING: "\033[31m",   # red
    State.PARTIAL: "\033[33m",   # yellow
    State.NA:      "\033[90m",   # grey
}
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"

_ICON = {
    State.OK:      "✓",
    State.STALE:   "~",
    State.MISSING: "✗",
    State.PARTIAL: "±",
    State.NA:      "·",
}


@dataclasses.dataclass
class Artifact:
    """A single output file that contributes to an entity's state."""
    label:  str
    path:   str | None


@dataclasses.dataclass
class EntityStatus:
    kind:      str         # fpga / ip / design / synth / ...
    name:      str
    state:     State
    artifacts: list[Artifact]
    details:   list[str]   # extra one-line notes (fpga part, stages, etc.)
    sources:   list[str]   # source files used to detect staleness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mtime(path: str | None) -> float | None:
    if path and os.path.exists(path):
        return os.path.getmtime(path)
    return None


def _age(path: str | None) -> str:
    mt = _mtime(path)
    if mt is None:
        return ""
    delta = time.time() - mt
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    return f"{int(delta / 86400)}d ago"


def _artifact_state(artifacts: list[Artifact], sources: list[str]) -> State:
    """
    Derive a State from a list of Artifacts and their source files.

    Rules:
    - If no artifacts are defined            → NA
    - If none exist                          → MISSING
    - If some exist, some don't              → PARTIAL
    - If all exist, any source is newer      → STALE
    - All exist, no source is newer          → OK
    """
    paths = [a.path for a in artifacts if a.path]
    if not paths:
        return State.NA

    existing = [p for p in paths if os.path.exists(p)]

    if not existing:
        return State.MISSING
    if len(existing) < len(paths):
        return State.PARTIAL

    # All artifacts present — check staleness against sources
    oldest_artifact = min(os.path.getmtime(p) for p in existing)
    for src in sources:
        if os.path.exists(src) and os.path.getmtime(src) > oldest_artifact:
            return State.STALE

    return State.OK


def _colorize(state: State, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"{_COLOR[state]}{text}{_RESET}"


def _bold(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}" if _USE_COLOR else text


def _dim(text: str) -> str:
    return f"{_DIM}{text}{_RESET}" if _USE_COLOR else text


# ---------------------------------------------------------------------------
# Per-entity status builders
# ---------------------------------------------------------------------------

def _status_fpga(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for fpga in cfg._fpga_list:
        details = []
        if fpga.fpga_part:
            details.append(f"part: {fpga.fpga_part}")
        if fpga.board_part:
            details.append(f"board: {fpga.board_part}")
        out.append(EntityStatus(
            kind="fpga", name=fpga.name,
            state=State.NA,
            artifacts=[], sources=[], details=details,
        ))
    return out


def _status_ip(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for ip in cfg._ip_list:
        ip_dir = os.path.join(ip.repo, f"{ip.name}_{ip.version}".replace(".", "_"))
        comp_xml = os.path.join(ip_dir, "component.xml")

        artifacts = [Artifact("component.xml", comp_xml)]
        state     = _artifact_state(artifacts, ip.sources)

        details = [f"vlnv: {ip.vlnv}", f"fpga: {ip.fpga_ref}"]

        wrapper = cfg._get_wrapper_cfg_optional(ip.name)
        if wrapper:
            w_artifact = Artifact("wrapper", wrapper.wrapper_file)
            artifacts.append(w_artifact)
            state = _artifact_state(artifacts, ip.sources + wrapper.sources)
            details.append(f"wrapper: {os.path.basename(wrapper.wrapper_file)}")

        out.append(EntityStatus(
            kind="ip", name=ip.name,
            state=state, artifacts=artifacts, sources=ip.sources, details=details,
        ))
    return out


def _status_core(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for core in cfg._core_list:
        artifacts = [Artifact("xci", core.xci_file)]
        state     = _artifact_state(artifacts, [])
        details   = [f"vlnv: {core.vlnv}", f"fpga: {core.fpga_ref}"]
        out.append(EntityStatus(
            kind="core", name=core.name,
            state=state, artifacts=artifacts, sources=[], details=details,
        ))
    return out


def _status_bd(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for bd in cfg._bd_list:
        artifacts = [
            Artifact("bd_file",  bd.bd_file),
            Artifact("wrapper",  bd.bd_wrapper_file),
        ]
        sources = [bd.save_file] if os.path.exists(bd.save_file) else []
        state   = _artifact_state(artifacts, sources)
        details = [
            f"fpga: {bd.fpga_ref}",
            f"ip_count: {len(bd.vlnv_list)}",
        ]
        out.append(EntityStatus(
            kind="bd", name=bd.name,
            state=state, artifacts=artifacts, sources=sources, details=details,
        ))
    return out


def _status_design(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for d in cfg._design_list:
        missing_src = [s for s in d.sources if not os.path.exists(s)]
        if missing_src:
            state = State.MISSING
        else:
            state = State.OK if d.sources else State.NA

        details = [f"top: {d.top}", f"fpga: {d.fpga_ref}"]
        if missing_src:
            details.append(f"missing sources: {len(missing_src)}")

        out.append(EntityStatus(
            kind="design", name=d.name,
            state=state, artifacts=[], sources=d.sources, details=details,
        ))
    return out


def _status_synth(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for s in cfg._synth_list:
        ref = s.design_name or s.bd_name or s.core_name

        # Ordered: only artifacts that are configured (not None)
        artifacts = [
            a for a in [
                Artifact("synth.dcp", s.synth_dcp_file),
                Artifact("place.dcp", s.place_dcp_file),
                Artifact("route.dcp", s.route_dcp_file),
                Artifact("bitstream", s.bitstream_file),
                Artifact("xsa",       s.hw_platform_xsa_file),
            ] if a.path
        ]

        # Sources: design or bd files
        sources: list[str] = []
        if s.design_name:
            design = cfg._get_design_cfg_optional(s.design_name)
            if design:
                sources = design.sources
        if s.bd_name:
            bd = cfg._get_bd_cfg_optional(s.bd_name)
            if bd and os.path.exists(bd.bd_file):
                sources = [bd.bd_file]

        state = _artifact_state(artifacts, sources)

        stages = [
            label for flag, label in [
                (s.run_synth,    "synth"),
                (s.run_opt,      "opt"),
                (s.run_place,    "place"),
                (s.run_phys_opt, "phys_opt"),
                (s.run_route,    "route"),
            ] if flag
        ]

        details = [
            f"ref: {ref}",
            f"top: {s.top}",
            f"stages: {' → '.join(stages) if stages else 'none'}",
        ]

        out.append(EntityStatus(
            kind="synth", name=ref,
            state=state, artifacts=artifacts, sources=sources, details=details,
        ))
    return out


def _status_simulation(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for sim in cfg._sim_list:
        wdb  = os.path.join(sim.work_dir or "", f"{sim.top}.wdb") if sim.work_dir else None
        artifacts = [Artifact("wdb", wdb)]

        sources = list(sim.sources)
        if sim.design:
            design = cfg._get_design_cfg_optional(sim.design)
            if design:
                sources = design.sources + sources

        state   = _artifact_state(artifacts, sources)
        details = [f"top: {sim.top}", f"backend: {sim.backend}"]
        if sim.design:
            details.append(f"design: {sim.design}")

        out.append(EntityStatus(
            kind="sim", name=sim.name,
            state=state, artifacts=artifacts, sources=sources, details=details,
        ))
    return out


def _status_platform(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for p in cfg._platform_list:
        bsp_lib = os.path.join(p.dir, p.cpu, "lib", "libxil.a")
        artifacts = [
            Artifact("bsp_lib", bsp_lib),
            Artifact("xsa",     p.xsa_file),
        ]
        state   = _artifact_state(artifacts, [p.xsa_file] if os.path.exists(p.xsa_file) else [])
        details = [f"cpu: {p.cpu}", f"os: {p.os}"]
        out.append(EntityStatus(
            kind="platform", name=p.name,
            state=state, artifacts=artifacts, sources=[], details=details,
        ))
    return out


def _status_app(cfg: XvivConfig) -> list[EntityStatus]:
    out = []
    for app in cfg._app_list:
        artifacts = [Artifact("elf", app.elf_file)]
        sources   = list(app.sources)

        # Mark stale if platform BSP is newer than ELF
        plat = cfg._get_platform_cfg_optional(app.platform)
        if plat:
            bsp_lib = os.path.join(plat.dir, plat.cpu, "lib", "libxil.a")
            if os.path.exists(bsp_lib):
                sources.append(bsp_lib)

        state   = _artifact_state(artifacts, sources)
        details = [f"platform: {app.platform}", f"template: {app.template}"]
        out.append(EntityStatus(
            kind="app", name=app.name,
            state=state, artifacts=artifacts, sources=sources, details=details,
        ))
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_W_KIND  = 8
_W_NAME  = 28
_W_STATE = 7


def _render_row(es: EntityStatus, verbose: bool) -> list[str]:
    icon  = _ICON[es.state]
    state_str = es.state.value
    colored_icon  = _colorize(es.state, icon)
    colored_state = _colorize(es.state, f"{state_str:<{_W_STATE}}")

    # Primary artifact for age display
    primary = next(
        (a for a in es.artifacts if a.path and os.path.exists(a.path)), None
    )
    age = _age(primary.path) if primary else ""

    row = (
        f"  {colored_icon}  "
        f"{_bold(es.kind):<{_W_KIND + (10 if _USE_COLOR else 0)}}  "
        f"{es.name:<{_W_NAME}}  "
        f"{colored_state}  "
        f"{_dim(age):<12}"
    )

    lines = [row]

    if not verbose:
        return lines

    # Verbose: artifact breakdown + details
    indent = "         "   # aligns under the name column

    for detail in es.details:
        lines.append(f"{indent}{_dim(detail)}")

    for i, art in enumerate(es.artifacts):
        if not art.path:
            continue
        exists   = os.path.exists(art.path)
        art_icon = "✓" if exists else "✗"
        art_col  = _colorize(State.OK if exists else State.MISSING, art_icon)
        basename = os.path.basename(art.path)
        art_age  = _age(art.path) if exists else "not built"
        lines.append(
            f"{indent}{art_col} {art.label:<14} {basename:<30} {_dim(art_age)}"
        )

    # Stale: show which source is newer
    if es.state == State.STALE and es.artifacts:
        existing_arts = [a.path for a in es.artifacts if a.path and os.path.exists(a.path)]
        if existing_arts:
            oldest = min(os.path.getmtime(p) for p in existing_arts)
            for src in es.sources:
                if os.path.exists(src) and os.path.getmtime(src) > oldest:
                    lines.append(
                        f"{indent}{_colorize(State.STALE, '~ newer source:')} "
                        f"{os.path.basename(src)}"
                    )

    return lines


def _render_summary(statuses: list[EntityStatus]) -> list[str]:
    counts: dict[State, int] = {s: 0 for s in State}
    for es in statuses:
        counts[es.state] += 1

    parts = []
    for state in [State.OK, State.STALE, State.PARTIAL, State.MISSING, State.NA]:
        n = counts[state]
        if n:
            parts.append(_colorize(state, f"{_ICON[state]} {n} {state.value}"))

    return ["", "  " + "   ".join(parts)]


def _render_header() -> str:
    kind_h  = f"{'KIND':<{_W_KIND}}"
    name_h  = f"{'NAME':<{_W_NAME}}"
    state_h = f"{'STATE':<{_W_STATE}}"
    age_h   = "LAST BUILT"
    return (
        f"  {'':2}  {_bold(kind_h)}  {_bold(name_h)}  "
        f"{_bold(state_h)}  {_bold(age_h)}"
    )


def cmd_status(cfg: XvivConfig, args: argparse.Namespace) -> None:
	verbose = getattr(args, "verbose", False)
	only    = getattr(args, "filter",  None)
	stale_only = getattr(args, "stale", False)

	# Collect all statuses
	builders = [
		("fpga",     _status_fpga),
		("ip",       _status_ip),
		("core",     _status_core),
		("bd",       _status_bd),
		("design",   _status_design),
		("synth",    _status_synth),
		("sim",      _status_simulation),
		("platform", _status_platform),
		("app",      _status_app),
	]

	all_statuses: list[EntityStatus] = []
	for kind, builder in builders:
		if only and kind != only:
			continue
		all_statuses.extend(builder(cfg))

	if stale_only:
		all_statuses = [
			es for es in all_statuses
			if es.state in (State.STALE, State.MISSING, State.PARTIAL)
		]

	if not all_statuses:
		print("  (nothing to show)")
		return

	print()
	print(_render_header())
	print("  " + "─" * 72)

	prev_kind = None
	for es in all_statuses:
		# Blank separator between entity kinds
		if prev_kind and es.kind != prev_kind:
			print()
		prev_kind = es.kind

		for line in _render_row(es, verbose):
			print(line)

	for line in _render_summary(all_statuses):
		print(line)

	print()