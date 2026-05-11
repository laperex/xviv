import glob
import os
import shutil

from xviv.config.loader import resolve_config_completer, load_config


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
				desc_text = desc_text[:avail - 1] + "…"
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
            ids = [(kind, name) for kind, name in [
                ('Design', synth.design_name),
                ('Core', synth.core_name),
                ('BD', synth.bd_name),
            ] if name]

            if len(ids) != 1:
                continue

            kind, name = ids[0]

            for phase, file in [
                ('synth', synth.synth_dcp_file),
                ('place', synth.place_dcp_file),
                ('route', synth.route_dcp_file),
            ]:
                if file:
                    rel = os.path.relpath(file, config_dir)
                    result[rel] = f'{phase} — {kind} — {name}'

        return result

    except Exception:
        return {}

def c_sim_modes(prefix, parsed_args, **kwargs):
    return [
		'default',
		'post_synth_functional',
		'post_synth_timing',
		'post_impl_functional',
		'post_impl_timing'
	]

# ---------------------------------------------------------------------------
# Public completers
# ---------------------------------------------------------------------------

c_ip            = _cfg_completer("_ip_list")
c_bd            = _cfg_completer("_bd_list")
c_app           = _cfg_completer("_app_list")
c_platform      = _cfg_completer("_platform_list")
c_core          = _cfg_completer("_core_list")
c_design        = _cfg_completer("_design_list")
c_sim_target    = _cfg_completer("_sim_list")

c_core_instance = core_instance_completer

# ---------------------------------------------------------------------------
# Parser-building helpers
# ---------------------------------------------------------------------------

def arg(container, *flags, completer=None, **kwargs):
	action = container.add_argument(*flags, **kwargs)
	if completer is not None:
		action.completer = completer
	return action


def target_group(parser, *,
	design: bool = False,
	ip: bool = False,
	bd: bool = False,
	sim: bool = False,
	sim_mode: bool = False,
	app: bool = False,
	platform: bool = False,
	wdb: bool = False,
	dcp: bool = False,
	core: bool = False,
	required: bool = True
):
	mg = parser.add_mutually_exclusive_group(required=required)
	
	if platform:
		arg(mg, "--platform", metavar="NAME", help="Platform name", completer=c_platform)
	if app:
		arg(mg, "--app", metavar="NAME", help="App name", completer=c_app)

	if sim:
		arg(mg, "--target", metavar="NAME", help="Simulation name", completer=c_sim_target)
	if wdb:
		arg(mg, "--wdb", metavar="NAME", help="Simulation target name in config", completer=c_sim_target)

	if dcp:
		arg(mg, "--dcp", metavar="NAME", help="Checkpoint file", completer=c_dcp_file)

	if ip:
		arg(mg, "--ip", metavar="NAME", help="IP name", completer=c_ip)

	if design:
		arg(mg, "--design", metavar="NAME", help="Design name", completer=c_design)
	if bd:
		arg(mg, "--bd", metavar="NAME", help="BD name", completer=c_bd)
	if core:
		arg(mg, "--core", metavar="NAME", help="Core name", completer=c_core)

	if sim_mode:
		arg(parser, "--mode", metavar="NAME", help="Core name", completer=c_sim_modes)

	return mg