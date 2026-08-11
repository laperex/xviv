# import argparse
import glob
import logging
import os
import shutil

from xviv.config.params import CleanParams
from xviv.config.project import XvivConfig
from xviv.utils.fs import resolve_globs

logger = logging.getLogger(__name__)


def _safe_rm(path: str, dry_run: bool) -> None:
	if not os.path.exists(path):
		return

	if dry_run:
		logger.info(f"[DRY RUN] Would delete: {path}")
		return

	try:
		if os.path.isdir(path):
			shutil.rmtree(path)
		else:
			os.remove(path)
		logger.info(f"Deleted: {path}")
	except OSError as e:
		logger.error(f"Failed to remove {path}: {e}")


def cmd_clean(
	cfg: XvivConfig,
	*,
	design_name: str | None = None,
	bd_name: str | None = None,
	core_name: str | None = None,
	ip_name: str | None = None,
	app_name: str | None = None,
	platform_name: str | None = None,
	params: CleanParams,
) -> None:
	if params.all:
		_safe_rm(cfg.work_dir, cfg.dry_run)

	elif params.logs:
		for ext in ["*.jou", "*.log", "*.str", "*.pb", "*.wdb", "*.wcfg"]:
			for f in resolve_globs([os.path.join(cfg.base_dir, ext)], cfg.base_dir):
				_safe_rm(f, cfg.dry_run)

	elif params.cache:
		_safe_rm(os.path.join(cfg.base_dir, ".Xil"), cfg.dry_run)
		# Optional: Add Vivado IP cache dir here if mapped in project config

	elif params.synth or params.impl:
		if param_ids := [i for i in [design_name, core_name, bd_name] if i]:
			# Impl artifacts share the synth directory hierarchy in xviv
			target_dir = os.path.join(cfg.synth_dir, param_ids[0])
			_safe_rm(target_dir, cfg.dry_run)

	elif params.sim_target:
		target_dir = os.path.join(cfg.work_dir, "sim", params.sim_target)
		_safe_rm(target_dir, cfg.dry_run)

	elif params.formal_target:
		target_dir = os.path.join(cfg.formal_dir, params.formal_target)
		_safe_rm(target_dir, cfg.dry_run)

	else:
		# 2. Handle entity-based targets (Flags on base command)
		entity_maps = {
			"bd": (bd_name, cfg.bd_dir),
			"core": (core_name, cfg.core_dir),
			# ip, app, and platform directories map directly under the work_dir
			"ip": (ip_name, os.path.join(cfg.work_dir, "ip")),
			"app": (app_name, os.path.join(cfg.work_dir, "app")),
			"platform": (platform_name, os.path.join(cfg.work_dir, "platform")),
		}

		for name, (val, base_path) in entity_maps.items():
			if val:
				if val == "all":
					_safe_rm(base_path, cfg.dry_run)
				else:
					if name == "ip":
						val = cfg.get_ip(val).vid

					_safe_rm(os.path.join(base_path, val), cfg.dry_run)
