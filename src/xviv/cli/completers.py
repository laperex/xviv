import os
import pathlib
import shutil

from xviv.config.loader import load_config, resolve_config_completer

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cfg_completer(collection: str, attr: str = "name"):
	def completer(prefix, parsed_args, **kwargs):
		try:
			cfg = load_config(os.path.abspath(resolve_config_completer(prefix, parsed_args)))
			return [getattr(item, attr) for item in getattr(cfg, collection)]
		except Exception:
			return []

	return completer


def core_instance_completer(prefix: str, parsed_args, **kwargs) -> dict[str, str]:
	def _term_width() -> int:
		return shutil.get_terminal_size().columns * 2

	def _fmt_instance_desc(vlnv: str, entry) -> str:
		parts = [vlnv, entry.display_name]
		flags = []
		if entry.hidden:
			flags.append("⚠ internal")
		if entry.board_dependent:
			flags.append("⚠ board-dep")
		if entry.ipi_only:
			flags.append("⚠ IPI-only")
		if flags:
			parts.append("  ".join(flags))
		desc_text = " ".join(entry.description.split())
		avail = _term_width() - sum(len(p) + 2 for p in parts)
		if avail > 10 and desc_text:
			if len(desc_text) > avail:
				desc_text = desc_text[: avail - 1] + "…"
			parts.append(f"— {desc_text}")
		return "  ".join(parts)

	try:
		comp_line = os.environ.get("COMP_LINE", "")
		comp_point = int(os.environ.get("COMP_POINT", len(comp_line)))
		tokens = comp_line[:comp_point].split()
		real_prefix = tokens[-1] if tokens else prefix

		catalog = load_config(resolve_config_completer(prefix, parsed_args)).get_catalog()

		completions: dict[str, str] = {}

		for vlnv, entry in catalog.items():
			name_ver = f"{entry.name}:{entry.version}"
			desc = _fmt_instance_desc(vlnv, entry)

			if name_ver.startswith(real_prefix):
				completions[name_ver] = desc
			else:
				completions[vlnv] = desc
		return completions
	except Exception:
		return {}


def c_dcp_file(prefix, parsed_args, **kwargs):
	try:
		config_path = os.path.abspath(resolve_config_completer(prefix, parsed_args))
		cfg = load_config(config_path)
		config_dir = os.path.dirname(config_path)

		result: dict[str, str] = {}

		for synth in cfg._synth_list:
			ids = [
				(kind, name)
				for kind, name in [
					("Design", synth.design_name),
					("Core", synth.core_name),
					("BD", synth.bd_name),
				]
				if name
			]

			if len(ids) != 1:
				continue

			kind, name = ids[0]

			for phase, file in [
				("synth", synth.synth_dcp_file),
				("place", synth.place_dcp_file),
				("route", synth.route_dcp_file),
			]:
				if file:
					rel = os.path.relpath(file, config_dir)
					result[rel] = f"{phase} — {kind} — {name}"

		return result

	except Exception:
		return {}


def c_bitstream(prefix, parsed_args, **kwargs):
	try:
		config_path = os.path.abspath(resolve_config_completer(prefix, parsed_args))
		cfg = load_config(config_path)

		result: list[str] = []

		for platform in cfg._platform_list:
			result.append(os.path.relpath(platform.bitstream_file, os.path.dirname(config_path)))

		for synth in cfg._synth_list:
			if synth.bitstream_file:
				if synth.bitstream_file not in result:
					result.append(os.path.relpath(synth.bitstream_file, os.path.dirname(config_path)))

		return result

	except Exception:
		return {}


def c_elf(prefix, parsed_args, **kwargs):
	try:
		config_path = os.path.abspath(resolve_config_completer(prefix, parsed_args))
		cfg = load_config(config_path)

		result: list[str] = []

		for app in cfg._app_list:
			result.append(os.path.relpath(app.elf_file, os.path.dirname(config_path)))

		return result

	except Exception:
		return {}


def c_uvm_test(prefix, parsed_args, **kwargs):

	try:
		config_path = os.path.abspath(resolve_config_completer(prefix, parsed_args))
		cfg = load_config(config_path)
		result: dict[str, str] = {}

		target = vars(parsed_args).get("target", None)

		pathlib.Path("/tmp/xviv_debug.log").write_text(
			f"target={target!r}\nuvm_simulations={[uvm.simulation for uvm in cfg._uvm_list]}\n"
		)

		if target:
			for uvm in cfg._uvm_list:
				if uvm.simulation == target:
					result[uvm.test] = f"{uvm.test} : {uvm.verbosity}"
		else:
			for uvm in cfg._uvm_list:
				result[uvm.test] = f"{uvm.simulation} - {uvm.test} : {uvm.verbosity}"

		return result
	except Exception as e:
		pathlib.Path("/tmp/xviv_debug.log").write_text(f"EXCEPTION: {e}\n")
		return []


# ---------------------------------------------------------------------------
# Public completers
# ---------------------------------------------------------------------------

c_ip = _cfg_completer("_ip_list")
c_bd = _cfg_completer("_bd_list")
c_app = _cfg_completer("_app_list")
c_platform = _cfg_completer("_platform_list")
c_core = _cfg_completer("_core_list")
c_design = _cfg_completer("_design_list")
c_sim_target = _cfg_completer("_sim_list")
c_formal_target = _cfg_completer("_formal_list")

c_core_instance = core_instance_completer

# ---------------------------------------------------------------------------
# Parser-building helpers
# ---------------------------------------------------------------------------


def arg(container, *flags, completer=None, **kwargs):
	action = container.add_argument(*flags, **kwargs)
	if completer is not None:
		action.completer = completer
	return action


def target_group(
	parser,
	exclusive: bool = True,
	required: bool = True,
	*,
	design: bool = False,
	ip: bool = False,
	bd: bool = False,
	sim_target: bool = False,
	uvm_test: bool = False,
	formal_target: bool = False,
	app: bool = False,
	platform: bool = False,
	wdb: bool = False,
	dcp: bool = False,
	core: bool = False,
	bitstream: bool = False,
	elf: bool = False,
):
	grp = parser

	if exclusive:
		grp = parser.add_mutually_exclusive_group(required=required)
		required = False

	if app:
		arg(grp, "--app", metavar="NAME", help="App name", completer=c_app, required=required)
	if platform:
		arg(grp, "--platform", metavar="NAME", help="Platform name", completer=c_platform, required=required)

	if sim_target:
		arg(grp, "--target", metavar="NAME", help="Simulation Target name", completer=c_sim_target, required=required)
	if uvm_test:
		arg(grp, "--uvm", metavar="NAME", help="Uvm Test name", completer=c_uvm_test, required=required)
	# if sim_mode:
	# 	arg(grp, "--mode", metavar="NAME", help="Core name", completer=c_sim_modes, required=required)

	if formal_target:
		arg(grp, "--target", metavar="NAME", help="Formal Target name", completer=c_formal_target, required=required)

	if wdb:
		arg(grp, "--wdb", metavar="NAME", help="Simulation Target name", completer=c_sim_target, required=required)

	if dcp:
		arg(grp, "--dcp", metavar="NAME", help="Checkpoint File", completer=c_dcp_file, required=required)

	if ip:
		arg(grp, "--ip", metavar="NAME", help="IP name", completer=c_ip, required=required)

	if design:
		arg(grp, "--design", metavar="NAME", help="Design name", completer=c_design, required=required)
	if bd:
		arg(grp, "--bd", metavar="NAME", help="BD name", completer=c_bd, required=required)
	if core:
		arg(grp, "--core", metavar="NAME", help="Core name", completer=c_core, required=required)

	if bitstream:
		arg(
			grp,
			"--bitstream",
			metavar="PATH",
			help="Explicit path to .bit file",
			completer=c_bitstream,
			required=required,
		)

	if elf:
		arg(grp, "--elf", metavar="PATH", help="Explicit path to .elf file", completer=c_elf, required=required)

	return grp
