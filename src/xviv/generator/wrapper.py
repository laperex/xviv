from __future__ import annotations

import argparse
import logging
import os
import re

from xviv.parsers.rtl import (
	IfaceSignal,
	ModuleInfo,
	ParamDecl,
	PortDecl,
	resolve_modules,
)
from xviv.utils.fs import assert_file_exists
from xviv.utils.log import setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Code-generation helpers
# ---------------------------------------------------------------------------


def _param_decl_str(name: str, pdecl: ParamDecl, mapped: str) -> str:

	parts = [pdecl.keyword, pdecl.type_str, mapped]
	if pdecl.default_str:
		parts.append(f"= {pdecl.default_str}")
	return " ".join(p for p in parts if p)


def _port_decl_str(pdecl: PortDecl) -> str:

	parts = [pdecl.direction, pdecl.type_str, pdecl.name]
	return " ".join(p for p in parts if p)


def _iface_port_decl_str(sig: IfaceSignal, io_name: str, subbed_type: str) -> str:

	parts = [sig.direction, subbed_type, io_name]
	return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# SystemVerilogWrapper
# ---------------------------------------------------------------------------


class SystemVerilogWrapper:
	def __init__(
		self,
		top: str,
		wrapper_top: str,
		wrapper_file: str,
		sources: list[str],
	) -> None:
		logger.info("Create Wrapper for %s", top)

		self.top = top
		self.wrapper_top = wrapper_top
		self.wrapper_file = wrapper_file

		logger.debug("wrapper sources: %s", sources)

		os.makedirs(os.path.dirname(self.wrapper_file), exist_ok=True)

		self._initialize_fileset(sources)
		self._create_wrapper()

	# ------------------------------------------------------------------
	# Initialisation
	# ------------------------------------------------------------------

	def _initialize_fileset(self, fileset: list[str]) -> None:
		logger.debug("Initialising and parsing fileset...")
		self.module_data: dict[str, ModuleInfo] = resolve_modules(fileset)
		logger.debug("Modules resolved: %s", list(self.module_data.keys()))

	# ------------------------------------------------------------------
	# Interface-port helpers
	# ------------------------------------------------------------------

	def _top_interface_ports(self) -> list[tuple[str, str, str]]:

		top_info = self.module_data[self.top]
		return [(pname, pdecl.interface_name, pdecl.modport_name) for pname, pdecl in top_info.ports.items() if pdecl.is_interface]

	# ------------------------------------------------------------------
	# I/O resolution
	# ------------------------------------------------------------------

	def _resolve_wrapper_io(
		self,
	) -> tuple[list[str], list[str], list[str], dict[str, tuple]]:

		logger.debug("Resolving wrapper IO...")

		top_info = self.module_data[self.top]

		# Processing order: top module first, then one entry per interface port.
		# The list is reversed when iterating so instantiation order matches
		# the original behaviour (interface instances precede the top module).
		flat_port_module_list: list[tuple[str, str, str]] = [(f"u_{self.top}", self.top, "")] + self._top_interface_ports()

		flat_params: list[str] = []
		flat_ports: list[str] = []
		flat_assign: list[str] = []
		instantiations: dict[str, tuple] = {}

		for inst_name, module_name, modport_name in reversed(flat_port_module_list):
			mod_info = self.module_data[module_name]
			inst_params: list[tuple[str, str]] = []
			inst_ports: list[tuple[str, str]] = []
			param_map: dict[str, str] = {}

			# ---- parameters ----------------------------------------
			for pname, pdecl in mod_info.params.items():
				# Prefix parameter names for interface modules to avoid clashes
				# with the top module's own parameters.
				mapped = pname if module_name == self.top else f"{inst_name.upper()}_{pname}"
				param_map[pname] = mapped
				inst_params.append((f".{pname}", f"({mapped})"))
				flat_params.append(_param_decl_str(pname, pdecl, mapped))

			# Build a substitution function for parameter name replacement
			# inside interface signal types (e.g. WIDTH -> U_M_AXI_WIDTH).
			if param_map:
				_pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in param_map) + r")\b")

				def _sub(s: str, _pm: dict = param_map, _re: re.Pattern = _pat) -> str:
					return _re.sub(lambda m: _pm[m.group(0)], s)
			else:

				def _sub(s: str) -> str:  # type: ignore[misc]
					return s

			# ---- ports ---------------------------------------------
			if module_name == self.top:
				# Emit every non-interface port as a flat wrapper port and
				# connect it directly to the top instance by name.
				for pname, pdecl in mod_info.ports.items():
					if pdecl.is_interface:
						# Connect to the interface instance (same name as port)
						inst_ports.append((f".{pname}", f"({pname})"))
					else:
						inst_ports.append((f".{pname} ", f"({pname})"))
						flat_ports.append(_port_decl_str(pdecl))

			else:
				# Interface module: expand modport signals into flat ports and
				# connect via assign statements.
				# The signals for this port live in top_info.iface_signals,
				# keyed by the port name (= inst_name for interface entries).
				signals = top_info.iface_signals.get(inst_name, {})
				for sig_name, sig in signals.items():
					io_pname = f"{inst_name}_{sig_name}"
					type_str = _sub(sig.type_str)
					flat_ports.append(_iface_port_decl_str(sig, io_pname, type_str))

					if "output" in sig.direction:
						flat_assign.append(f"assign {io_pname} = {inst_name}.{sig_name};")
					else:
						flat_assign.append(f"assign {inst_name}.{sig_name} = {io_pname};")

			instantiations[f"{module_name} #({{}}) {inst_name} ({{}});"] = (
				inst_params,
				inst_ports,
			)

		return flat_params, flat_ports, flat_assign, instantiations

	# ------------------------------------------------------------------
	# SV file generation
	# ------------------------------------------------------------------

	def _create_wrapper(self) -> None:
		logger.debug("Creating wrapper...")
		flat_params, flat_ports, flat_assign, instantiations = self._resolve_wrapper_io()

		param_block = ",\n\t".join(flat_params).strip().rstrip(",")
		port_block = ",\n\t".join(flat_ports).strip().rstrip(",")
		assign_block = "\n\t".join(flat_assign).strip()

		inst_block = ""
		for fmt, (param_list, port_list) in instantiations.items():
			pstr = ",\n\t\t".join(" ".join(p).strip() for p in param_list)
			qstr = ",\n\t\t".join(" ".join(p).strip() for p in port_list)
			inst_block += (
				"\t"
				+ fmt.format(
					f"\n\t\t{pstr}\n\t" if pstr else "",
					f"\n\t\t{qstr}\n\t" if qstr else "",
				)
				+ "\n\n"
			)

		lines = [
			f"module {self.wrapper_top} #(",
			f"\t{param_block}" if param_block else "\t// no parameters",
			") (",
			f"\t{port_block}" if port_block else "\t// no ports",
			");",
			inst_block,
			f"\t{assign_block}" if assign_block else "",
			"endmodule",
		]

		with open(self.wrapper_file, "w", encoding="utf-8") as fh:
			fh.write("\n".join(lines))

		logger.info("Wrapper created: %s", self.wrapper_file)


# ---------------------------------------------------------------------------
# CLI (unchanged)
# ---------------------------------------------------------------------------


def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="XVIV_WRAP_TOP: Create Top Wrapper")

	parser.add_argument("-t", "--top", default="", dest="xviv_top", help="Specify Top Module")
	parser.add_argument("-o", default="", dest="out_dir", help="Specify Wrapper Output Directory")
	parser.add_argument("--wrapper-dir", default="", dest="out_dir", help="Destination to store the generated synthesis wrapper")
	parser.add_argument("--dry-run", action="store_true", dest="xviv_dry_run")
	parser.add_argument("--log-file", default="", dest="xviv_log_file", help="Path to log file")
	parser.add_argument("xviv_fileset", nargs="*", help="Input source files")
	parser.add_argument("-i", "--include", action="append", dest="xviv_include_dirs", default=[], help="Add an include directory")

	args = parser.parse_args()

	cleaned: list[str] = []
	for path in args.xviv_fileset:
		if not os.path.isfile(path):
			assert_file_exists(path)
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
	setup_logging(config.xviv_log_file)
	SystemVerilogWrapper(config.xviv_top, config.out_dir, config.xviv_fileset)


if __name__ == "__main__":
	main()
