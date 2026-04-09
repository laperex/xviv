#!/usr/bin/env python3
"""
xviv  -  FPGA project controller for Vivado / Vitis
Reads project.toml and drives Vivado, xsct, or standalone Xilinx tools.

Usage:
xviv [--config project.toml] <command> [options]

Vivado-backed commands:
create-ip    --ip   <n>
edit-ip      --ip   <n>
ip-config    --ip   <n>
create-bd    --bd   <n>
edit-bd      --bd   <n>
generate-bd  --bd   <n>
export-bd    --bd   <n>
bd-config    --bd   <n>
synthesis    --top  <module>
synth-config --top  <module>
simulate     --top  <sim_top>  [--so libdpi]  [--dpi-lib ./build/libs]
open-dcp     --top  <module>   [--dcp post_synth]

xsct-backed commands (MicroBlaze / Vitis):
create-platform  --platform <n>
platform-build   --platform <n>
create-app       --app <n>  [--platform <n>]  [--template <t>]
app-build        --app <n>  [--info]
program          (--bitstream <path> | --platform <n>)  [--elf <path> | --app <n>]
processor        (--reset | --status)
jtag-monitor     --uart

Standalone commands:
open-wdb        --top <sim_top>
reload-wdb      --top <sim_top>
open-snapshot   --top <sim_top>
reload-snapshot --top <sim_top>
"""

import argparse
import glob as _glob
import logging
import os
import subprocess
import sys
import argcomplete

from xviv import config, wrapper
from xviv.config import _resolve_globs, generate_config_tcl, load_config
from xviv.hooks import generate_bd_hooks, generate_ip_hooks, generate_synth_hooks
from xviv.platform import _app_dir, _bsp_dir, _find_elf, _hw_server, _mb_tool, _platform_paths, _resolve_app_cfg, _resolve_platform_cfg, _transform_app_makefile
from xviv.utils import _atomic_symlink, _git_sha_tag, _setup_logging
from xviv.vitis import _find_xsct_script, _get_vitis_env, run_xsct, run_xsct_live
from xviv.vivado import _find_tcl_script, _strip_bd_tcl, run_vivado, run_vivado_xelab, run_vivado_xsim, run_vivado_xvlog
from xviv.waveform import open_snapshot, open_wdb, reload_snapshot, reload_wdb

logger = logging.getLogger(__name__)


def _find_config(prefix, parsed_args, **kwargs) -> str:
    return getattr(parsed_args, "config", None) or "project.toml"


def _ip_names_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        return [ip["name"] for ip in cfg.get("ip", [])]
    except Exception:
        return []


def _bd_names_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        return [bd["name"] for bd in cfg.get("bd", [])]
    except Exception:
        return []


def _top_names_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        return [s["top"] for s in cfg.get("synthesis", [])]
    except Exception:
        return []


def _dcp_stems_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        top = getattr(parsed_args, "top", None)
        build_dir = cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR)
        if not top:
            return ["post_synth", "post_place", "post_route"]
        stems = [
            os.path.splitext(os.path.basename(f))[0]
            for f in _glob.glob(os.path.join(build_dir, top, "*.dcp"))
        ]
        return stems or ["post_synth", "post_place", "post_route"]
    except Exception:
        return ["post_synth", "post_place", "post_route"]


def _platform_names_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        return [p["name"] for p in cfg.get("platform", [])]
    except Exception:
        return []


def _app_names_completer(prefix, parsed_args, **kwargs):
    try:
        cfg = load_config(os.path.abspath(_find_config(prefix, parsed_args)))
        return [a["name"] for a in cfg.get("app", [])]
    except Exception:
        return []


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xviv",
        description="FPGA project controller for Vivado / Vitis",
    )
    p.add_argument(
        "--config", "-c",
        default="project.toml",
        metavar="TOML",
        help="Project configuration file (default: project.toml)",
    )
    p.add_argument(
        "--log-file",
        default="",
        metavar="FILE",
        help="Append debug log to FILE",
    )

    sub = p.add_subparsers(dest="command", required=True)

    def _cmd(name: str, help_str: str):
        return sub.add_parser(name, help=help_str)

    for name in ("create-ip", "edit-ip"):
        c = _cmd(name, f"{name} for the specified IP")
        c.add_argument(
            "--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
        ).completer = _ip_names_completer

    c = _cmd("ip-config", "Generate a starter hooks file for an IP")
    c.add_argument(
        "--ip", required=True, help="IP name as defined in [[ip]] TOML entry"
    ).completer = _ip_names_completer

    for name in ("create-bd", "edit-bd", "generate-bd"):
        c = _cmd(name, f"{name} for the specified Block Design")
        c.add_argument(
            "--bd", required=True, help="BD name as defined in [[bd]] TOML entry"
        ).completer = _bd_names_completer

    c = _cmd("export-bd", "Export the current BD as a versioned re-runnable TCL script")
    c.add_argument(
        "--bd",
        required=True,
        help="BD name as defined in [[bd]] TOML entry"
    ).completer = _bd_names_completer

    c = _cmd("bd-config", "Generate a starter hooks file for a BD")
    c.add_argument(
        "--bd",
        required=True,
        help="BD name as defined in [[bd]] TOML entry"
    ).completer = _bd_names_completer

    c = _cmd("synthesis", "Synthesise, place, route, and write bitstream")
    c.add_argument(
        "--top",
        required=True,
        help="Top module name"
    ).completer = _top_names_completer

    c.add_argument("--out-of-context", required=True, help="Enable Out of Context Synthesis")
    c.add_argument("--report-all", required=True, help="Enable All Reports")
    c.add_argument("--report-synth", required=True, help="Synthesis Reports")
    c.add_argument("--report-place", required=True, help="Placement Reports")
    c.add_argument("--report-route", required=True, help="Routing Reports")
    c.add_argument(
        "--generate-netlist",
        required=True,
        help="Generate Functional and Timing Netlists for Post Synthesis and Implementation simulation runs"
    )

    c = _cmd("synth-config", "Generate a starter hooks file for synthesis")
    c.add_argument(
        "--top",
        required=True, help="Top module name"
    ).completer = _top_names_completer

    c = _cmd("elaborate", "Compile and optionally run simulation")
    c.add_argument(
        "--top",
        required=True, help="Simulation top module"
    ).completer = _top_names_completer
    c.add_argument("--so",      default="", help="DPI shared library name (no path/extension)")
    c.add_argument("--dpi-lib", default="", help="Directory containing the DPI .so")
    c.add_argument("--run",     default="", help="Simulation run time, e.g. 1000ns")

    c = _cmd("open-dcp", "Open a checkpoint in Vivado GUI")
    c.add_argument(
        "--top",
        required=True, help="Top module name (locates build/<top>/)"
    ).completer = _top_names_completer
    c.add_argument(
        "--dcp",
        default="post_synth", help="Checkpoint stem (default: post_synth)"
    ).completer = _dcp_stems_completer

    c = _cmd("open-snapshot", "Open the simulation snapshot in xsim GUI")
    c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

    c = _cmd("reload-snapshot", "Restart simulation snapshot")
    c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

    c = _cmd("open-wdb", "Open the waveform database in xsim GUI")
    c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

    c = _cmd("reload-wdb", "Reload waveform window")
    c.add_argument("--top", required=True, help="Simulation top module").completer = _top_names_completer

    c = _cmd(
        "create-platform",
        "Generate BSP from XSA using hsi (xsct). "
        "BSP is placed in build/bsp/<platform>.",
    )
    c.add_argument(
        "--platform",
        required=True,
        help="Platform name as defined in [[platform]] TOML entry",
    ).completer = _platform_names_completer

    c = _cmd(
        "platform-build",
        "Compile the BSP with make -j<ncpu>.",
    )
    c.add_argument(
        "--platform",
        required=True,
        help="Platform name as defined in [[platform]] TOML entry",
    ).completer = _platform_names_completer

    c = _cmd(
        "create-app",
        "Scaffold an application from a Vitis template using hsi (xsct). "
        "App is placed in build/app/<app>. "
        "If the BSP does not yet exist it is created automatically.",
    )
    c.add_argument(
        "--app",
        required=True,
        help="App name as defined in [[app]] TOML entry",
    ).completer = _app_names_completer
    c.add_argument(
        "--platform", default="",
        help="Override the platform name specified in the [[app]] TOML entry",
    ).completer = _platform_names_completer
    c.add_argument(
        "--template", default="",
        help="Override the app template (e.g. 'empty_application', 'hello_world')",
    )

    c = _cmd(
        "app-build",
        "Compile the application with make -j<ncpu>.",
    )
    c.add_argument(
        "--app",
        required=True,
        help="App name as defined in [[app]] TOML entry",
    ).completer = _app_names_completer
    c.add_argument(
        "--info", action="store_true",
        help="Print ELF section sizes and headers after a successful build "
        "(uses microblaze-xilinx-elf-size and microblaze-xilinx-elf-objdump)",
    )

    c = _cmd(
        "program",
        "Download bitstream to FPGA, and optionally load an ELF. "
        "Requires hw_server running (Vivado Hardware Manager or standalone).",
    )
    bit_src = c.add_mutually_exclusive_group()
    bit_src.add_argument(
        "--bitstream", metavar="PATH",
        help="Explicit path to the .bit file to program",
    )
    bit_src.add_argument(
        "--platform", metavar="NAME",
        help="Derive bitstream path from [[platform]] TOML entry",
    ).completer = _platform_names_completer

    elf_src = c.add_mutually_exclusive_group()
    elf_src.add_argument(
        "--elf", metavar="PATH",
        help="Explicit path to the .elf file to load",
    )
    elf_src.add_argument(
        "--app", metavar="NAME",
        help="Derive ELF path from [[app]] build directory",
    ).completer = _app_names_completer

    c = _cmd(
        "processor",
        "Control the embedded MicroBlaze processor via JTAG.",
    )
    proc_action = c.add_mutually_exclusive_group(required=True)
    proc_action.add_argument(
        "--reset", action="store_true",
        help="Soft-reset the processor (rst -processor then continue)",
    )
    proc_action.add_argument(
        "--status", action="store_true",
        help="Print target list, processor state, and key registers",
    )

    c = _cmd(
        "jtag-monitor",
        "Stream debug output from the embedded processor over JTAG. "
        "Requires the MDM IP in the Vivado design with JTAG UART enabled. "
        "Press Ctrl-C to stop.",
    )
    c.add_argument(
        "--uart", action="store_true", default=True,
        help="Stream JTAG UART output to stdout (default mode)",
    )

    return p


def main() -> None:
    parser = build_parser()
    # echo 'eval "$(register-python-argcomplete xviv)"' >> ~/.zshrc
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    cfg_path = os.path.abspath(args.config)
    project_dir = os.path.dirname(cfg_path)
    os.chdir(project_dir)

    cfg = load_config(cfg_path)

    build_dir = os.path.join(project_dir, cfg.get("build", {}).get("dir", config.DEFAULT_BUILD_DIR))
    _setup_logging(args.log_file or os.path.join(build_dir, "xviv", "xviv.log"))

    tcl_script = _find_tcl_script()
    xsct_script = _find_xsct_script()
    cmd = args.command

    if cmd == "create-ip":
        if args.ip:
            build_cfg = cfg.get("build", {})
            ip_wrapper_dir = os.path.abspath(os.path.join(project_dir, build_cfg.get("wrapper_dir", config.DEFAULT_BUILD_WRAPPER_DIR)))

            ip_list = cfg.get("ip", [])
            ip_cfg = next((i for i in ip_list if i["name"] == args.ip), None)
            if ip_cfg is None:
                sys.exit(f"ERROR: IP '{args.ip}' not found in project.toml [[ip]] entries")

            if ip_cfg.get('create-wrapper', False):
                ip_rtl_files = _resolve_globs(ip_cfg.get("rtl", []), project_dir)
                ip_top = ip_cfg.get("top", ip_cfg["name"])

                wrapper.xviv_wrap_top(ip_top, ip_wrapper_dir, ip_rtl_files)

                ip_wrapper_file = os.path.join(ip_wrapper_dir, f"{ip_top}_wrapper.sv")
                if ip_wrapper_file not in ip_rtl_files:
                    ip_rtl_files.append(ip_wrapper_file)

                ip_cfg["top"] = f"{ip_top}_wrapper"
                ip_cfg["rtl"] = ip_rtl_files

        config_tcl = generate_config_tcl(cfg, project_dir, ip_name=args.ip)
        run_vivado(cfg, tcl_script, "create_ip", [], config_tcl)

    elif cmd == "edit-ip":
        config_tcl = generate_config_tcl(cfg, project_dir, ip_name=args.ip)
        run_vivado(cfg, tcl_script, "edit_ip", [], config_tcl)

    elif cmd == "ip-config":
        generate_ip_hooks(cfg, project_dir, args.ip)

    elif cmd == "create-bd":
        generate_bd_hooks(cfg, project_dir, args.bd, exist_ok=True)
        config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
        run_vivado(cfg, tcl_script, "create_bd", [], config_tcl)

    elif cmd == "edit-bd":
        config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
        run_vivado(cfg, tcl_script, "edit_bd", [], config_tcl)

    elif cmd == "generate-bd":
        config_tcl = generate_config_tcl(cfg, project_dir, bd_name=args.bd)
        run_vivado(cfg, tcl_script, "generate_bd", [], config_tcl)

    elif cmd == "export-bd":
        sha, dirty, tag = _git_sha_tag()

        bd_list = cfg.get("bd", [])
        bd_cfg = next((b for b in bd_list if b["name"] == args.bd), None)
        if bd_cfg is None:
            sys.exit(f"ERROR: BD '{args.bd}' not found in project.toml [[bd]] entries")

        export_base = bd_cfg.get("export_tcl", f"scripts/bd/{args.bd}.tcl")
        export_base = os.path.abspath(os.path.join(project_dir, export_base))
        stem = os.path.splitext(export_base)[0]
        versioned = f"{stem}_{tag}.tcl"
        symlink = export_base

        logger.info("BD export: sha=%s dirty=%s", sha, dirty)
        logger.info("BD export versioned: %s", versioned)
        logger.info("BD export symlink  : %s", symlink)

        if dirty:
            logger.warning(
                "Working tree is dirty - export tagged _dirty. "
                "Commit changes before a production export."
            )

        config_tcl = generate_config_tcl(
            cfg, project_dir,
            bd_name=args.bd,
            bd_export_path=versioned,
        )

        run_vivado(cfg, tcl_script, "export_bd", [], config_tcl)
        _strip_bd_tcl(versioned)

        _atomic_symlink(versioned, symlink)
        logger.info(
            "Symlink updated: %s -> %s",
            os.path.basename(symlink),
            os.path.basename(versioned),
        )

        print(f"Exported : {versioned}")
        print(f"Symlink  : {symlink} -> {os.path.basename(versioned)}")

    elif cmd == "bd-config":
        generate_bd_hooks(cfg, project_dir, args.bd)

    elif cmd == "synthesis":
        _, _, tag = _git_sha_tag()
        config_tcl = generate_config_tcl(cfg, project_dir, top_name=args.top)
        run_vivado(cfg, tcl_script, "synthesis", [args.top, tag], config_tcl)

    elif cmd == "synth-config":
        generate_synth_hooks(cfg, project_dir, args.top)  # noqa: F821

    elif cmd == "open-dcp":
        dcp_path = os.path.abspath(
            os.path.join(build_dir, args.top, f"{args.dcp}.dcp")
        )
        config_tcl = generate_config_tcl(cfg, project_dir)
        run_vivado(cfg, tcl_script, "open_dcp", [dcp_path], config_tcl)

    elif cmd == "elaborate":
        sim_build_dir = os.path.join(build_dir, "xviv", args.top)
        sources_cfg = cfg.get("sources", {})
        sim_files = _resolve_globs(sources_cfg.get("sim", []), project_dir)

        run_vivado_xvlog(cfg, sim_build_dir, sim_files)
        run_vivado_xelab(cfg, sim_build_dir, args.top)

        if args.run:
            x_simulate_tcl = f"""
				log_wave -recursive *
				run {args.run}
				exit
			"""
            run_vivado_xsim(cfg, sim_build_dir, args.top, x_simulate_tcl)

    elif cmd == "open-snapshot":
        open_snapshot(cfg, args.top, build_dir)

    elif cmd == "reload-snapshot":
        reload_snapshot(build_dir, args.top)

    elif cmd == "open-wdb":
        open_wdb(cfg, args.top, build_dir)

    elif cmd == "reload-wdb":
        reload_wdb(build_dir, args.top)

    elif cmd == "create-platform":
        plat_cfg = _resolve_platform_cfg(cfg, args.platform)
        xsa, _ = _platform_paths(cfg, project_dir, build_dir, plat_cfg)
        bsp = _bsp_dir(build_dir, args.platform)
        cpu = plat_cfg["cpu"]
        os_name = plat_cfg.get("os", "standalone")

        if not os.path.exists(xsa):
            sys.exit(
                f"ERROR: XSA not found: {xsa}\n"
                f"  Run 'xviv synthesis --top {plat_cfg.get('synth_top', '<top>')}' first."
            )

        logger.info("Creating BSP platform '%s'", args.platform)
        logger.info("  XSA    : %s", xsa)
        logger.info("  CPU    : %s", cpu)
        logger.info("  OS     : %s", os_name)
        logger.info("  BSP dir: %s", bsp)

        run_xsct(cfg, xsct_script, ["create_platform", xsa, cpu, os_name, bsp])

    elif cmd == "platform-build":
        plat_cfg = _resolve_platform_cfg(cfg, args.platform)
        bsp = _bsp_dir(build_dir, args.platform)

        env = _get_vitis_env(cfg)

        if not os.path.isdir(bsp):
            sys.exit(
                f"ERROR: BSP directory not found: {bsp}\n"
                f"  Run: xviv create-platform --platform {args.platform}"
            )

        logger.info("Building BSP: %s", bsp)
        subprocess.run(
            ["make", f"-j{os.cpu_count() or 4}"],
            check=True,
            cwd=bsp,
            env=env
        )
        logger.info("BSP build complete")

    elif cmd == "create-app":
        app_cfg = _resolve_app_cfg(cfg, args.app)
        plat_name = args.platform or app_cfg["platform"]
        plat_cfg = _resolve_platform_cfg(cfg, plat_name)
        xsa, _ = _platform_paths(cfg, project_dir, build_dir, plat_cfg)
        bsp = _bsp_dir(build_dir, plat_name)
        app_out_dir = _app_dir(build_dir, args.app)
        cpu = plat_cfg["cpu"]
        os_name = plat_cfg.get("os", "standalone")
        template = args.template or app_cfg.get("template", "empty_application")
        src_dir = app_cfg.get("src_dir", f"srcs/sw/{args.app}")

        if not os.path.exists(xsa):
            sys.exit(
                f"ERROR: XSA not found: {xsa}\n"
                f"  Run synthesis for platform '{plat_name}' first."
            )

        # Auto-create BSP if absent
        if not os.path.isdir(bsp):
            logger.info("BSP not found - creating platform '%s' first", plat_name)
            run_xsct(cfg, xsct_script, ["create_platform", xsa, cpu, os_name, bsp])

        logger.info("Creating app '%s' from template '%s'", args.app, template)
        logger.info("  App dir : %s", app_out_dir)

        run_xsct(cfg, xsct_script, ["create_app", xsa, cpu, os_name, template, app_out_dir])

        if not os.path.isdir(src_dir):
            logger.warning(f"src_dir not found, creating {src_dir}")

        os.makedirs(src_dir, exist_ok=True)

    elif cmd == "app-build":
        app_cfg = _resolve_app_cfg(cfg, args.app)
        plat_name = app_cfg["platform"]
        plat_cfg = _resolve_platform_cfg(cfg, plat_name)
        bsp = _bsp_dir(build_dir, plat_name)
        cpu = plat_cfg["cpu"]
        app_out_dir = _app_dir(build_dir, args.app)
        src_dir = os.path.abspath(app_cfg.get("src_dir", f"srcs/sw/{args.app}"))
        env = _get_vitis_env(cfg)

        _transform_app_makefile(os.path.join(app_out_dir, "Makefile"))

        if not os.path.isdir(app_out_dir):
            sys.exit(
                f"ERROR: App directory not found: {app_out_dir}\n"
                f"  Run: xviv create-app --app {args.app}"
            )

        bsp_include = os.path.join(bsp, cpu, "include")
        bsp_lib = os.path.join(bsp, cpu, "lib")

        c_sources = " ".join(_resolve_globs(["**/*.c"], src_dir))

        logger.info("Building app '%s'", args.app)
        subprocess.run(
            [
                "make", f"-j{os.cpu_count() or 4}",
                f"INCLUDEPATH=-I{src_dir} -I{bsp_include} -I{bsp}",
                f"c_SOURCES={c_sources}",
                f"LIBPATH=-L{bsp_lib}",
            ],
            check=True,
            cwd=app_out_dir,
            env=env
        )
        logger.info("App build complete")

        if args.info:
            elf = _find_elf(app_out_dir, args.app)
            if elf:
                logger.info("ELF: %s", elf)
                print(f"\n=== ELF size: {os.path.basename(elf)} ===")
                subprocess.run([_mb_tool(cfg, "size"), elf])
                print(f"\n=== ELF sections: {os.path.basename(elf)} ===")
                subprocess.run([_mb_tool(cfg, "objdump"), "-h", elf])
            else:
                logger.warning("No ELF found in %s", app_out_dir)

    elif cmd == "program":
        server = _hw_server(cfg)

        if args.bitstream:
            bit = os.path.abspath(args.bitstream)
        elif args.platform:
            plat_cfg = _resolve_platform_cfg(cfg, args.platform)
            _, bit = _platform_paths(cfg, project_dir, build_dir, plat_cfg)
        elif args.app:
            app_cfg = _resolve_app_cfg(cfg, args.app)
            plat_cfg = _resolve_platform_cfg(cfg, app_cfg.get("platform", None))
            _, bit = _platform_paths(cfg, project_dir, build_dir, plat_cfg)

        if not os.path.exists(bit):
            sys.exit(f"ERROR: Bitstream not found: {bit}")

        elf = ""
        if args.elf:
            elf = os.path.abspath(args.elf) or ""
            if not os.path.exists(elf):
                sys.exit(f"ERROR: ELF not found: {elf}")
        elif args.app:
            app_cfg = _resolve_app_cfg(cfg, args.app)
            app_out_dir = _app_dir(build_dir, args.app)
            elf = _find_elf(app_out_dir, args.app) or ""
            if not elf:
                sys.exit(
                    f"ERROR: No ELF found in {app_out_dir}\n"
                    f"  Run: xviv app-build --app {args.app}"
                )

        logger.info("Programming FPGA")
        logger.info("  Bitstream : %s", bit)
        if elf:
            logger.info("  ELF       : %s", elf)
        logger.info("  hw_server : %s", server)

        run_xsct(cfg, xsct_script, ["program", bit, elf or "", server])

    elif cmd == "processor":
        server = _hw_server(cfg)
        if args.reset:
            logger.info("Resetting embedded processor via JTAG (%s)", server)
            run_xsct(cfg, xsct_script, ["processor_reset", server])
        elif args.status:
            run_xsct(cfg, xsct_script, ["processor_status", server])

    elif cmd == "jtag-monitor":
        server = _hw_server(cfg)
        logger.info("Starting JTAG UART monitor (Ctrl-C to stop)")
        logger.info("  hw_server : %s", server)
        run_xsct_live(cfg, xsct_script, ["jtag_uart", server])

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
