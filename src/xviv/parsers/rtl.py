from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
	import pyslang
except ImportError as exc:
	raise ImportError("pyslang is required for RTL parsing - install it with: pip install pyslang") from exc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PortInfo / RTLPortExtractor  (used by validate command)
# ---------------------------------------------------------------------------


@dataclass
class PortInfo:
	name: str
	direction: str  # "In" | "Out" | "InOut"
	type_str: str  # e.g. "logic", "logic[7:0]"
	msb: int = 0
	lsb: int = 0
	width: int = 1

	def expand_bits(self) -> List[str]:

		if self.width == 1:
			return [self.name]
		lo = min(self.lsb, self.msb)
		hi = max(self.lsb, self.msb)
		return [f"{self.name}[{i}]" for i in range(lo, hi + 1)]


class RTLPortExtractor:
	def __init__(self, rtl_files: List[str], top_module: Optional[str] = None) -> None:
		self.rtl_files = rtl_files
		self.top_module = top_module
		self.errors: List[str] = []
		self.module_name: Optional[str] = None
		self.ports: List[PortInfo] = []
		self._extract()

	def _extract(self) -> None:
		if not self.rtl_files:
			self.errors.append("No RTL source files specified.")
			return

		comp = pyslang.Compilation()
		for path in self.rtl_files:
			try:
				comp.addSyntaxTree(pyslang.SyntaxTree.fromFile(path))
			except Exception as exc:
				self.errors.append(f"Cannot open RTL file '{path}': {exc}")
				return

		top_insts = list(comp.getRoot().topInstances)
		if not top_insts:
			self.errors.append("No top-level module instances found.")
			return

		inst = None
		if self.top_module:
			for ti in top_insts:
				if ti.name == self.top_module:
					inst = ti
					break
			if inst is None:
				avail = ", ".join(ti.name for ti in top_insts)
				self.errors.append(f"Module '{self.top_module}' not found. Available: {avail}")
				return
		else:
			inst = top_insts[0]

		self.module_name = inst.name
		for p in inst.body.portList:
			if str(p.kind).endswith("InterfacePort"):
				continue  # interface ports have no physical bit representation
			type_str = str(p.type)
			msb, lsb, width = _parse_dims(type_str)
			self.ports.append(
				PortInfo(
					name=p.name,
					direction=str(p.direction).split(".")[-1],
					type_str=type_str,
					msb=msb,
					lsb=lsb,
					width=width,
				)
			)


# ---------------------------------------------------------------------------
# ModuleInfo and friends  (used by wrapper generator)
# ---------------------------------------------------------------------------


@dataclass
class PortDecl:
	name: str
	direction: str  # "input" | "output" | "inout" | "ref" | ""
	type_str: str  # e.g. "logic[7:0]"; "" for interface ports
	is_interface: bool = False
	interface_name: Optional[str] = None  # e.g. "AXI4"
	modport_name: Optional[str] = None  # e.g. "Master"


@dataclass
class ParamDecl:
	name: str
	type_str: str  # e.g. "int", "logic"
	default_str: str  # elaborated default, e.g. "8"
	keyword: str = "parameter"


@dataclass
class IfaceSignal:
	name: str
	direction: str  # "input" | "output" | "inout" - from modport's perspective
	type_str: str  # source-form type tokens, e.g. "logic[WIDTH-1:0]"


@dataclass
class ModuleInfo:
	name: str
	params: Dict[str, ParamDecl]
	ports: Dict[str, PortDecl]
	iface_signals: Dict[str, Dict[str, IfaceSignal]]


# ---------------------------------------------------------------------------
# Internal Semantic-API helpers
# ---------------------------------------------------------------------------


def _parse_dims(type_str: str) -> Tuple[int, int, int]:

	m = re.search(r"\[(\d+):(\d+)\]", type_str)
	if m:
		msb, lsb = int(m.group(1)), int(m.group(2))
		return msb, lsb, abs(msb - lsb) + 1
	return 0, 0, 1


_DIR_MAP: Dict[str, str] = {
	"In": "input",
	"Out": "output",
	"InOut": "inout",
	"Ref": "ref",
}


def _dir_kw(direction) -> str:

	return _DIR_MAP.get(str(direction).split(".")[-1], "input")


def _modport_dirs(modport_sym) -> Dict[str, str]:

	result: Dict[str, str] = {}
	ports_list = modport_sym.syntax.ports  # AnsiPortListSyntax

	for child in ports_list:
		if isinstance(child, pyslang.Token):
			continue
		# child is the SeparatedList
		for item in child:
			if isinstance(item, pyslang.Token):
				continue
			if isinstance(item, pyslang.ModportSimplePortListSyntax):
				direction = str(getattr(item, "direction", "")).strip().lower()
				for port in getattr(item, "ports", []):
					if isinstance(port, pyslang.Token):
						continue
					name_tok = getattr(port, "name", None)
					if name_tok and hasattr(name_tok, "valueText"):
						result[name_tok.valueText] = direction
			elif isinstance(item, pyslang.ModportSubroutinePortListSyntax):
				# task/function imports: skip for wrapper purposes
				pass

	return result


def _iface_sig_types(idef_syntax) -> Dict[str, str]:

	def _tokens_text(node) -> str:
		parts: List[str] = []
		for c in node:
			if isinstance(c, pyslang.Token) and c.valueText:
				parts.append(c.valueText)
			elif isinstance(c, pyslang.SyntaxNode):
				inner = _tokens_text(c)
				if inner:
					parts.append(inner)
		return "".join(parts)

	result: Dict[str, str] = {}
	for m in idef_syntax.members:
		if not isinstance(m, pyslang.DataDeclarationSyntax):
			continue
		dtype_node = getattr(m, "type", None)
		type_str = _tokens_text(dtype_node) if dtype_node is not None else ""
		for decl in getattr(m, "declarators", []):
			if isinstance(decl, pyslang.Token):
				continue
			name_tok = getattr(decl, "name", None)
			if name_tok and hasattr(name_tok, "valueText"):
				dims = "".join(str(d).strip() for d in getattr(decl, "dimensions", []))
				result[name_tok.valueText] = type_str + dims

	return result


def _extract_params(body) -> Dict[str, ParamDecl]:

	params: Dict[str, ParamDecl] = {}
	for p in body.parameters:
		if p.isLocalParam:
			continue
		try:
			default_str = str(p.value)
		except Exception:
			default_str = ""
		params[p.name] = ParamDecl(
			name=p.name,
			type_str=str(p.type) if hasattr(p, "type") else "",
			default_str=default_str,
			keyword="parameter",
		)
	return params


def _extract_iface_port(
	p,
) -> Tuple[PortDecl, Optional["ModuleInfo"], Dict[str, IfaceSignal]]:

	iface_inst_sym, modport_sym = p.connection
	iface_def = p.interfaceDef  # DefinitionSymbol
	modport_name: str = p.modport  # plain string

	port_decl = PortDecl(
		name=p.name,
		direction="",
		type_str="",
		is_interface=True,
		interface_name=iface_def.name,
		modport_name=modport_name,
	)

	# Parameters of the interface definition (elaborated with defaults)
	iface_module_info = ModuleInfo(
		name=iface_def.name,
		params=_extract_params(iface_inst_sym.body),
		ports={},
		iface_signals={},
	)

	# Signal directions come from the modport (syntax walk preserves exact names)
	mp_dirs = _modport_dirs(modport_sym)
	# Signal types come from the interface body syntax (preserves param names)
	sig_types = _iface_sig_types(iface_def.syntax)

	signals: Dict[str, IfaceSignal] = {}
	for sig_name, direction in mp_dirs.items():
		signals[sig_name] = IfaceSignal(
			name=sig_name,
			direction=direction,
			type_str=sig_types.get(sig_name, "logic"),
		)

	return port_decl, iface_module_info, signals


def _resolve_module(inst) -> Tuple["ModuleInfo", Dict[str, "ModuleInfo"]]:

	params = _extract_params(inst.body)
	ports: Dict[str, PortDecl] = {}
	iface_signals: Dict[str, Dict[str, IfaceSignal]] = {}
	iface_defs: Dict[str, ModuleInfo] = {}

	for p in inst.body.portList:
		if str(p.kind).endswith("InterfacePort"):
			port_decl, iface_info, signals = _extract_iface_port(p)
			ports[p.name] = port_decl
			iface_signals[p.name] = signals
			if iface_info and iface_info.name not in iface_defs:
				iface_defs[iface_info.name] = iface_info
		else:
			ports[p.name] = PortDecl(
				name=p.name,
				direction=_dir_kw(p.direction),
				type_str=str(p.type),
			)

	module_info = ModuleInfo(
		name=inst.name,
		params=params,
		ports=ports,
		iface_signals=iface_signals,
	)
	return module_info, iface_defs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_modules(files: List[str]) -> Dict[str, ModuleInfo]:

	if not files:
		raise ValueError("resolve_modules: no source files provided")

	comp = pyslang.Compilation()
	for path in files:
		comp.addSyntaxTree(pyslang.SyntaxTree.fromFile(path))

	result: Dict[str, ModuleInfo] = {}
	for inst in comp.getRoot().topInstances:
		module_info, iface_defs = _resolve_module(inst)
		result[inst.name] = module_info
		# Interface definitions are added only the first time they appear
		for name, info in iface_defs.items():
			result.setdefault(name, info)

	return result
