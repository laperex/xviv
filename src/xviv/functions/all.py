from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from xviv.cli.command.bd import cmd_bd_create
from xviv.config.model import ProjectConfig
from xviv.functions.core import cmd_core_create
from xviv.functions.ip import cmd_ip_create

# -----------------------------------------------------------------------------
# create --all
# -----------------------------------------------------------------------------
def cmd_all_create(cfg: ProjectConfig):
	ip_vlnvs = {ip.vlnv for ip in cfg.ips}

	independent_cores = [c for c in cfg.cores if c.vlnv not in ip_vlnvs]
	dependent_cores = [c for c in cfg.cores if c.vlnv in ip_vlnvs]

	max_workers = getattr(cfg, "max_parallel_jobs", 4)

	def run_parallel(tasks: list[tuple[callable, str]], phase: int):
		with ThreadPoolExecutor(max_workers=max_workers) as pool:
			futures = {
				pool.submit(fn): label
				for fn, label in tasks
			}
			for fut in as_completed(futures):
				label = futures[fut]
				fut.result()
				print(f"[phase {phase}] {label} done")

	# -------------------------------------------------------------------------
	# Phase 1 - all IPs + cores not backed by a custom IP (parallel)
	# -------------------------------------------------------------------------
	phase1 = (
		[(partial(cmd_ip_create, cfg, ip.name), f"cmd_ip_create({ip.name})") for ip in cfg.ips] +
		[(partial(cmd_core_create, cfg, core.name, core.vlnv), f"cmd_core_create({core.name})") for core in independent_cores]
	)
	run_parallel(phase1, phase=1)

	# -------------------------------------------------------------------------
	# Phase 2 - cores whose vlnv IS a custom IP (must follow phase 1)
	# -------------------------------------------------------------------------
	if dependent_cores:
		phase2 = [
			(partial(cmd_core_create, cfg, core.name, core.vlnv), f"cmd_core_create({core.name})") for core in dependent_cores
		]
		run_parallel(phase2, phase=2)

	# -------------------------------------------------------------------------
	# Phase 3 - all block designs (parallel, after all IPs and cores are ready)
	# -------------------------------------------------------------------------
	phase3 = [
		(partial(cmd_bd_create, cfg, bd.name), f"cmd_bd_create({bd.name})") for bd in cfg.bds
	]
	run_parallel(phase3, phase=3)
