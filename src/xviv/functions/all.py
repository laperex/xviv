
from xviv.config.model import ProjectConfig


# -----------------------------------------------------------------------------
# create --all
# -----------------------------------------------------------------------------
def cmd_all_create(cfg: ProjectConfig):
	for ip in cfg.ips:
		print(ip.name)

	for core in cfg.cores:
		print(core.name)

	for bd in cfg.bds:
		print(bd.name)
