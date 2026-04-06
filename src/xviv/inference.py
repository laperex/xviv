#!/usr/bin/env python3
"""
sv_to_vivado_tcl.py
====================
Parse a SystemVerilog / Verilog module definition using **pyslang** and emit
a Vivado IP-XACT TCL script that registers every port as a named bus interface.

Dependencies
------------
	pip install pyslang          # MIT-licensed, covers SV-2017 + Verilog-2005

Supported interface types
-------------------------
	AXI4, AXI4-Lite, AXI-Stream, APB, AHB-Lite,
	BRAM, FIFO-Write, FIFO-Read,
	I2C (IIC), SPI, UART, CAN,
	GPIO, Diff-Clock, MII, GMII, RGMII, SGMII, XGMII,
	Clock (signal), Reset (signal), Interrupt (signal)

Vivado compatibility
--------------------
	:1.0 VLNV  ->  Vivado 2014.1 -> 2024.x  (default, --vlnv-v2 NOT set)
	:2.0 VLNV  ->  Vivado 2024.2+           (use --vlnv-v2)

Usage
-----
	python sv_to_vivado_tcl.py <module.sv> [options]

	Options
	-o / --output FILE    Write TCL to FILE (default: <module_name>_interfaces.tcl)
	--top NAME            Override top module name when file has multiple modules
	--dry-run             Print TCL to stdout only, do not write a file
	--strict              Exit with error if any port cannot be assigned
	--verbose             Print debug grouping / scoring info
	--vlnv-v2             Use :2.0 VLNV suffixes for AXI interfaces (Vivado 2024.2+)

pyslang API surface used (all confirmed via help()):
----------------------------------------------------
	SyntaxTree.fromFile(str)                -> SyntaxTree
	Compilation()
	Compilation.addSyntaxTree(SyntaxTree)
	Compilation.getAllDiagnostics()
	Compilation.getRoot()                   -> RootSymbol
	RootSymbol.topInstances                 -> iterable of InstanceSymbol
	InstanceSymbol.isModule                 -> bool
	InstanceSymbol.name                     -> str   (via Symbol)
	InstanceSymbol.body                     -> InstanceBodySymbol
	InstanceBodySymbol.portList             -> iterable of PortSymbol
	Scope.__iter__                          -> Iterator[Symbol]  (fallback)
	Symbol.kind.name                        -> str
	Symbol.name                             -> str
	PortSymbol.direction                    -> ArgumentDirection
	PortSymbol.type                         -> Type
	Type.bitWidth                           -> int
	ArgumentDirection.In / Out / InOut / Ref

Author : generated helper
License: MIT
"""

from __future__ import annotations

import sys
import re as _re
import argparse
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# 0.  pyslang import guard
# -----------------------------------------------------------------------------

try:
	import pyslang
except ImportError:
	sys.exit(
		"[ERROR] pyslang is not installed.\n"
		"        Run:  pip install pyslang\n"
		"        Docs: https://github.com/MikePopoloski/slang"
	)


# -----------------------------------------------------------------------------
# 1.  Interface Database
# -----------------------------------------------------------------------------

@dataclass
class InterfaceDef:
	"""Describes one Vivado bus / signal interface type."""
	key:          str
	vlnv:         str                        # abstraction VLNV  (:1.0 form)
	bus_vlnv:     str                        # bus-type VLNV     (:1.0 form)
	signals:      Dict[str, List[str]]       # logical -> accepted physical suffixes
	required:     List[str]                  # logical names that MUST be present
	mode_support: List[str]                  # 'slave' | 'master' | 'monitor'
	is_signal:    bool = False               # True for clock/reset/interrupt
	protocol:     Optional[str] = None       # AXI4 / AXI4LITE / AXI3
	notes:        str = ""


IFACE_DB: Dict[str, InterfaceDef] = {}

def _reg(iface: InterfaceDef) -> InterfaceDef:
	IFACE_DB[iface.key] = iface
	return iface


# -- AXI-Stream ---------------------------------------------------------------
_reg(InterfaceDef(
	key="axis", vlnv="xilinx.com:interface:axis_rtl:1.0",
	bus_vlnv="xilinx.com:interface:axis:1.0",
	mode_support=["slave", "master"],
	signals={
		"TDATA":  ["tdata"],  "TVALID": ["tvalid"], "TREADY": ["tready"],
		"TLAST":  ["tlast"],  "TSTRB":  ["tstrb"],  "TKEEP":  ["tkeep"],
		"TID":    ["tid"],    "TDEST":  ["tdest"],  "TUSER":  ["tuser"],
	},
	required=["TVALID", "TREADY"],
))

# -- AXI4-Lite ----------------------------------------------------------------
_reg(InterfaceDef(
	key="axil", vlnv="xilinx.com:interface:aximm_rtl:1.0",
	bus_vlnv="xilinx.com:interface:aximm:1.0",
	protocol="AXI4LITE", mode_support=["slave", "master"],
	signals={
		"AWADDR": ["awaddr"], "AWPROT":  ["awprot"],  "AWVALID": ["awvalid"], "AWREADY": ["awready"],
		"WDATA":  ["wdata"],  "WSTRB":   ["wstrb"],   "WVALID":  ["wvalid"],  "WREADY":  ["wready"],
		"BRESP":  ["bresp"],  "BVALID":  ["bvalid"],  "BREADY":  ["bready"],
		"ARADDR": ["araddr"], "ARPROT":  ["arprot"],  "ARVALID": ["arvalid"], "ARREADY": ["arready"],
		"RDATA":  ["rdata"],  "RRESP":   ["rresp"],   "RVALID":  ["rvalid"],  "RREADY":  ["rready"],
	},
	required=["AWADDR", "AWVALID", "ARADDR", "ARVALID"],
))

# -- AXI4 Full MM -------------------------------------------------------------
_reg(InterfaceDef(
	key="axi4", vlnv="xilinx.com:interface:aximm_rtl:1.0",
	bus_vlnv="xilinx.com:interface:aximm:1.0",
	protocol="AXI4", mode_support=["slave", "master"],
	signals={
		"AWID": ["awid"], "AWADDR": ["awaddr"], "AWLEN": ["awlen"], "AWSIZE": ["awsize"],
		"AWBURST": ["awburst"], "AWLOCK": ["awlock"], "AWCACHE": ["awcache"],
		"AWPROT": ["awprot"], "AWQOS": ["awqos"], "AWREGION": ["awregion"],
		"AWUSER": ["awuser"], "AWVALID": ["awvalid"], "AWREADY": ["awready"],
		"WID": ["wid"], "WDATA": ["wdata"], "WSTRB": ["wstrb"], "WLAST": ["wlast"],
		"WUSER": ["wuser"], "WVALID": ["wvalid"], "WREADY": ["wready"],
		"BID": ["bid"], "BRESP": ["bresp"], "BUSER": ["buser"],
		"BVALID": ["bvalid"], "BREADY": ["bready"],
		"ARID": ["arid"], "ARADDR": ["araddr"], "ARLEN": ["arlen"], "ARSIZE": ["arsize"],
		"ARBURST": ["arburst"], "ARLOCK": ["arlock"], "ARCACHE": ["arcache"],
		"ARPROT": ["arprot"], "ARQOS": ["arqos"], "ARREGION": ["arregion"],
		"ARUSER": ["aruser"], "ARVALID": ["arvalid"], "ARREADY": ["arready"],
		"RID": ["rid"], "RDATA": ["rdata"], "RRESP": ["rresp"], "RLAST": ["rlast"],
		"RUSER": ["ruser"], "RVALID": ["rvalid"], "RREADY": ["rready"],
	},
	required=["AWADDR", "AWVALID", "WDATA", "WLAST", "ARADDR", "ARVALID", "RDATA", "RLAST"],
))

# -- AXI3 ---------------------------------------------------------------------
_reg(InterfaceDef(
	key="axi3", vlnv="xilinx.com:interface:aximm_rtl:1.0",
	bus_vlnv="xilinx.com:interface:aximm:1.0",
	protocol="AXI3", mode_support=["slave", "master"],
	signals={
		"AWID": ["awid"], "AWADDR": ["awaddr"], "AWLEN": ["awlen"], "AWSIZE": ["awsize"],
		"AWBURST": ["awburst"], "AWLOCK": ["awlock"], "AWCACHE": ["awcache"],
		"AWPROT": ["awprot"], "AWVALID": ["awvalid"], "AWREADY": ["awready"],
		"WID": ["wid"], "WDATA": ["wdata"], "WSTRB": ["wstrb"], "WLAST": ["wlast"],
		"WVALID": ["wvalid"], "WREADY": ["wready"],
		"BID": ["bid"], "BRESP": ["bresp"], "BVALID": ["bvalid"], "BREADY": ["bready"],
		"ARID": ["arid"], "ARADDR": ["araddr"], "ARLEN": ["arlen"], "ARSIZE": ["arsize"],
		"ARBURST": ["arburst"], "ARLOCK": ["arlock"], "ARCACHE": ["arcache"],
		"ARPROT": ["arprot"], "ARVALID": ["arvalid"], "ARREADY": ["arready"],
		"RID": ["rid"], "RDATA": ["rdata"], "RRESP": ["rresp"], "RLAST": ["rlast"],
		"RVALID": ["rvalid"], "RREADY": ["rready"],
	},
	required=["AWADDR", "AWVALID", "WDATA", "ARADDR", "ARVALID"],
))

# -- APB ----------------------------------------------------------------------
_reg(InterfaceDef(
	key="apb", vlnv="xilinx.com:interface:apb_rtl:1.0",
	bus_vlnv="xilinx.com:interface:apb:1.0",
	mode_support=["slave", "master"],
	signals={
		"PADDR": ["paddr"], "PSEL": ["psel"], "PENABLE": ["penable"],
		"PWRITE": ["pwrite"], "PWDATA": ["pwdata"], "PREADY": ["pready"],
		"PRDATA": ["prdata"], "PSLVERR": ["pslverr"], "PPROT": ["pprot"],
		"PSTRB": ["pstrb"],
	},
	required=["PADDR", "PENABLE", "PREADY"],
))

# -- AHB-Lite -----------------------------------------------------------------
_reg(InterfaceDef(
	key="ahblite", vlnv="xilinx.com:interface:ahblite_rtl:1.0",
	bus_vlnv="xilinx.com:interface:ahblite:1.0",
	mode_support=["slave", "master"],
	signals={
		"HADDR": ["haddr"], "HWRITE": ["hwrite"], "HTRANS": ["htrans"],
		"HSIZE": ["hsize"], "HBURST": ["hburst"], "HPROT": ["hprot"],
		"HMASTLOCK": ["hmastlock"], "HWDATA": ["hwdata"], "HRDATA": ["hrdata"],
		"HREADY": ["hready", "hreadyin"], "HREADYOUT": ["hreadyout"],
		"HRESP": ["hresp"], "HSEL": ["hsel"],
	},
	required=["HADDR", "HTRANS", "HRDATA"],
))

# -- BRAM ---------------------------------------------------------------------
_reg(InterfaceDef(
	key="bram", vlnv="xilinx.com:interface:bram_rtl:1.0",
	bus_vlnv="xilinx.com:interface:bram:1.0",
	mode_support=["slave", "master"],
	signals={
		"ADDR": ["addr", "addra", "addrb"], "CLK": ["clk", "clka", "clkb"],
		"DIN":  ["din",  "dina", "dinb"], "DOUT": ["dout", "douta", "doutb"],
		"EN":   ["en",   "ena",  "enb"],  "RST":  ["rst",  "rsta",  "rstb"],
		"WE":   ["we",   "wea",  "web"],
	},
	required=["ADDR", "DIN", "DOUT"],
))

# -- FIFO Write / Read --------------------------------------------------------
_reg(InterfaceDef(
	key="fifo_write", vlnv="xilinx.com:interface:fifo_write_rtl:1.0",
	bus_vlnv="xilinx.com:interface:fifo_write:1.0",
	mode_support=["slave", "master"],
	signals={
		"WR_DATA":  ["wr_data", "din"],   "WR_EN":  ["wr_en", "wr"],
		"FULL":     ["full"],             "ALMOST_FULL": ["almost_full", "prog_full"],
		"WR_COUNT": ["wr_count", "wr_data_count"],
		"WR_ACK":   ["wr_ack"],           "OVERFLOW": ["overflow"],
	},
	required=["WR_DATA", "WR_EN", "FULL"],
))

_reg(InterfaceDef(
	key="fifo_read", vlnv="xilinx.com:interface:fifo_read_rtl:1.0",
	bus_vlnv="xilinx.com:interface:fifo_read:1.0",
	mode_support=["slave", "master"],
	signals={
		"RD_DATA":  ["rd_data", "dout"],  "RD_EN":  ["rd_en", "rd"],
		"EMPTY":    ["empty"],            "ALMOST_EMPTY": ["almost_empty", "prog_empty"],
		"RD_COUNT": ["rd_count", "rd_data_count"],
		"VALID":    ["valid"],            "UNDERFLOW": ["underflow"],
	},
	required=["RD_DATA", "RD_EN", "EMPTY"],
))

# -- IIC (I2C) ----------------------------------------------------------------
_reg(InterfaceDef(
	key="iic", vlnv="xilinx.com:interface:iic_rtl:1.0",
	bus_vlnv="xilinx.com:interface:iic:1.0",
	mode_support=["slave", "master"],
	signals={
		"SCL_I": ["scl_i"], "SCL_O": ["scl_o"], "SCL_T": ["scl_t"],
		"SDA_I": ["sda_i"], "SDA_O": ["sda_o"], "SDA_T": ["sda_t"],
	},
	required=["SCL_I", "SDA_I", "SDA_O"],
))

# -- SPI ----------------------------------------------------------------------
_reg(InterfaceDef(
	key="spi", vlnv="xilinx.com:interface:spi_rtl:1.0",
	bus_vlnv="xilinx.com:interface:spi:1.0",
	mode_support=["slave", "master"],
	signals={
		"SCK_I":  ["sck_i",  "sclk_i"],  "SCK_O": ["sck_o",  "sclk_o"], "SCK_T": ["sck_t",  "sclk_t"],
		"MOSI_I": ["mosi_i"],             "MOSI_O": ["mosi_o"],           "MOSI_T": ["mosi_t"],
		"MISO_I": ["miso_i"],             "MISO_O": ["miso_o"],           "MISO_T": ["miso_t"],
		"SS_I":   ["ss_i"],               "SS_O":   ["ss_o"],             "SS_T":   ["ss_t"],
	},
	required=["SCK_I", "MOSI_I", "MISO_O"],
))

# -- UART ---------------------------------------------------------------------
_reg(InterfaceDef(
	key="uart", vlnv="xilinx.com:interface:uart_rtl:1.0",
	bus_vlnv="xilinx.com:interface:uart:1.0",
	mode_support=["slave", "master"],
	signals={
		"TxD": ["txd", "tx"], "RxD": ["rxd", "rx"],
		"ctsn": ["ctsn", "cts_n", "cts"], "rtsn": ["rtsn", "rts_n", "rts"],
		"dcdn": ["dcdn"], "dsrn": ["dsrn"], "rin": ["rin"], "dtrn": ["dtrn"],
	},
	required=["TxD", "RxD"],
))

# -- CAN ----------------------------------------------------------------------
_reg(InterfaceDef(
	key="can", vlnv="xilinx.com:interface:can_rtl:1.0",
	bus_vlnv="xilinx.com:interface:can:1.0",
	mode_support=["slave", "master"],
	signals={"PHY_TX": ["phy_tx", "tx"], "PHY_RX": ["phy_rx", "rx"]},
	required=["PHY_TX", "PHY_RX"],
))

# -- GPIO ---------------------------------------------------------------------
_reg(InterfaceDef(
	key="gpio", vlnv="xilinx.com:interface:gpio_rtl:1.0",
	bus_vlnv="xilinx.com:interface:gpio:1.0",
	mode_support=["slave", "master"],
	signals={
		"TRI_I": ["tri_i", "gpio_i", "gpio_in"],
		"TRI_O": ["tri_o", "gpio_o", "gpio_out"],
		"TRI_T": ["tri_t", "gpio_t"],
	},
	required=["TRI_I"],
))

# -- Differential Clock -------------------------------------------------------
_reg(InterfaceDef(
	key="diff_clock", vlnv="xilinx.com:interface:diff_clock_rtl:1.0",
	bus_vlnv="xilinx.com:interface:diff_clock:1.0",
	mode_support=["slave"],
	signals={"CLK_P": ["clk_p", "p"], "CLK_N": ["clk_n", "n"]},
	required=["CLK_P", "CLK_N"],
))

# -- Ethernet: MII / GMII / RGMII / SGMII / XGMII ---------------------------
_reg(InterfaceDef(
	key="mii", vlnv="xilinx.com:interface:mii_rtl:1.0",
	bus_vlnv="xilinx.com:interface:mii:1.0",
	mode_support=["slave", "master"],
	signals={
		"TX_CLK": ["tx_clk"], "TXD": ["txd"], "TX_EN": ["tx_en"], "TX_ER": ["tx_er"],
		"RX_CLK": ["rx_clk"], "RXD": ["rxd"], "RX_DV": ["rx_dv"], "RX_ER": ["rx_er"],
		"CRS": ["crs"], "COL": ["col"],
	},
	required=["TXD", "RXD", "TX_CLK", "RX_CLK"],
))

_reg(InterfaceDef(
	key="gmii", vlnv="xilinx.com:interface:gmii_rtl:1.0",
	bus_vlnv="xilinx.com:interface:gmii:1.0",
	mode_support=["slave", "master"],
	signals={
		"TX_CLK": ["gtx_clk", "tx_clk"], "TXD": ["txd"], "TX_EN": ["tx_en"], "TX_ER": ["tx_er"],
		"RX_CLK": ["rx_clk"], "RXD": ["rxd"], "RX_DV": ["rx_dv"], "RX_ER": ["rx_er"],
		"CRS": ["crs"], "COL": ["col"],
	},
	required=["TXD", "RXD", "TX_EN"],
))

_reg(InterfaceDef(
	key="rgmii", vlnv="xilinx.com:interface:rgmii_rtl:1.0",
	bus_vlnv="xilinx.com:interface:rgmii:1.0",
	mode_support=["slave", "master"],
	signals={
		"TD": ["td"], "TX_CTL": ["tx_ctl"], "TXC": ["txc"],
		"RD": ["rd"], "RX_CTL": ["rx_ctl"], "RXC": ["rxc"],
	},
	required=["TD", "RD", "TXC", "RXC"],
))

_reg(InterfaceDef(
	key="sgmii", vlnv="xilinx.com:interface:sgmii_rtl:1.0",
	bus_vlnv="xilinx.com:interface:sgmii:1.0",
	mode_support=["slave", "master"],
	signals={"TXP": ["txp"], "TXN": ["txn"], "RXP": ["rxp"], "RXN": ["rxn"]},
	required=["TXP", "TXN", "RXP", "RXN"],
))

_reg(InterfaceDef(
	key="xgmii", vlnv="xilinx.com:interface:xgmii_rtl:1.0",
	bus_vlnv="xilinx.com:interface:xgmii:1.0",
	mode_support=["slave", "master"],
	signals={"TXD": ["txd"], "TXC": ["txc"], "RXD": ["rxd"], "RXC": ["rxc"]},
	required=["TXD", "TXC", "RXD", "RXC"],
))

# -- Clock / Reset / Interrupt (signal-level) ---------------------------------
_reg(InterfaceDef(
	key="clk_signal", vlnv="xilinx.com:signal:clock_rtl:1.0",
	bus_vlnv="xilinx.com:signal:clock:1.0",
	mode_support=["slave"], is_signal=True,
	signals={"CLK": ["clk", "clock", "aclk"]},
	required=["CLK"],
))

_reg(InterfaceDef(
	key="rst_signal", vlnv="xilinx.com:signal:reset_rtl:1.0",
	bus_vlnv="xilinx.com:signal:reset:1.0",
	mode_support=["slave"], is_signal=True,
	signals={"RST": ["rst", "reset", "aresetn", "rst_n", "reset_n"]},
	required=["RST"],
	notes="Set POLARITY to ACTIVE_LOW when port name ends in _n / aresetn",
))

_reg(InterfaceDef(
	key="intr_signal", vlnv="xilinx.com:signal:interrupt_rtl:1.0",
	bus_vlnv="xilinx.com:signal:interrupt:1.0",
	mode_support=["master"], is_signal=True,
	signals={"INTERRUPT": ["interrupt", "irq", "intr", "int"]},
	required=["INTERRUPT"],
))


# -----------------------------------------------------------------------------
# 2.  Reverse lookup  suffix_lower -> [(logical, iface_key), …]
# -----------------------------------------------------------------------------

_SUFFIX_MAP: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
for _ikey, _idef in IFACE_DB.items():
	for _log, _suf_list in _idef.signals.items():
		for _s in _suf_list:
			_SUFFIX_MAP[_s.lower()].append((_log, _ikey))


# -----------------------------------------------------------------------------
# 3.  Port data class
# -----------------------------------------------------------------------------

@dataclass
class Port:
	name:      str
	direction: str          # 'input' | 'output' | 'inout'
	width:     str = "1"    # e.g. "[31:0]" or "1"


# -----------------------------------------------------------------------------
# 4.  pyslang-based module parser  (all APIs verified against help())
# -----------------------------------------------------------------------------

_DIR_MAP: Optional[Dict] = None


def _build_dir_map() -> Dict:
	d = pyslang.ArgumentDirection
	return {
		d.In:    "input",
		d.Out:   "output",
		d.InOut: "inout",
		d.Ref:   "inout",
	}


def _bit_width(typ) -> int:
	try:
		return int(typ.bitWidth)
	except Exception:
		return 1


def parse_module(source_path: str,
				top: Optional[str] = None,
				verbose: bool = False) -> Tuple[str, List[Port]]:
	"""
	Parse a SV/V file with pyslang and return (module_name, [Port, ...]).

	All pyslang API calls verified against help() output:
	SyntaxTree.fromFile(str)
	Compilation()
	Compilation.addSyntaxTree(tree)
	Compilation.getAllDiagnostics()
	Compilation.getRoot()
	RootSymbol.topInstances
	InstanceSymbol.isModule
	InstanceSymbol.name
	InstanceSymbol.body
	InstanceBodySymbol.portList
	Scope.__iter__
	Symbol.kind.name
	Symbol.name
	PortSymbol.direction
	PortSymbol.type
	Type.bitWidth
	ArgumentDirection.In/Out/InOut/Ref
	"""
	global _DIR_MAP
	if _DIR_MAP is None:
		_DIR_MAP = _build_dir_map()

	# -- Parse and compile ----------------------------------------------------
	tree = pyslang.SyntaxTree.fromFile(source_path)
	comp = pyslang.Compilation()
	comp.addSyntaxTree(tree)

	if verbose:
		for d in comp.getAllDiagnostics():
			print(f"[pyslang] {d}", file=sys.stderr)

	root = comp.getRoot()

	# Filter to modules only; topInstances may include interface instances
	instances = [
		i for i in root.topInstances
		if i.isModule
	]

	if not instances:
		raise ValueError(
			"pyslang found no top-level module instances.\n"
			"Check that the file is a valid SV/V source with at least one module."
		)

	# -- Select target module -------------------------------------------------
	if top:
		inst = next((i for i in instances if i.name == top), None)
		if inst is None:
			avail = [i.name for i in instances]
			raise ValueError(
				f"Module '{top}' not found. "
				f"Available modules: {avail}"
			)
	else:
		if len(instances) > 1 and verbose:
			names = [i.name for i in instances]
			print(f"[INFO] Multiple modules found: {names}. "
				f"Using '{instances[0].name}'. "
				f"Use --top to override.", file=sys.stderr)
		inst = instances[0]

	module_name: str = inst.name
	ports: List[Port] = []

	# -- Primary: portList (preserves declaration order) ----------------------
	for sym in inst.body.portList:

		if sym.kind.name not in ("Port", "MultiPort"):
			continue
		direction = _DIR_MAP.get(sym.direction, "input")
														#    ArgumentDirection enu
		bw    = _bit_width(sym.type)
		width = f"[{bw - 1}:0]" if bw > 1 else "1"
		ports.append(Port(name=sym.name, direction=direction, width=width))

	# -- Fallback: scope iteration (non-ANSI style modules) -------------------
	if not ports:
		if verbose:
			print("[INFO] portList empty, falling back to Scope.__iter__", file=sys.stderr)
		for sym in inst.body:
			if sym.kind.name not in ("Port", "MultiPort"):
				continue
			direction = _DIR_MAP.get(getattr(sym, "direction", None), "input")
			bw    = _bit_width(sym.type)
			width = f"[{bw - 1}:0]" if bw > 1 else "1"
			ports.append(Port(name=sym.name, direction=direction, width=width))

	if not ports:
		raise ValueError(
			f"Module '{module_name}' was found but has no ports. "
			"Ensure it is not an empty or parameter-only module."
		)

	return module_name, ports


# -----------------------------------------------------------------------------
# 5.  Interface classifier
# -----------------------------------------------------------------------------

@dataclass
class PortGroup:
	prefix:     str
	iface_key:  str
	mode:       str
	iface_name: str
	port_map:   Dict[str, Port] = field(default_factory=dict)
	clock_port: Optional[str]   = None
	reset_port: Optional[str]   = None
	unmatched:  List[Port]      = field(default_factory=list)
	score:      int = 0


_PREFIX_HINTS: List[Tuple[str, str]] = [
	(r"^[sm]_axis",        "axis"),
	(r"^[sm]_axil$",       "axil"),
	(r"^[sm]_axi_?lite$",  "axil"),
	(r"^[sm]_axi[04]?$",   "axi4"),
	(r"^[sm]_axi3$",       "axi3"),
	(r"^[sm]_apb$",        "apb"),
	(r"^[sm]_ahb",         "ahblite"),
	(r"^[sm]_iic$",        "iic"),
	(r"^[sm]_spi$",        "spi"),
	(r"^[sm]_uart$",       "uart"),
	(r"^[sm]_can$",        "can"),
	(r"^[sm]_gpio",        "gpio"),
	(r"^[sm]_bram",        "bram"),
	(r"^fifo_wr",          "fifo_write"),
	(r"^fifo_rd",          "fifo_read"),
	(r"^mii$",             "mii"),
	(r"^gmii$",            "gmii"),
	(r"^rgmii$",           "rgmii"),
	(r"^sgmii$",           "sgmii"),
	(r"^xgmii$",           "xgmii"),
	(r"^diff_clk",         "diff_clock"),
]

_PREFIX_PATS = [(_re.compile(p, _re.I), k) for p, k in _PREFIX_HINTS]

_CLK_SUFF = {"aclk", "clk", "clock"}
_RST_SUFF = {"aresetn", "rst_n", "rst", "reset_n", "reset", "areset_n"}


def _infer_mode(prefix: str) -> str:
	p = prefix.lower()
	if p.startswith("s_"):  return "slave"
	if p.startswith("m_"):  return "master"
	return "slave"


def _score_group(ports: List[Port], iface_key: str) -> Tuple[int, Dict[str, Port]]:
	idef    = IFACE_DB[iface_key]
	sig_lut = {s.lower(): log
			for log, suf_list in idef.signals.items()
			for s in suf_list}

	matched: Dict[str, Port] = {}
	for p in ports:
		lo = p.name.lower()
		for suf in sorted(sig_lut, key=len, reverse=True):
			if lo.endswith(suf) or lo == suf:
				log = sig_lut[suf]
				if log not in matched:
					matched[log] = p
				break

	score  = sum(2 if r in matched else -3 for r in idef.required)
	score += len(matched) - len(idef.required)
	return score, matched


def _find_prefix(port_name: str) -> str:
	lo      = port_name.lower()
	all_suf = sorted(_SUFFIX_MAP.keys(), key=len, reverse=True)
	for suf in all_suf:
		if lo.endswith(f"_{suf}"):
			return port_name[:len(port_name) - len(suf) - 1]
		if lo == suf:
			return port_name
	parts = port_name.rsplit("_", 1)
	return parts[0] if len(parts) > 1 else port_name


def classify_ports(ports: List[Port], verbose: bool = False) -> Tuple[List[PortGroup], List[Port]]:
	clk_rst_ports: List[Port] = []
	main_ports:    List[Port] = []
	for p in ports:
		lo = p.name.lower()
		if any(lo == s or lo.endswith(f"_{s}") for s in _CLK_SUFF | _RST_SUFF):
			clk_rst_ports.append(p)
		else:
			main_ports.append(p)

	# -- Group main ports by prefix -------------------------------------------
	prefix_groups: Dict[str, List[Port]] = defaultdict(list)
	for p in main_ports:
		prefix_groups[_find_prefix(p.name)].append(p)

	# -- Score each prefix group ----------------------------------------------
	groups:     List[PortGroup] = []
	unassigned: List[Port]      = []

	for prefix, grp_ports in prefix_groups.items():
		hint_key: Optional[str] = None
		for pat, key in _PREFIX_PATS:
			if pat.search(prefix):
				hint_key = key
				break

		candidates = list(dict.fromkeys(
			([hint_key] if hint_key else []) +
			(["axi4", "axil", "axis", "apb"] if hint_key else list(IFACE_DB.keys()))
		))
		candidates = [c for c in candidates if c]

		best_key, best_score, best_map = None, -999, {}
		for ikey in candidates:
			sc, mp = _score_group(grp_ports, ikey)
			if verbose:
				print(f"  [{prefix}] vs {ikey}: score={sc} matched={list(mp.keys())}")
			if sc > best_score:
				best_score, best_key, best_map = sc, ikey, mp

		if best_key is None or best_score < 0:
			unassigned.extend(grp_ports)
			continue

		# Find associated clock / reset
		clk_p = rst_p = None
		pfx_lo = prefix.lower()
		for p in clk_rst_ports:
			lo  = p.name.lower()
			suf = lo[len(pfx_lo):].lstrip("_") if lo.startswith(pfx_lo) else ""
			if suf in _CLK_SUFF:
				clk_p = p.name
			elif suf in _RST_SUFF:
				rst_p = p.name

		iface_name = prefix.upper().replace("-", "_").replace(".", "_")
		groups.append(PortGroup(
			prefix     = prefix,
			iface_key  = best_key,
			mode       = _infer_mode(prefix),
			iface_name = iface_name,
			port_map   = best_map,
			clock_port = clk_p,
			reset_port = rst_p,
			unmatched  = [p for p in grp_ports if p not in best_map.values()],
			score      = best_score,
		))

	# -- Standalone clk / rst / intr signals ---------------------------------
	claimed = {g.clock_port for g in groups} | {g.reset_port for g in groups}
	for p in clk_rst_ports:
		if p.name in claimed:
			continue
		lo = p.name.lower()
		if any(lo == s or lo.endswith(f"_{s}") for s in _CLK_SUFF):
			ikey, log = "clk_signal", "CLK"
		elif any(lo == s or lo.endswith(f"_{s}") for s in _RST_SUFF):
			ikey, log = "rst_signal", "RST"
		else:
			unassigned.append(p)
			continue
		groups.append(PortGroup(
			prefix=p.name, iface_key=ikey, mode="slave",
			iface_name=p.name.upper(), port_map={log: p}, score=10,
		))

	# Remaining unmatched from main_ports
	assigned = {p.name for g in groups for p in g.port_map.values()}
	for p in main_ports:
		if p.name not in assigned:
			unassigned.append(p)

	return groups, unassigned


# -----------------------------------------------------------------------------
# 6.  TCL generator
# -----------------------------------------------------------------------------

_TCL_HEADER = """\
# =============================================================================
#  Auto-generated by sv_to_vivado_tcl.py  (pyslang edition)
#  Module      : {module_name}
#  Generated   : {date}
# =============================================================================
#
#  Vivado compatibility
#    :1.0 VLNV (default) : Vivado 2014.1 -> 2024.x
#    :2.0 VLNV (--vlnv-v2): Vivado 2024.2+ only
#
#  Usage: source this file inside an IP packager Tcl hook, e.g.:
#    proc ipx_infer_bus_interfaces {{}} {{
#        source [file join [file dirname [info script]] {tcl_name}]
#    }}
# =============================================================================

set core [ipx::current_core]

"""

_TCL_FOOTER = """
# =============================================================================
#  Finalize
# =============================================================================
ipx::check_integrity $core
ipx::save_core $core
update_compile_order -fileset sources_1
puts "INFO: Interface registration complete."
"""

_TCL_IFACE_HDR = """\
# -----------------------------------------------------------------------------
# Interface : {iface_name}  ({iface_key})  mode={mode}
# -----------------------------------------------------------------------------
set iface [ipx::add_bus_interface {iface_name} $core]
set_property abstraction_type_vlnv {vlnv}      $iface
set_property bus_type_vlnv         {bus_vlnv}  $iface
"""

_TCL_MODE     = "set_property interface_mode {mode}  $iface\n"
_TCL_PROTO    = ("set pp [ipx::add_bus_parameter PROTOCOL $iface]\n"
				"set_property value {protocol} $pp\n")
_TCL_POLARITY = ("set pol [ipx::add_bus_parameter POLARITY $iface]\n"
				"set_property value {polarity} $pol\n")
_TCL_PORT_MAP = ("set pm [ipx::add_port_map {logical} $iface]\n"
				"set_property physical_name {physical} $pm\n")
_TCL_CLK_ASSOC = (
	"# Associate clock  {clk_iface} -> {iface_name}\n"
	"set _ci [ipx::get_bus_interfaces {clk_iface} -of_objects $core]\n"
	"if {{$_ci ne \"\"}} {{\n"
	"    set _cp [ipx::add_bus_parameter ASSOCIATED_BUSIF $_ci]\n"
	"    set_property value {iface_name} $_cp\n"
	"}}\n"
)
_TCL_RST_ASSOC = (
	"# Associate reset  {rst_iface} -> {iface_name}\n"
	"set _ri [ipx::get_bus_interfaces {rst_iface} -of_objects $core]\n"
	"if {{$_ri ne \"\"}} {{\n"
	"    set _rp [ipx::add_bus_parameter ASSOCIATED_BUSIF $_ri]\n"
	"    set_property value {iface_name} $_rp\n"
	"}}\n"
)
_TCL_UNMATCHED = (
	"# WARNING: '{name}' ({direction} {width}) not assigned to any interface.\n"
	"# ipx::add_port {name} $core   ;# uncomment to register as plain port\n"
)


def generate_tcl(module_name: str, groups: List[PortGroup], unassigned: List[Port], vlnv_v2: bool = False) -> str:
	def _vlnv(s: str) -> str:
		return s.replace(":1.0", ":2.0") if vlnv_v2 else s

	lines: List[str] = []
	tcl_name = f"{module_name}_interfaces.tcl"

	lines.append(_TCL_HEADER.format(
		module_name=module_name,
		date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
		tcl_name=tcl_name,
	))

	for g in groups:
		idef = IFACE_DB[g.iface_key]

		lines.append(_TCL_IFACE_HDR.format(
			iface_name=g.iface_name, iface_key=g.iface_key, mode=g.mode,
			vlnv=_vlnv(idef.vlnv), bus_vlnv=_vlnv(idef.bus_vlnv),
		))

		if not idef.is_signal:
			lines.append(_TCL_MODE.format(mode=g.mode))

		if idef.protocol:
			lines.append(_TCL_PROTO.format(protocol=idef.protocol))

		if g.iface_key == "rst_signal":
			for p in g.port_map.values():
				lo = p.name.lower()
				active_low = lo.endswith("_n") or "resetn" in lo or "rstn" in lo
				lines.append(_TCL_POLARITY.format(
					polarity="ACTIVE_LOW" if active_low else "ACTIVE_HIGH"
				))

		for logical, port in g.port_map.items():
			lines.append(_TCL_PORT_MAP.format(logical=logical, physical=port.name))

		if g.clock_port:
			lines.append(_TCL_CLK_ASSOC.format(
				clk_iface=g.clock_port.upper(), iface_name=g.iface_name,
			))
		if g.reset_port:
			lines.append(_TCL_RST_ASSOC.format(
				rst_iface=g.reset_port.upper(), iface_name=g.iface_name,
			))

		lines.append("")  # blank separator

	if unassigned:
		lines.append("# " + "=" * 77)
		lines.append("# UNMATCHED PORTS - manual review required")
		lines.append("# " + "=" * 77)
		for p in unassigned:
			lines.append(_TCL_UNMATCHED.format(
				name=p.name, direction=p.direction, width=p.width,
			))

	lines.append(_TCL_FOOTER)
	return "\n".join(lines)


# -----------------------------------------------------------------------------
# 7.  CLI entry-point
# -----------------------------------------------------------------------------

def main() -> None:
	ap = argparse.ArgumentParser(
		description="Parse SV/V module with pyslang -> Vivado IP-XACT interface TCL",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__,
	)
	ap.add_argument("source",         help="SystemVerilog / Verilog source file")
	ap.add_argument("-o", "--output", help="Output TCL (default: <module>_interfaces.tcl)")
	ap.add_argument("--top",          help="Top module name (multi-module files)")
	ap.add_argument("--dry-run",      action="store_true",
					help="Print TCL to stdout, do not write file")
	ap.add_argument("--strict",       action="store_true",
					help="Exit with error if any port cannot be assigned")
	ap.add_argument("--verbose",      action="store_true",
					help="Print pyslang diagnostics and scoring info")
	ap.add_argument("--vlnv-v2",      action="store_true",
					help="Emit :2.0 VLNV suffixes (Vivado 2024.2+ only)")
	args = ap.parse_args()

	module_name, ports = parse_module(
		source_path=args.source,
		top=args.top,
		verbose=args.verbose,
	)
	print(f"[INFO] Module : {module_name}  ({len(ports)} ports)")

	groups, unassigned = classify_ports(ports, verbose=args.verbose)

	print(f"[INFO] Interfaces detected: {len(groups)}")
	for g in groups:
		print(f"       {g.iface_name:<30s}  type={g.iface_key:<12s}  "
			f"mode={g.mode:<7s}  signals={len(g.port_map)}  score={g.score}")

	if unassigned:
		print(f"[WARN] {len(unassigned)} port(s) unassigned:")
		for p in unassigned:
			print(f"       {p.name}  ({p.direction} {p.width})")
		if args.strict:
			print("[ERROR] --strict: aborting due to unassigned ports.")
			sys.exit(1)

	tcl = generate_tcl(module_name, groups, unassigned, vlnv_v2=args.vlnv_v2)

	if args.dry_run:
		print("\n" + "=" * 80 + "\n" + tcl)
	else:
		out_path = args.output or f"{module_name}_interfaces.tcl"
		with open(out_path, "w") as fh:
			fh.write(tcl)
		print(f"[INFO] TCL written -> {out_path}")


if __name__ == "__main__":
	main()