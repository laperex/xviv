

from xviv.config.model import ProjectConfig
from xviv.core_catalog import parser


def cmd_search_core(cfg: ProjectConfig, query: str) -> None:
    """
    Print a formatted table of IPs matching `query` from vv_index.xml.
    Invoked by `xviv search-core <query>`.

    Output example:
        VLNV                                        Display Name              Description
        ──────────────────────────────────────────  ────────────────────────  ─────────────────────
        xilinx.com:ip:fifo_generator:13.2           FIFO Generator            Configurable FIFO …
        xilinx.com:ip:axis_data_fifo:2.0            AXI4-Stream Data FIFO     Insert buffering …
    """

    catalog = parser.load(cfg.vivado.path)
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

    print(f"\n{len(matches)} result(s).  "
          f"Add to project.toml:  vlnv = \"<VLNV>\"  in a [[core]] entry.")