#!/usr/bin/env python3
"""
wrapper.py - SystemVerilog wrapper generator for xviv.

Parses a top-level SV module (and any interface ports it uses) via pyslang,
then emits a flat wrapper module that exposes every signal as a plain I/O port
instead of an interface port.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile

import pyslang
from xviv.utils.log import _setup_logging


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
DatatypeInfo  = dict
PortInfo      = dict
ParamInfo     = dict
MemberInfo    = dict
ModuleData    = dict
TreeData      = dict


# ---------------------------------------------------------------------------
# Token / tree helpers
# ---------------------------------------------------------------------------

def _get_all_tokens(node: pyslang.SyntaxNode):
	"""Yield every Token reachable under *node* (depth-first)."""
	for child in node:
		if isinstance(child, pyslang.Token):
			yield child
		elif isinstance(child, pyslang.SyntaxNode):
			yield from _get_all_tokens(child)


def filter_comments_from_tree(tree: pyslang.SyntaxTree) -> pyslang.SyntaxTree:
	"""Return a new SyntaxTree with all line- and block-comments stripped.

	Notes
	-----
	``SyntaxTree.fromText`` returns a ``ModuleDeclarationSyntax`` root when the
	text contains exactly one module, but a ``CompilationUnitSyntax`` root when
	it contains more than one top-level item.  To guarantee a
	``CompilationUnitSyntax`` root (required by :func:`resolve_tree`) we write
	the reconstructed text to a temporary file and re-parse with
	``SyntaxTree.fromFiles``, which *always* wraps in a CompilationUnit.
	"""
	_COMMENT_KINDS = (pyslang.TriviaKind.LineComment, pyslang.TriviaKind.BlockComment)

	clean_parts: list[str] = []
	for token in _get_all_tokens(tree.root):
		for trivia in token.trivia:
			if trivia.kind not in _COMMENT_KINDS:
				clean_parts.append(trivia.getRawText())
		clean_parts.append(token.valueText)

	clean_text = "".join(clean_parts)

	# Write to a temp file so fromFiles guarantees CompilationUnitSyntax root.
	with tempfile.NamedTemporaryFile(
		mode="w", suffix=".sv", delete=False, encoding="utf-8"
	) as tmp:
		tmp.write(clean_text)
		tmp_path = tmp.name

	try:
		return pyslang.SyntaxTree.fromFiles([tmp_path])
	finally:
		os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Datatype / declarator extraction
# ---------------------------------------------------------------------------

def get_datatype_info(node) -> DatatypeInfo:
	"""Return a normalised dict describing a datatype syntax node.

	Returns an empty dict for ``None`` or string inputs (defensive; callers
	should not pass these).
	"""
	if node is None or isinstance(node, str):
		return {}

	match type(node):
		case pyslang.IntegerTypeSyntax:
			return {
				"kind":       "IntegerTypeSyntax",
				"dimensions": "".join(str(d).strip() for d in getattr(node, "dimensions", "")),
				"keyword":    str(getattr(node, "keyword",  "")).strip(),
				"signing":    str(getattr(node, "signing",  "")).strip(),
			}

		case pyslang.NamedTypeSyntax:
			return {
				"kind": "NamedTypeSyntax",
				"name": str(getattr(node, "name", "")).strip(),
			}

		case pyslang.ImplicitTypeSyntax:
			return {
				"kind":       "ImplicitTypeSyntax",
				"dimensions": "".join(str(d).strip() for d in getattr(node, "dimensions", "")),
				"placeholder": str(getattr(node, "placeholder", "")).strip(),
				"signing":    str(getattr(node, "signing",  "")).strip(),
			}

		case pyslang.KeywordTypeSyntax:
			return {
				"kind":    "KeywordTypeSyntax",
				"keyword": str(getattr(node, "keyword", "")).strip(),
			}

		case _:
			raise TypeError(f"Unhandled datatype node: {type(node)!r}")


def get_declarator(declarator: pyslang.DeclaratorSyntax) -> tuple[pyslang.Token | None, dict]:
	"""Return ``(name_token, decl_dict)`` for a DeclaratorSyntax node.

	Returns ``(None, {})`` when *declarator* is falsy, so callers can safely
	unpack without a ``ValueError``.
	"""
	if not declarator or isinstance(declarator, str):
		return None, {}

	initializer = getattr(declarator, "initializer", None)
	name        = getattr(declarator, "name",        "")
	dimensions  = "".join(str(d).strip() for d in getattr(declarator, "dimensions", []))
	expr        = str(getattr(initializer, "expr",  "")).strip() if initializer else ""
	itype       = str(getattr(initializer, "type",  "")).strip() if initializer else ""

	return name, {
		"dimensions": dimensions,
		"expr":       expr + itype,
	}


# ---------------------------------------------------------------------------
# Port-header extraction
# ---------------------------------------------------------------------------

def get_port_header_info(node) -> PortInfo:
	"""Return a normalised dict describing a port-header syntax node."""
	if node is None or isinstance(node, str):
		return {}

	match type(node):
		case pyslang.InterfacePortHeaderSyntax:
			name_or_kw = getattr(node, "nameOrKeyword", "")
			modport    = getattr(node, "modport",       "")
			member     = getattr(modport, "member",     "")
			return {
				"kind":      "InterfacePortHeaderSyntax",
				"interface": str(name_or_kw).strip(),
				"modport":   str(member).strip(),
			}

		case pyslang.NetPortHeaderSyntax:
			return {
				"kind":      "NetPortHeaderSyntax",
				"type":      get_datatype_info(getattr(node, "dataType",  None)),
				"direction": str(getattr(node, "direction", "")).strip(),
				"netType":   str(getattr(node, "netType",   "")).strip(),
			}

		case pyslang.VariablePortHeaderSyntax:
			return {
				"kind":         "VariablePortHeaderSyntax",
				"constKeyword": str(getattr(node, "constKeyword", "")).strip(),
				"type":         get_datatype_info(getattr(node, "dataType", None)),
				"direction":    str(getattr(node, "direction",    "")).strip(),
				"varKeyword":   str(getattr(node, "varKeyword",   "")).strip(),
			}

		case _:
			raise TypeError(f"Unhandled port-header node: {type(node)!r}")


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

def resolve_parameters(param_list) -> dict[str, ParamInfo]:
	"""Parse a ParameterPortListSyntax (or None) into a name → info dict."""
	params: dict[str, ParamInfo] = {}

	for decl in getattr(param_list, "declarations", []):
		if isinstance(decl, pyslang.Token):
			continue

		decl_type   = getattr(decl, "type",    "")
		keyword     = getattr(decl, "keyword", "")

		for declarator in getattr(decl, "declarators", []):
			if isinstance(declarator, pyslang.Token):
				continue

			match type(declarator):
				case pyslang.DeclaratorSyntax:
					name_tok, decl_dict = get_declarator(declarator)
					if name_tok is None:
						continue
					params[name_tok.valueText] = {
						"kind":    "DeclaratorSyntax",
						"keyword": str(keyword).strip(),
						"decl":    decl_dict,
						"type":    get_datatype_info(decl_type),
					}

				case pyslang.TypeAssignmentSyntax:
					name_tok   = getattr(declarator, "name",       "")
					assignment = getattr(declarator, "assignment", None)
					assigned_t = getattr(assignment, "type",       None) if assignment else None
					params[name_tok.valueText] = {
						"kind": "TypeAssignmentSyntax",
						"type": get_datatype_info(assigned_t),
					}

				case _:
					raise TypeError(f"Unhandled declarator type in parameters: {type(declarator)!r}")

	return params


# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------

def resolve_ports(
	port_list: pyslang.AnsiPortListSyntax
			  | pyslang.NonAnsiPortListSyntax
			  | pyslang.WildcardPortListSyntax
			  | None,
) -> dict[str, PortInfo]:
	"""Parse any port-list syntax node into a name → info dict."""
	ports: dict[str, PortInfo] = {}

	if port_list is None:
		return ports

	# WildcardPortListSyntax (.*)  has no 'ports' iterable; return empty.
	if isinstance(port_list, pyslang.WildcardPortListSyntax):
		logger.debug("Wildcard port list encountered - skipping")
		return ports

	for decl in getattr(port_list, "ports", []):
		if isinstance(decl, pyslang.Token):
			continue

		match type(decl):
			# ------------------------------------------------------------------
			# ANSI implicit port  (input logic clk)
			# ------------------------------------------------------------------
			case pyslang.ImplicitAnsiPortSyntax:
				declarator  = getattr(decl, "declarator", None)
				header      = getattr(decl, "header",     None)
				attributes  = getattr(decl, "attributes", "")

				name_tok    = getattr(declarator, "name",        "")
				initializer = getattr(declarator, "initializer", None)
				dimensions  = "".join(str(d).strip() for d in getattr(declarator, "dimensions", []))
				expr        = str(getattr(initializer, "expr",   "")).strip() if initializer else ""

				header_val = get_port_header_info(header)

				# Inherit direction from previous port when not explicit
				if (
					header_val
					and header_val.get("kind") != "InterfacePortHeaderSyntax"
					and not header_val.get("direction")
					and ports
				):
					header_val = next(reversed(ports.values()))["header"]

				ports[name_tok.valueText] = {
					"kind":       "ImplicitAnsiPortSyntax",
					"attributes": str(attributes).strip(),
					"dimensions": dimensions,
					"expr":       expr,
					"header":     header_val,
				}

			# ------------------------------------------------------------------
			# Non-ANSI implicit port  (clk)
			# ------------------------------------------------------------------
			case pyslang.ImplicitNonAnsiPortSyntax:
				expr      = getattr(decl, "expr",   "")
				name_tok  = getattr(expr,  "name",   "")
				select    = getattr(expr,  "select", None)

				ports[name_tok.valueText] = {
					"kind":   "ImplicitNonAnsiPortSyntax",
					"select": str(select).strip() if select is not None else None,
				}

			# ------------------------------------------------------------------
			# Non-ANSI explicit port  (.clk(clk_sig))
			# ------------------------------------------------------------------
			case pyslang.ExplicitNonAnsiPortSyntax:
				name_tok  = getattr(decl, "name", "")
				expr      = getattr(decl, "expr", "")
				expr_name = getattr(expr,  "name",   "")
				expr_sel  = getattr(expr,  "select", None)

				ports[name_tok.valueText] = {
					"kind":   "ExplicitNonAnsiPortSyntax",
					"select": str(expr_sel).strip() if expr_sel is not None else None,
					"signal": str(expr_name).strip(),
				}

			case pyslang.EmptyNonAnsiPortSyntax:
				pass  # empty port slot - legal in SV, nothing to record

			# ------------------------------------------------------------------
			# Modport port list  (input clk, output data)
			# ------------------------------------------------------------------
			case pyslang.ModportSimplePortListSyntax | pyslang.ModportSubroutinePortListSyntax:
				direction_tok  = getattr(decl, "direction",    None)
				import_tok     = getattr(decl, "importExport", None)
				direction_str  = str(direction_tok if direction_tok is not None else import_tok).strip()

				for port in getattr(decl, "ports", []):
					if isinstance(port, pyslang.Token):
						continue

					match type(port):
						case pyslang.ModportExplicitPortSyntax:
							name_tok = getattr(port, "name", "")
							expr_tok = getattr(port, "expr", "")
							ports[name_tok.valueText] = {
								"kind":      "ModportExplicitPortSyntax",
								"expr":      str(expr_tok).strip(),
								"direction": direction_str,
							}

						case pyslang.ModportNamedPortSyntax:
							name_tok = getattr(port, "name", "")
							ports[name_tok.valueText] = {
								"kind":      "ModportNamedPortSyntax",
								"direction": direction_str,
							}

						case pyslang.ModportSubroutinePortSyntax:
							# FIX: was using undefined `_name` from outer scope.
							proto    = getattr(port, "prototype", "")
							name_tok = getattr(proto, "name", "") if proto else getattr(port, "name", "")
							ports[name_tok.valueText] = {
								"kind":      "ModportSubroutinePortSyntax",
								"direction": str(proto).strip(),
							}

						case _:
							raise TypeError(
								f"Unhandled modport port type: {type(port)!r}"
							)

			case _:
				raise TypeError(f"Unhandled port declaration type: {type(decl)!r}")

	return ports


# ---------------------------------------------------------------------------
# Member resolution
# ---------------------------------------------------------------------------

def resolve_members(members) -> MemberInfo:
	"""Parse module-body members into categorised dicts."""
	port_dict: dict = {}
	decl_dict: dict = {}
	inst_dict: dict = {}
	modp_dict: dict = {}

	for member in members:
		match type(member):
			# ------------------------------------------------------------------
			case pyslang.ModportDeclarationSyntax:
				for item in getattr(member, "items", []):
					name_tok = getattr(item, "name",  "")
					ports_sn = getattr(item, "ports", None)
					modp_dict[name_tok.valueText] = {
						"ports": resolve_ports(ports_sn),
					}

			# ------------------------------------------------------------------
			case pyslang.DataDeclarationSyntax | pyslang.NetDeclarationSyntax:
				modifiers     = " ".join(str(m).strip() for m in getattr(member, "modifiers",     []))
				member_type   = getattr(member, "type",          None)
				attributes    = getattr(member, "attributes",    "")
				delay         = getattr(member, "delay",         "")
				expansion_hint= getattr(member, "expansionHint", "")
				net_type      = getattr(member, "netType",       "")
				strength      = getattr(member, "strength",      "")

				for declarator in getattr(member, "declarators", []):
					if isinstance(declarator, pyslang.Token):
						continue

					match type(declarator):
						case pyslang.DeclaratorSyntax:
							name_tok, decl_info = get_declarator(declarator)
							if name_tok is None:
								continue
							decl_dict[name_tok.valueText] = {
								"kind":          str(member.kind),
								"attributes":    str(attributes).strip(),
								"modifiers":     modifiers,
								"netType":       str(net_type).strip(),
								"expansionHint": str(expansion_hint).strip(),
								"strength":      str(strength).strip(),
								"delay":         str(delay).strip(),
								"decl":          decl_info,
								"type":          get_datatype_info(member_type),
							}

						case _:
							raise TypeError(
								f"Unhandled declarator in data/net decl: {type(declarator)!r}"
							)

			# ------------------------------------------------------------------
			case pyslang.PortDeclarationSyntax:
				header     = getattr(member, "header",     None)
				attributes = getattr(member, "attributes", "")

				for declarator in getattr(member, "declarators", []):
					if isinstance(declarator, pyslang.Token):
						continue

					match type(declarator):
						case pyslang.DeclaratorSyntax:
							name_tok, decl_info = get_declarator(declarator)
							if name_tok is None:
								continue
							port_dict[name_tok.valueText] = {
								"kind":       "DeclaratorSyntax",
								"attributes": str(attributes).strip(),
								"decl":       decl_info,
								"header":     get_port_header_info(header),
							}

						case _:
							raise TypeError(
								f"Unhandled declarator in port decl: {type(declarator)!r}"
							)

			# ------------------------------------------------------------------
			case pyslang.HierarchyInstantiationSyntax | pyslang.PrimitiveInstantiationSyntax:
				member_type = getattr(member, "type",   "")
				delay       = getattr(member, "delay",  "")
				strength    = getattr(member, "strength", "")

				for inst in getattr(member, "instances", []):
					decl = getattr(inst, "decl", None)
					if decl is None:
						continue
					dims     = getattr(decl, "dimensions", "")
					name_tok = getattr(decl, "name",       "")
					inst_dict[name_tok.valueText] = {
						"kind":       str(member.kind),
						"type":       str(member_type).strip(),
						"dimensions": str(dims).strip(),
						"delay":      str(delay).strip(),
						"strength":   str(strength).strip(),
					}

			# ------------------------------------------------------------------
			case _:
				logger.debug("Skipping unhandled member type: %s", type(member).__name__)

	return {
		"declarations":  decl_dict,
		"modports":      modp_dict,
		"instantiations": inst_dict,
		"ports":         port_dict,
	}


# ---------------------------------------------------------------------------
# Module / header resolution
# ---------------------------------------------------------------------------

def resolve_header(header: pyslang.ModuleHeaderSyntax) -> tuple:
	"""Return ``(name_token, header_dict)``."""
	imports   = getattr(header, "imports",       "")
	lifetime  = getattr(header, "lifetime",      "")
	keyword   = getattr(header, "moduleKeyword", "")
	name      = getattr(header, "name",          "")
	parameters= getattr(header, "parameters",    None)
	ports     = getattr(header, "ports",         None)

	return name, {
		"keyword":    str(keyword).strip(),
		"lifetime":   str(lifetime).strip(),
		"imports":    str(imports).strip(),
		"parameters": resolve_parameters(parameters),
		"ports":      resolve_ports(ports),
	}


def resolve_module(node: pyslang.ModuleDeclarationSyntax) -> tuple:
	"""Return ``(name_token, module_dict)``."""
	block_name = getattr(node, "blockName",  None)
	header     = getattr(node, "header",     None)
	members    = getattr(node, "members",    [])
	attributes = getattr(node, "attributes", "")

	name_tok, header_dict = resolve_header(header)
	member_dict = resolve_members(members)

	return name_tok, {
		"attributes": str(attributes).strip(),
		"block_name": str(block_name).strip() if block_name is not None else None,
		"headers":    header_dict,
		"members":    member_dict,
	}


def resolve_tree(node: pyslang.CompilationUnitSyntax | pyslang.ModuleDeclarationSyntax) -> TreeData:
	"""Walk a syntax tree root and return all module definitions as a dict."""
	tree_data: TreeData = {}

	# Handle the case where fromText returns a bare ModuleDeclarationSyntax.
	if isinstance(node, pyslang.ModuleDeclarationSyntax):
		name_tok, mdata = resolve_module(node)
		tree_data[name_tok.valueText] = mdata
		return tree_data

	for member in getattr(node, "members", []):
		if isinstance(member, pyslang.ModuleDeclarationSyntax):
			name_tok, mdata = resolve_module(member)
			tree_data[name_tok.valueText] = mdata
		else:
			logger.debug(
				"resolve_tree: skipping top-level member of type %s (kind=%s)",
				type(member).__name__,
				getattr(member, "kind", "?"),
			)

	return tree_data


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def resolve_files(fileset: list[str]) -> tuple[TreeData, list[str]]:
	"""Parse *fileset*, strip comments, and return ``(tree_data, resolved_fileset)``."""
	tree = pyslang.SyntaxTree.fromFiles(fileset)

	resolved: list[str] = []
	for member in getattr(tree.root, "members", []):
		path = os.path.abspath(
			tree.sourceManager.getFileName(member.sourceRange.start)
		)
		if path not in resolved:
			resolved.append(path)

	tree = filter_comments_from_tree(tree)
	return resolve_tree(tree.root), resolved


# ---------------------------------------------------------------------------
# Code-generation helpers
# ---------------------------------------------------------------------------

def construct_datatype(info: DatatypeInfo) -> tuple[tuple[str, str, str], tuple[int, int, int]]:
	"""Return ``((keyword, signing, dimensions), (len, len, len))``."""
	match info.get("kind"):
		case "IntegerTypeSyntax":
			kw  = info["keyword"]
			sgn = info["signing"]
			dim = info["dimensions"]
			return (kw, sgn, dim), (len(kw), len(sgn), len(dim))

		case "NamedTypeSyntax":
			nm  = info["name"]
			return (nm, "", ""), (len(nm), 0, 0)

		case "ImplicitTypeSyntax":
			sgn = info["signing"]
			dim = info["dimensions"]
			return ("", sgn, dim), (0, len(sgn), len(dim))

		case "KeywordTypeSyntax":
			kw = info["keyword"]
			return (kw, "", ""), (len(kw), 0, 0)

		case _:
			raise ValueError(f"Unknown datatype kind: {info.get('kind')!r}")


def construct_port_header_info(
	info: PortInfo,
) -> tuple[tuple[str, str, str, str], tuple[int, int, int, int]]:
	"""Return ``((parts...), (lengths...))`` for a port-header info dict."""
	match info.get("kind"):
		case "InterfacePortHeaderSyntax":
			iface  = info["interface"]
			mport  = info["modport"]
			full   = f"{iface}.{mport}" if mport else iface
			return (full, "", "", ""), (len(full), 0, 0, 0)

		case "NetPortHeaderSyntax":
			dtype, _ = construct_datatype(info["type"])
			dtype_s  = " ".join(p for p in dtype if p)
			direction= info["direction"]
			net_type = info["netType"]
			return (direction, net_type, dtype_s, ""), (
				len(direction), len(net_type), len(dtype_s), 0
			)

		case "VariablePortHeaderSyntax":
			const    = info["constKeyword"]
			dtype, _ = construct_datatype(info["type"])
			dtype_s  = " ".join(p for p in dtype if p)
			direction= info["direction"]
			var_kw   = info["varKeyword"]
			return (const, direction, var_kw, dtype_s), (
				len(const), len(direction), len(var_kw), len(dtype_s)
			)

		case _:
			raise ValueError(f"Unknown port-header kind: {info.get('kind')!r}")


class SystemVerilogWrapper:
	def __init__(self, top: str, wrapper_top: str, wrapper_file: str, sources: list[str]) -> None:
		logger.info(f'Create Wrapper for {top}')

		self.top = top
		self.wrapper_top = wrapper_top
		self.wrapper_file = wrapper_file

		os.makedirs(os.path.dirname(self.wrapper_file), exist_ok=True)

		self._initialize_fileset(sources)
		self._create_wrapper()

	def _initialize_fileset(self, fileset: list[str]) -> None:
		logger.info("Initializing and parsing fileset...")
		self.pyslang_data, self.fileset = resolve_files(fileset)

	def _top_module_interface_ports(self) -> list[tuple[str, str, str]]:
		"""Return ``[(port_name, interface_module, modport)]`` for interface ports."""
		pdata = self.pyslang_data[self.top]["headers"]["ports"]
		return [
			(name, info["header"]["interface"], info["header"]["modport"])
			for name, info in pdata.items()
			if info["header"].get("kind") == "InterfacePortHeaderSyntax"
		]

	def _resolve_wrapper_io(
		self,
	) -> tuple[list[str], list[str], list[str], dict[str, tuple]]:
		logger.info("Resolving wrapper IO...")

		# (instance_name, module_name, modport) - top module listed first,
		# then each interface port module.  Reversed so top ends up last in
		# the instantiation list (matches original ordering intent).
		flat_port_module_list: list[tuple[str, str, str]] = [
			(f"u_{self.top}", self.top, "")
		] + self._top_module_interface_ports()

		flat_params:  list[str] = []
		flat_ports:   list[str] = []
		flat_assign:  list[str] = []
		instantiations: dict[str, tuple] = {}

		for p_name, module, modport in reversed(flat_port_module_list):
			inst_ports:  list[tuple[str, str]] = []
			inst_params: list[tuple[str, str]] = []
			param_map:   dict[str, str]        = {}

			# ---- parameters ------------------------------------------------
			for pname, pval in self.pyslang_data[module]["headers"]["parameters"].items():
				dtype, _ = construct_datatype(pval["type"])
				keyword  = pval.get("keyword", "")
				decl     = pval.get("decl", {})
				dims     = decl.get("dimensions", "")
				expr     = decl.get("expr", "")

				# Prefix parameter names for interface modules to avoid clashes
				mapped = pname if module == self.top else f"{p_name.upper()}_{pname}"
				param_map[pname] = mapped
				inst_params.append((f".{pname}", f"({mapped})"))

				parts = [keyword] + [p for p in dtype if p] + [mapped, dims]
				if expr:
					parts.append(f"= {expr}")
				flat_params.append(" ".join(p for p in parts if p))

			# ---- ports -----------------------------------------------------
			if module == self.top:
				port_items = self.pyslang_data[module]["headers"]["ports"].items()
			elif modport:
				port_items = (
					self.pyslang_data[module]["members"]["modports"][modport]["ports"].items()
				)
			else:
				port_items = iter(())

			# Build regex only when there are parameters to substitute
			if param_map:
				_re_params = re.compile("|".join(re.escape(k) for k in param_map))

				def _sub_params(s: str) -> str:
					return _re_params.sub(lambda m: param_map[m.group(0)], s)
			else:
				def _sub_params(s: str) -> str:  # type: ignore[misc]
					return s

			for name, value in port_items:
				if module != self.top:
					direction   = value["direction"]
					declaration = self.pyslang_data[module]["members"]["declarations"][name]
					dtype, _    = construct_datatype(declaration["type"])
					dims        = declaration["decl"]["dimensions"]

					attrs    = declaration["attributes"]
					mods     = declaration["modifiers"]
					net_type = declaration["netType"]
					strength = declaration["strength"]
					exp_hint = declaration["expansionHint"]

					io_pname = f"{p_name}_{name}"
					parts    = [
						attrs, direction, mods, net_type, strength, exp_hint,
						*dtype, io_pname, dims,
					]
					type_str = _sub_params(" ".join(p for p in parts if p))
					flat_ports.append(type_str)

					if "output" in direction:
						flat_assign.append(f"assign {io_pname} = {p_name}.{name};")
					else:
						flat_assign.append(f"assign {p_name}.{name} = {io_pname};")

				else:
					inst_ports.append((f".{name} ", f"({name})"))
					if value["header"].get("kind") != "InterfacePortHeaderSyntax":
						attrs   = value["attributes"]
						dims    = value["dimensions"]
						hdr, _  = construct_port_header_info(value["header"])
						parts   = [attrs, *hdr, name, dims]
						flat_ports.append(" ".join(p for p in parts if p))

			instantiations[f"{module} #({{}}) {p_name} ({{}});"] = (
				inst_params,
				inst_ports,
			)

		return flat_params, flat_ports, flat_assign, instantiations

	def _create_wrapper(self) -> None:
		logger.info("Creating wrapper...")
		flat_params, flat_ports, flat_assign, instantiations = self._resolve_wrapper_io()

		param_block = ",\n\t".join(flat_params).strip().rstrip(",")
		port_block  = ",\n\t".join(flat_ports).strip().rstrip(",")
		assign_block= "\n\t".join(flat_assign).strip()

		inst_block  = ""
		for fmt, (param_list, port_list) in instantiations.items():
			pstr = ",\n\t\t".join(" ".join(p).strip() for p in param_list)
			qstr = ",\n\t\t".join(" ".join(p).strip() for p in port_list)
			inst_block += "\t" + fmt.format(
				f"\n\t\t{pstr}\n\t" if pstr else "",
				f"\n\t\t{qstr}\n\t" if qstr else "",
			) + "\n\n"

		lines = [
			f"module {self.wrapper_top} #(",
			f"\t{param_block}" if param_block else "\t// no parameters",
			f") (",
			f"\t{port_block}" if port_block else "\t// no ports",
			f");",
			inst_block,
			f"\t{assign_block}" if assign_block else "",
			f"endmodule",
		]

		with open(self.wrapper_file, "w", encoding="utf-8") as fh:
			fh.write("\n".join(lines))

		logger.info("Wrapper created: %s", self.wrapper_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="XVIV_WRAP_TOP: Create Top Wrapper")

	parser.add_argument("-t", "--top",       default="", dest="xviv_top",       help="Specify Top Module")
	parser.add_argument("-o",                default="", dest="out_dir",         help="Specify Wrapper Output Directory")
	parser.add_argument("--wrapper-dir",     default="", dest="out_dir",         help="Destination to store the generated synthesis wrapper")
	parser.add_argument("--dry-run",         action="store_true", dest="xviv_dry_run")
	parser.add_argument("--log-file",        default="", dest="xviv_log_file",   help="Path to log file")
	parser.add_argument("xviv_fileset",      nargs="*",                           help="Input source files")
	parser.add_argument("-i", "--include",   action="append", dest="xviv_include_dirs", default=[],
						help="Add an include directory")

	args = parser.parse_args()

	cleaned: list[str] = []
	for path in args.xviv_fileset:
		if not os.path.isfile(path):
			sys.stderr.write(f"Error: Invalid File: {path}\n")
			sys.exit(1)
		cleaned.append(os.path.abspath(path))
	args.xviv_fileset = cleaned

	if args.out_dir:
		args.out_dir = os.path.abspath(args.out_dir)

	for inc in args.xviv_include_dirs:
		if not os.path.isdir(inc):
			raise argparse.ArgumentTypeError(f"'{inc}' is not a valid directory.")

	return args


def main() -> None:
	config = parse_arguments()
	_setup_logging(config.xviv_log_file or "./build/xviv/xviv_wrap_top.log")
	SystemVerilogWrapper(config.xviv_top, config.out_dir, config.xviv_fileset)


if __name__ == "__main__":
	main()