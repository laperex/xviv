import argparse
import os
from typing import Any

from xviv.config.project import XvivConfig

# ---------------------------------------------------------------------------
# Tree rendering primitives
# ---------------------------------------------------------------------------

_PIPE   = "│   "
_TEE    = "├── "
_LAST   = "└── "
_BLANK  = "    "


def _tree_lines(
	items: list[tuple[str, list[str]]],
	prefix: str = "",
) -> list[str]:
	"""
	Render a list of (label, children) pairs as tree lines.

	Each item is a (label, [child_line, ...]) tuple.
	Returns a flat list of strings ready to print.
	"""
	lines: list[str] = []
	for i, (label, children) in enumerate(items):
		is_last = i == len(items) - 1
		connector  = _LAST if is_last else _TEE
		child_pfx  = _BLANK if is_last else _PIPE

		lines.append(f"{prefix}{connector}{label}")
		for child in children:
			lines.append(f"{prefix}{child_pfx}{child}")

	return lines


def _section(title: str, rows: list[tuple[str, list[str]]]) -> list[str]:
	"""Render a top-level section with its rows as a sub-tree."""
	if not rows:
		return []

	lines = [f"{_TEE}{title}"]
	for i, (label, children) in enumerate(rows):
		is_last = i == len(rows) - 1
		connector = _LAST if is_last else _TEE
		child_pfx = _BLANK if is_last else _PIPE

		lines.append(f"{_PIPE}{connector}{label}")
		for child in children:
			lines.append(f"{_PIPE}{child_pfx}{child}")

	return lines


def _leaf(key: str, value: Any) -> str:
	"""Single key: value detail line."""
	return f"{key}: {value}"


def _detail(key: str, value: Any) -> list[str]:
	"""Return a one-element list if value is truthy, else empty."""
	return [_leaf(key, value)] if value else []


def _path(key: str, value: str | None) -> list[str]:
	"""Show only the basename to keep lines short, with the key label."""
	if not value:
		return []
	return [_leaf(key, os.path.basename(value))]


def _sources(sources: list[str]) -> list[str]:
	"""Render a sources list compactly."""
	if not sources:
		return []
	if len(sources) == 1:
		return [_leaf("src", os.path.basename(sources[0]))]
	lines = ["sources:"]
	for i, s in enumerate(sources):
		conn = _LAST if i == len(sources) - 1 else _TEE
		lines.append(f"    {conn}{os.path.basename(s)}")
	return lines


# ---------------------------------------------------------------------------
# Per-entity renderers
# ---------------------------------------------------------------------------

def _render_fpga(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for fpga in cfg._fpga_list:
		children = []
		if fpga.fpga_part:
			children.append(_leaf("part",  fpga.fpga_part))
		if fpga.board_part:
			children.append(_leaf("board", fpga.board_part))
		rows.append((f"[fpga]  {fpga.name}", children))
	return rows


def _render_ip(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for ip in cfg._ip_list:
		children = [
			_leaf("vlnv",  ip.vlnv),
			_leaf("fpga",  ip.fpga_ref),
			_leaf("top",   ip.top),
			*_sources(ip.sources),
		]

		# Show wrapper if one exists
		wrapper = cfg._get_wrapper_cfg_optional(ip.name)
		if wrapper:
			children.append(
				_leaf("wrapper", os.path.basename(wrapper.wrapper_file))
			)

		rows.append((f"[ip]  {ip.name}", children))
	return rows


def _render_core(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for core in cfg._core_list:
		children = [
			_leaf("vlnv", core.vlnv),
			_leaf("fpga", core.fpga_ref),
			*_path("xci",  core.xci_file),
		]
		rows.append((f"[core]  {core.name}", children))
	return rows


def _render_bd(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for bd in cfg._bd_list:
		children = [
			_leaf("fpga", bd.fpga_ref),
			*_path("bd_file", bd.bd_file),
			*_path("save",    bd.save_file),
		]
		if bd.vlnv_list:
			children.append(_leaf("ip_count", len(bd.vlnv_list)))
		if bd.core_list:
			children.append(f"sub_cores: {len(bd.core_list)}")
			for sc in bd.core_list:
				children.append(f"    {_TEE}{sc.name}  ({sc.vlnv})")
		rows.append((f"[bd]  {bd.name}", children))
	return rows


def _render_design(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for d in cfg._design_list:
		children = [
			_leaf("top",  d.top),
			_leaf("fpga", d.fpga_ref),
			*_sources(d.sources),
		]
		rows.append((f"[design]  {d.name}", children))
	return rows


def _render_synth(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for s in cfg._synth_list:
		ref  = s.design_name or s.bd_name or s.core_name
		kind = (
			"design" if s.design_name else
			"bd"     if s.bd_name     else
			"core"
		)

		# Build stage flags concisely
		stages = []
		if s.run_synth:  stages.append("synth")
		if s.run_opt:    stages.append("opt")
		if s.run_place:  stages.append("place")
		if s.run_phys_opt: stages.append("phys_opt")
		if s.run_route:  stages.append("route")

		children = [
			_leaf("ref",   f"{kind}/{ref}"),
			_leaf("top",   s.top),
			_leaf("fpga",  s.fpga_ref),
			_leaf("stages", " → ".join(stages) if stages else "none"),
		]

		if s.constraints:
			children.append(_leaf("constraints", len(s.constraints)))

		# Outputs
		outputs = []
		if s.bitstream_file:
			outputs.append(_path("bit",  s.bitstream_file)[0])
		if s.synth_dcp_file:
			outputs.append(_path("synth_dcp", s.synth_dcp_file)[0])
		if s.route_dcp_file:
			outputs.append(_path("route_dcp", s.route_dcp_file)[0])
		if s.hw_platform_xsa_file:
			outputs.append(_path("xsa", s.hw_platform_xsa_file)[0])

		if outputs:
			children.append("outputs:")
			for i, o in enumerate(outputs):
				conn = _LAST if i == len(outputs) - 1 else _TEE
				children.append(f"    {conn}{o}")

		label = f"[synth]  {ref}"
		if s.synth_incremental or s.impl_incremental:
			label += "  (incremental)"

		rows.append((label, children))
	return rows


def _render_simulation(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for sim in cfg._sim_list:
		children = [
			_leaf("top",     sim.top),
			_leaf("backend", sim.backend),
		]
		if sim.design:
			children.append(_leaf("design", sim.design))
		children += _sources(sim.sources)
		rows.append((f"[sim]  {sim.name}", children))
	return rows


def _render_platform(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for p in cfg._platform_list:
		children = [
			_leaf("cpu", p.cpu),
			_leaf("os",  p.os),
			*_path("xsa",       p.xsa_file),
			*_path("bitstream", p.bitstream_file),
		]
		rows.append((f"[platform]  {p.name}", children))
	return rows


def _render_app(cfg: XvivConfig) -> list[tuple[str, list[str]]]:
	rows = []
	for app in cfg._app_list:
		children = [
			_leaf("platform", app.platform),
			_leaf("template", app.template),
			*_path("elf",     app.elf_file),
			*_sources(app.sources),
		]
		rows.append((f"[app]  {app.name}", children))
	return rows


# ---------------------------------------------------------------------------
# Dependency / cross-reference summary
# ---------------------------------------------------------------------------

def _render_dependency_map(cfg: XvivConfig) -> list[str]:
	"""
	Separate compact section showing the inter-entity dependency chains,
	e.g.  design/cv_pipeline → synth/cv_pipeline → platform/pynq → app/hello
	"""
	chains: list[str] = []

	# Walk synth → platform → app chains
	for synth in cfg._synth_list:
		ref  = synth.design_name or synth.bd_name or synth.core_name
		node = f"{ref}"

		# Find platforms that consume this synth's XSA
		for plat in cfg._platform_list:
			if plat.xsa_file == synth.hw_platform_xsa_file:
				plat_node = f"platform/{plat.name}"

				# Find apps on this platform
				apps = [a for a in cfg._app_list if a.platform == plat.name]
				if apps:
					for app in apps:
						chains.append(
							f"{node} → synth/{synth.top} "
							f"→ {plat_node} → app/{app.name}"
						)
				else:
					chains.append(f"{node} → synth/{synth.top} → {plat_node}")

		# Sims that reference this design
		if synth.design_name:
			for sim in cfg._sim_list:
				if sim.design == synth.design_name:
					chains.append(
						f"{ref} → sim/{sim.name}"
					)

	if not chains:
		return []

	lines = [f"{_TEE}dependency chains"]
	for i, chain in enumerate(chains):
		conn = _LAST if i == len(chains) - 1 else _TEE
		lines.append(f"{_PIPE}{conn}{chain}")

	return lines


def cmd_graph(cfg: XvivConfig, args: argparse.Namespace) -> None:
	# dry_run is set by super but graph never calls vivado, so ignore it.
	only = getattr(args, "filter", None)
	no_deps = getattr(args, "no_deps", False)

	project_name = os.path.basename(cfg.base_dir)
	print(f"{project_name}/")

	# Ordered sections
	sections: list[tuple[str, list[tuple[str, list[str]]]]] = [
		("fpga",     _render_fpga(cfg)),
		("ip",       _render_ip(cfg)),
		("core",     _render_core(cfg)),
		("bd",       _render_bd(cfg)),
		("design",   _render_design(cfg)),
		("synth",    _render_synth(cfg)),
		("sim",      _render_simulation(cfg)),
		("platform", _render_platform(cfg)),
		("app",      _render_app(cfg)),
	]

	# Apply --filter
	if only:
		sections = [(k, v) for k, v in sections if k == only]
		if not sections:
			print(f"    (no entries of kind '{only}')")
			return

	# Render visible sections
	visible = [(k, v) for k, v in sections if v]
	dep_lines = [] if no_deps else _render_dependency_map(cfg)
	total = len(visible) + (1 if dep_lines else 0)

	for idx, (_, rows) in enumerate(visible):
		is_last_section = (idx == total - 1) and not dep_lines
		section_pfx     = _BLANK if is_last_section else _PIPE

		for i, (label, children) in enumerate(rows):
			is_last_row = i == len(rows) - 1 and is_last_section
			row_conn    = _LAST if is_last_row else _TEE

			print(f"{section_pfx}{row_conn}{label}")

			child_pfx = _BLANK if is_last_row else (section_pfx + _PIPE)
			for j, child in enumerate(children):
				is_last_child = j == len(children) - 1
				child_conn    = _LAST if is_last_child else _TEE
				# children may themselves contain multi-line entries
				# (e.g. sources block) — print verbatim if they already
				# contain tree chars, otherwise prefix with connector
				if child.startswith("    ") or "──" in child:
					print(f"{child_pfx}    {child}")
				else:
					print(f"{child_pfx}{child_conn}{child}")

	# Dependency chain summary
	for line in dep_lines:
		print(line)

	# Footer counts
	print()
	counts = [
		f"{len(v)} {k}"
		for k, v in sections
		if v
	]
	print("    " + "  ·  ".join(counts))