
import argparse
import argcomplete
import glob
import os
from xviv.config.loader import load_config
from xviv.catalog.completer import _core_instance_completer, _core_vlnv_completer


def _find_config(prefix, parsed_args, **kwargs) -> str:
	cfg = getattr(parsed_args, "config", None)
	if cfg:
		return cfg
	if os.path.exists("project.cue"):
		return "project.cue"
	return "project.toml"


def _ip_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [ip.name for ip in cfg.ips]
	except Exception:
		return []


def _bd_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [bd.name for bd in cfg.bds]
	except Exception:
		return []

def _top_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s.top for s in cfg.synths] + [s.top for s in cfg.simulations]
	except Exception:
		return []

def _top_synth_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s.top for s in cfg.synths]
	except Exception:
		return []

def _top_sim_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [s.top for s in cfg.simulations]
	except Exception:
		return []


def _dcp_stems_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
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


def _platform_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [p.name for p in cfg.platforms]
	except Exception:
		return []

def _core_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [p.name for p in cfg.cores]
	except Exception:
		return []


def _app_names_completer(prefix, parsed_args, **kwargs):
	try:
		cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
		return [a.name for a in cfg.apps]
	except Exception:
		return []


def build_completions_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="xviv",
		description="FPGA project controller for Vivado / Vitis",
	)

	p.add_argument("--config", "-c", default="", metavar="TOML",
				help="Project configuration file (default: project.cue | project.toml)")
	p.add_argument("--log-file", default="", metavar="FILE",
				help="Append debug log to FILE")

	sub = p.add_subparsers(dest="command", required=True)

	# ------------------------------------------------------------------
	# create --ip | --bd | --app [--platform] [--template] | --platform
	# ------------------------------------------------------------------
	c = sub.add_parser("create", help="Create an IP, BD, platform, or app")

	c.add_argument("--ip", metavar="NAME", help="IP name").completer  = _ip_names_completer
	c.add_argument("--core", metavar="NAME", nargs="?", const="", default=None,
		help="Core instance name (optional — derived from --vlnv if omitted)").completer = _core_names_completer
	c.add_argument("--bd",       metavar="NAME", help="BD name").completer  = _bd_names_completer
	c.add_argument("--app",      metavar="NAME", help="App name").completer = _app_names_completer
	c.add_argument("--platform", metavar="NAME",
		help="Platform to create, or platform override when used with --app").completer = _platform_names_completer
	c.add_argument("--template", metavar="TMPL", default=None,
		help="App template override (used with --app)")
	c.add_argument("--vlnv", default=None,
		help="VLNV of IP from Vivado's IP catalog").completer = _core_instance_completer
	c.add_argument("--edit",      action="store_true", help="Customize in GUI")

	c = sub.add_parser("search", help="Search Vivado's IP catalog by name, VLNV, or keyword")
	c.add_argument(
		"query",
		metavar="QUERY",
		help="IP name, partial VLNV, or keyword (e.g. 'fifo', 'clk_wiz')",
	).completer = _core_vlnv_completer

	# ------------------------------------------------------------------
	# edit --ip | --bd
	# ------------------------------------------------------------------
	c = sub.add_parser("edit", help="Open an IP or BD in Vivado for editing")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip", metavar="NAME", help="IP name").completer = _ip_names_completer
	mg.add_argument("--bd", metavar="NAME", help="BD name").completer = _bd_names_completer
	mg.add_argument("--core", metavar="NAME", help="Core name").completer = _core_names_completer
	c.add_argument("--nogui",      action="store_true", help="Do Not Open in GUI | TCL Mode")

	# ------------------------------------------------------------------
	# config --ip | --bd | --top
	# ------------------------------------------------------------------
	c = sub.add_parser("config", help="Generate starter hooks for an IP, BD, or top")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip",  metavar="NAME", help="IP name").completer  = _ip_names_completer
	mg.add_argument("--bd",  metavar="NAME", help="BD name").completer  = _bd_names_completer
	mg.add_argument("--top", metavar="NAME", help="Top module name").completer = _top_synth_names_completer
	c.add_argument("--synth", action="store_true", dest="synth", help="for synthesis targets")
	# ------------------------------------------------------------------
	# generate --bd
	# ------------------------------------------------------------------
	c = sub.add_parser("generate", help="Generate output products for a BD")
	c.add_argument("--bd", required=True, metavar="NAME", help="BD name").completer = _bd_names_completer

	# ------------------------------------------------------------------
	# synth --ip | --bd [--ooc-run] | --top
	# ------------------------------------------------------------------
	c = sub.add_parser("synth", help="Synthesise an IP, BD, or top module")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip",  metavar="NAME", help="IP name").completer  = _ip_names_completer
	mg.add_argument("--bd",  metavar="NAME", help="BD name").completer  = _bd_names_completer
	mg.add_argument("--top", metavar="NAME", help="Top module name").completer = _top_synth_names_completer
	c.add_argument("--ooc-run", action="store_true", dest="ooc_run",
		help="Run out-of-context synthesis for leaf IPs (BD only)")

	# ------------------------------------------------------------------
	# open --dcp --top | --snapshot --top | --wdb --top
	# ------------------------------------------------------------------
	c = sub.add_parser("open", help="Open a checkpoint, simulation snapshot, or waveform DB")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--dcp",      metavar="STEM",
		help="Checkpoint stem (e.g. post_synth)").completer = _dcp_stems_completer
	mg.add_argument("--snapshot", action="store_true",
		help="Open simulation snapshot in xsim GUI")
	mg.add_argument("--wdb",      action="store_true",
		help="Open waveform DB in xsim GUI")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--ip",  metavar="NAME", help="IP name").completer  = _ip_names_completer
	mg.add_argument("--bd",  metavar="NAME", help="BD name").completer  = _bd_names_completer
	mg.add_argument("--top", metavar="NAME", help="Top module name").completer = _top_names_completer
	c.add_argument("--nogui",      action="store_true", help="Do Not Open in GUI | TCL Mode")

	# ------------------------------------------------------------------
	# elaborate --top [--run <time>]
	# ------------------------------------------------------------------
	c = sub.add_parser("elaborate", help="Compile and optionally run simulation")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Simulation top module").completer = _top_sim_names_completer
	c.add_argument("--run", metavar="TIME", default="",
		help="Simulation run time, e.g. 1000ns")
	
	# ------------------------------------------------------------------
	# simulate --top [--run <time>]
	# ------------------------------------------------------------------
	c = sub.add_parser("simulate", help="Run simulation")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Simulation top module").completer = _top_sim_names_completer
	c.add_argument("--run", metavar="TIME", default="",
		help="Simulation run time, e.g. 1000ns")

	# ------------------------------------------------------------------
	# reload --snapshot --top | --wdb --top
	# ------------------------------------------------------------------
	c = sub.add_parser("reload", help="Restart a simulation snapshot or reload a waveform DB")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--snapshot", action="store_true", help="Restart snapshot")
	mg.add_argument("--wdb",      action="store_true", help="Reload waveform window")
	c.add_argument("--top", required=True, metavar="NAME",
		help="Simulation top module").completer = _top_synth_names_completer

	# ------------------------------------------------------------------
	# build --platform | --app [--info]
	# ------------------------------------------------------------------
	c = sub.add_parser("build", help="Compile a BSP platform or application")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--platform", metavar="NAME",
		help="Platform name").completer = _platform_names_completer
	mg.add_argument("--app",      metavar="NAME",
		help="App name").completer      = _app_names_completer
	c.add_argument("--info", action="store_true",
		help="Print ELF section sizes after build (used with --app)")

	# ------------------------------------------------------------------
	# program [--app | --platform] [--elf | --bitstream]
	# ------------------------------------------------------------------
	c = sub.add_parser("program", help="Download bitstream and/or ELF to FPGA")
	bit_src = c.add_mutually_exclusive_group()
	bit_src.add_argument("--platform",  metavar="NAME",
		help="Derive bitstream from [[platform]] entry").completer = _platform_names_completer
	bit_src.add_argument("--bitstream", metavar="PATH",
		help="Explicit path to .bit file")
	elf_src = c.add_mutually_exclusive_group()
	elf_src.add_argument("--app", metavar="NAME",
		help="Derive ELF from [[app]] build dir").completer = _app_names_completer
	elf_src.add_argument("--elf", metavar="PATH",
		help="Explicit path to .elf file")

	# ------------------------------------------------------------------
	# processor --reset | --status
	# ------------------------------------------------------------------
	c = sub.add_parser("processor", help="Control the embedded processor via JTAG")
	mg = c.add_mutually_exclusive_group(required=True)
	mg.add_argument("--reset",  action="store_true", help="Soft-reset the processor")
	mg.add_argument("--status", action="store_true", help="Print processor state and registers")

	return p