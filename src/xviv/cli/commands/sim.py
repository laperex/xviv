import typing
from xviv.config.model import ProjectConfig
from xviv.tools import vivado


# -----------------------------------------------------------------------------
# elaborate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_top_elaborate(cfg: ProjectConfig, top_name: str, run: typing.Optional[str]):
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)
	sim_files     = cfg.resolve_globs(cfg.get_simulation(top_name=top_name).rtl)

	xsim_lib  = "xv_work"
	timescale = "1ns/1ps"

	vivado.run_vivado_xvlog(cfg, xlib_work_dir, sim_files, xsim_lib=xsim_lib)

	run_all = run == "all"
	vivado.run_vivado_xelab(cfg, xlib_work_dir, top_name, timescale=timescale, xsim_lib=xsim_lib, run_all=run_all)

	if not run_all and run:
		cmd_top_simulate(cfg, top_name, run)

# -----------------------------------------------------------------------------
# simulate --top <top_name> [--run <time>]
# -----------------------------------------------------------------------------
def cmd_top_simulate(cfg: ProjectConfig, top_name: str, run: str = "all"):
	xlib_work_dir = cfg.get_xlib_work_dir(top_name)

	x_simulate_tcl = f"""
		log_wave -recursive *
		run {run}
		exit
	"""

	vivado.run_vivado_xsim(cfg, xlib_work_dir, top_name, x_simulate_tcl)