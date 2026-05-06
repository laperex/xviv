from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from xviv.functions.bd import cmd_bd_create
from xviv.config.project import XvivConfig
from xviv.functions.core import cmd_core_create
from xviv.functions.ip import cmd_ip_create
from xviv.utils.parallel import run_parallel

# -----------------------------------------------------------------------------
# create --all
# -----------------------------------------------------------------------------
def cmd_all_create(cfg: XvivConfig):
	ip_vlnvs = {ip.vlnv for ip in cfg.ips}

	independent_cores = [c for c in cfg.cores if c.vlnv not in ip_vlnvs]
	dependent_cores = [c for c in cfg.cores if c.vlnv in ip_vlnvs]

	max_workers = cfg.build.max_parallel_jobs

	# -------------------------------------------------------------------------
	# Stage 1 - all IPs + cores not backed by a custom IP (parallel)
	# -------------------------------------------------------------------------
	run_parallel(
		[(partial(cmd_ip_create, cfg, ip.name), f"cmd_ip_create({ip.name})") for ip in cfg.ips] +
		[(partial(cmd_core_create, cfg, core.name, core.vlnv), f"cmd_core_create({core.name})") for core in independent_cores],
	stage=1, max_workers=max_workers)

	# -------------------------------------------------------------------------
	# Stage 2 - cores whose vlnv IS a custom IP (must follow stage 1)
	# -------------------------------------------------------------------------
	if dependent_cores:
		run_parallel(
			[(partial(cmd_core_create, cfg, core.name, core.vlnv), f"cmd_core_create({core.name})") for core in dependent_cores] +
			[(partial(cmd_bd_create, cfg, bd.name), f"cmd_bd_create({bd.name})") for bd in cfg.bds],
		stage=2, max_workers=max_workers)

	# # -------------------------------------------------------------------------
	# # Stage 3 - all block designs (parallel, after all IPs and cores are ready)
	# # -------------------------------------------------------------------------
	# run_parallel(
	# 	[(partial(cmd_bd_create, cfg, bd.name), f"cmd_bd_create({bd.name})") for bd in cfg.bds],
	# stage=3, max_workers=max_workers)
