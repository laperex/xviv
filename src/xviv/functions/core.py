import typing

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.tools import vivado

# -----------------------------------------------------------------------------
# create  --core <core_id> --vlnv <vlnv_id>
# -----------------------------------------------------------------------------
def cmd_core_create(cfg: XvivConfig, core_name: str, core_vlnv: str | None, edit: bool = False):
	config = (
		ConfigTclCommands(cfg)
		.create_core(core_name)
		.build()
	)

	vivado.run_vivado(cfg, config_tcl=config)

# -----------------------------------------------------------------------------
# edit --core <core_id>
# -----------------------------------------------------------------------------
def cmd_core_edit(cfg: XvivConfig, core_name: str, nogui: bool = False):
	config = (
		ConfigTclCommands(cfg)
		.edit_core(core_name, nogui=nogui)
		.build()
	)

	if nogui:
		cfg.get_vivado().mode = 'tcl'

	vivado.run_vivado(cfg, config_tcl=config)

# -----------------------------------------------------------------------------
# search --query <query>
# -----------------------------------------------------------------------------
def cmd_search_core(cfg: XvivConfig, query: str) -> None:
	catalog = cfg.get_catalog()

	needle = query.lower()
	matches = [
		entry for entry in sorted(catalog.values(), key=lambda e: e.vlnv)
		if not entry.hidden and (
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