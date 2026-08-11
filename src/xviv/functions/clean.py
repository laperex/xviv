import argparse
import glob
import logging
import os
import shutil

from xviv.config.project import XvivConfig

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

def execute_clean(cfg: XvivConfig, args: argparse.Namespace) -> None:
    dry_run = getattr(args, "dry_run", False)
    
    # 1. Handle stage-specific and system targets (Subcommands)
    cmd = getattr(args, "clean_cmd", None)
    
    if cmd == "all":
        _safe_rm(cfg.work_dir, dry_run)
        return
        
    elif cmd == "logs":
        for ext in ["*.jou", "*.log", "*.str", "*.pb", "*.wdb", "*.wcfg"]:
            for f in glob.glob(os.path.join(cfg.base_dir, ext)):
                _safe_rm(f, dry_run)
        return
        
    elif cmd == "cache":
        _safe_rm(os.path.join(cfg.base_dir, ".Xil"), dry_run)
        # Optional: Add Vivado IP cache dir here if mapped in project config
        return
        
    elif cmd in ("synth", "impl"):
        id_name = getattr(args, "design", None) or getattr(args, "bd", None) or getattr(args, "core", None)
        if id_name:
            # Impl artifacts share the synth directory hierarchy in xviv
            target_dir = os.path.join(cfg.synth_dir, id_name)
            _safe_rm(target_dir, dry_run)
        return
        
    elif cmd == "sim":
        if args.sim:
            target_dir = os.path.join(cfg.work_dir, "sim", args.sim)
            _safe_rm(target_dir, dry_run)
        return
        
    elif cmd == "formal":
        if args.target:
            # Matches the directory structure created by _sby_work_dir
            target_dir = os.path.join(cfg.formal_dir, args.target)
            _safe_rm(target_dir, dry_run)
        return

    # 2. Handle entity-based targets (Flags on base command)
    entity_maps = {
        "bd": (getattr(args, "bd", None), cfg.bd_dir),
        "core": (getattr(args, "core", None), cfg.core_dir),
        # ip, app, and platform directories map directly under the work_dir 
        "ip": (getattr(args, "ip", None), os.path.join(cfg.work_dir, "ip")),
        "app": (getattr(args, "app", None), os.path.join(cfg.work_dir, "app")),
        "platform": (getattr(args, "platform", None), os.path.join(cfg.work_dir, "platform")),
    }

    for ent_name, (val, base_path) in entity_maps.items():
        if val:
            if val == "all":
                _safe_rm(base_path, dry_run)
            else:
                _safe_rm(os.path.join(base_path, val), dry_run)
            return
            
    logger.warning("No valid target specified. Use 'xviv clean --help' for syntax.")
