from xviv.config.model import ProjectConfig
from xviv.simulation.waveform import open_snapshot, open_wdb, reload_snapshot, reload_wdb


# -----------------------------------------------------------------------------
# open --snapshot --top <top_name>
# -----------------------------------------------------------------------------
def cmd_snapshot_open(cfg: ProjectConfig, top_name: str):
	open_snapshot(cfg, top_name)


# -----------------------------------------------------------------------------
# open --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_open(cfg: ProjectConfig, top_name: str):
	open_wdb(cfg, top_name)


# -----------------------------------------------------------------------------
# reload --snapshot --top <top_name>
# -----------------------------------------------------------------------------
def cmd_snapshot_reload(cfg: ProjectConfig, top_name: str):
	reload_snapshot(cfg, top_name)


# -----------------------------------------------------------------------------
# reload --wdb --top <top_name>
# -----------------------------------------------------------------------------
def cmd_wdb_reload(cfg: ProjectConfig, top_name: str):
	reload_wdb(cfg, top_name)