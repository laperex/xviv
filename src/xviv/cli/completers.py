"""
Completers and parser-helper utilities used by every command class.

Public API
----------
arg(container, *flags, completer=None, **kwargs)
	Thin wrapper around add_argument that attaches a completer in one call.

target_group(parser, *, ip, bd, top, required) -> MutuallyExclusiveGroup
	Adds the standard --ip / --bd / --top mutex group in one call.

c_ip, c_bd, c_app, c_platform, c_core   — name completers for each entity type
c_top_all, c_top_synth, c_top_sim        — top-module name completers
c_core_instance, c_core_vlnv             — re-exported catalog completers
dcp_stems_completer                      — completer for .dcp stem names
"""

import glob
import os

from xviv.catalog.completer import core_instance_completer
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


def _top_completer(*, synth: bool = True, sim: bool = True):
	def completer(prefix, parsed_args, **kwargs):
		try:
			cfg = load_config(os.path.abspath(resolve_config_completer(prefix, parsed_args)))
			tops = []
			if synth:
				tops += [s.top for s in cfg.synths]
			if sim:
				tops += [s.top for s in cfg.simulations]
			return tops
		except Exception:
			return []
	return completer


# ---------------------------------------------------------------------------
# Public completers
# ---------------------------------------------------------------------------

c_ip            = _cfg_completer("ips")
c_bd            = _cfg_completer("bds")
c_app           = _cfg_completer("apps")
c_platform      = _cfg_completer("platforms")
c_core          = _cfg_completer("cores")
c_top_all       = _top_completer(synth=True,  sim=True)
c_top_synth     = _top_completer(synth=True,  sim=False)
c_top_sim       = _top_completer(synth=False, sim=True)

c_core_instance = core_instance_completer


def dcp_stems_completer(prefix, parsed_args, **kwargs):
	"""Complete .dcp stem names (post_synth, post_place, post_route, ...)."""
	try:
		cfg = load_config(os.path.abspath(resolve_config_completer(prefix, parsed_args)))
		top = getattr(parsed_args, "top", None)
		if not top:
			return ["post_synth", "post_place", "post_route"]
		stems = [
			os.path.splitext(os.path.basename(f))[0]
			for f in glob.glob(os.path.join(cfg.build_dir, top, "*.dcp"))
		]
		return stems or ["post_synth", "post_place", "post_route"]
	except Exception:
		return ["post_synth", "post_place", "post_route"]


# ---------------------------------------------------------------------------
# Parser-building helpers
# ---------------------------------------------------------------------------

def arg(container, *flags, completer=None, **kwargs):
	action = container.add_argument(*flags, **kwargs)
	if completer is not None:
		action.completer = completer
	return action


def target_group(parser, *, ip: bool = False, bd: bool = False, top=None, required: bool = True):
	mg = parser.add_mutually_exclusive_group(required=required)

	if ip:
		arg(mg, "--ip", metavar="NAME", help="IP name", completer=c_ip)
	if bd:
		arg(mg, "--bd", metavar="NAME", help="BD name", completer=c_bd)
	if top:
		arg(mg, "--top", metavar="NAME", help="Top module name", completer=top)

	return mg