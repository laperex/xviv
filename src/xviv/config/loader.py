
import json
import os
import subprocess
import sys
import tomllib
from xviv.config import model


def load_config(path: str) -> model.ProjectConfig:
	"""
	Parse project.toml and return a fully validated model.ProjectConfig.
	This is the only function that reads the raw TOML dict.
	"""
	path = os.path.abspath(path)
	if not os.path.isfile(path):
		sys.exit(f"ERROR: Config file not found - {path}")

	ext = os.path.splitext(path)[1].lower()

	if ext == ".toml":
		with open(path, "rb") as fh:
			raw = tomllib.load(fh)

	elif ext == ".cue":
		try:
			result = subprocess.run(
				["cue", "export", path, "--out", "json"],
				capture_output=True,
				text=True,
				check=True
			)
			raw = json.loads(result.stdout)
		except subprocess.CalledProcessError as e:
			sys.exit(f"ERROR: CUE validation failed in {path}:\n{e.stderr}")
		except FileNotFoundError:
			sys.exit("ERROR: 'cue' CLI not found. Please install it: https://cuelang.org/docs/install/")
		except json.JSONDecodeError as e:
			sys.exit(f"ERROR: Failed to parse CUE JSON output:\n{e}")

	else:
		sys.exit(f"ERROR: Unsupported configuration format '{ext}'. Must be .toml or .cue")

	base_dir = os.path.dirname(path)

	fpga_default_ref, fpga_named = model._parse_fpga(raw)

	if fpga_default_ref is None and not fpga_named:
		sys.exit(
			"ERROR: project.toml must define at least one FPGA target:\n"
			"  [fpga] default = '...'        (default target)\n"
			"  [fpga.<name>] part = '...' (named target, select with  fpga = '<name>')"
		)

	return model.ProjectConfig(
		base_dir     = base_dir,
		fpga_default_ref = fpga_default_ref,
		fpga_named   = fpga_named,
		vivado       = model._parse_vivado(raw),
		vitis        = model._parse_vitis(raw),
		build        = model._parse_build(raw),
		# sources      = model._parse_sources(raw),
		ips          = model._parse_ips(raw),
		bds          = model._parse_bds(raw),
		synths       = model._parse_synths(raw),
		simulations  = model._parse_simulations(raw),
		platforms    = model._parse_platforms(raw),
		apps         = model._parse_apps(raw),
	)