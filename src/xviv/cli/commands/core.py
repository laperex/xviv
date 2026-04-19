

import typing
from xviv.config.model import ProjectConfig
from xviv.config.tcl import generate_config_tcl
from xviv.catalog import data
from xviv.tools import vivado

# -----------------------------------------------------------------------------
# create --vlnv <vlnv_id> --core <core_id>
# -----------------------------------------------------------------------------
def cmd_core_create(cfg: ProjectConfig, core_vlnv: typing.Optional[str], core_name: typing.Optional[str], edit: bool = False):
	config_tcl = generate_config_tcl(cfg, core_name=core_name, core_vlnv=core_vlnv)

	# cfg.vivado.mode = 'tcl'

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "create_core", [str(int(edit))], config_tcl)

# -----------------------------------------------------------------------------
# edit --core <core_id>
# -----------------------------------------------------------------------------
def cmd_core_edit(cfg: ProjectConfig, core_name: typing.Optional[str], nogui: bool = False):
	config_tcl = generate_config_tcl(cfg, core_name=core_name)

	if nogui:
		cfg.vivado.mode = 'tcl'

	vivado.run_vivado(cfg, vivado._find_tcl_script(), "edit_core", [str(int(not nogui))], config_tcl)

# -----------------------------------------------------------------------------
# search --query <query>
# -----------------------------------------------------------------------------
def cmd_search_core(cfg: ProjectConfig, query: str) -> None:
	catalog = data.load(cfg.vivado.path, [cfg.ip_repo])
	if not catalog:
		print("WARNING: vv_index.xml not found or empty. Check vivado.path in project.toml.")
		return

	needle = query.lower()
	matches = [
		entry for entry in sorted(catalog.values(), key=lambda e: e.vlnv)
		if not entry.hidden
		and (
			needle in entry.vlnv.lower()
			or needle in entry.display_name.lower()
			or needle in entry.name.lower()
			or needle in entry.description.lower()
		)
	]

	if not matches:
		print(f"No IPs found matching '{query}'.")
		print("Tip: try a partial name like 'fifo', 'clk', 'dma', or a vendor like 'xilinx'.")
		return

	# Column widths
	w_vlnv = min(max(len(e.vlnv) for e in matches), 52)
	w_name = min(max(len(e.display_name) for e in matches), 30)
	w_desc = 60

	header = (
		f"{'VLNV':<{w_vlnv}}  {'Display Name':<{w_name}}  {'Description':<{w_desc}}"
	)
	sep = f"{'─' * w_vlnv}  {'─' * w_name}  {'─' * w_desc}"

	print(f"\n{header}")
	print(sep)

	for entry in matches:
		vlnv_col = entry.vlnv[:w_vlnv]
		name_col = entry.display_name[:w_name]

		# Flags take priority over description
		flags = []
		if entry.board_dependent:
			flags.append("[board-dep]")
		if entry.ipi_only:
			flags.append("[IPI-only]")

		if flags:
			desc_col = "  ".join(flags)
		else:
			desc_text = " ".join(entry.description.split())
			desc_col = (
				desc_text[:w_desc - 1] + "…"
				if len(desc_text) > w_desc
				else desc_text
			)

		print(f"{vlnv_col:<{w_vlnv}}  {name_col:<{w_name}}  {desc_col}")

	print(f"\n{len(matches)} result(s). Add to project.toml:  vlnv = \"<VLNV>\"  in a [[core]] entry.")