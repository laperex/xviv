- core
	- use in synth

- synth add debug marking

- project guide in search core
	link to project guide - html / pdf as a column in xviv search <query>

- package ip that uses another ip core internally.
	- Declare clk_wiz as a sub-core so downstream users know they need it
	ipx::add_subcore xilinx.com:ip:clk_wiz:6.0 [ipx::get_file_groups xilinx_verilogsynthesis -of $ip_core]

	- Include the XCI so the IP packager carries it
	ipx::add_file ip/clk_wiz_0/clk_wiz_0.xci $synth_fs
	set_property type xci [ipx::get_files ip/clk_wiz_0/clk_wiz_0.xci -of $synth_fs]

- search changes in syntax
	old: xviv search <query>
	new: xviv search --core <query>

- testing repo that tests all features. 

	- <parallel>[cmd_ip_create <ip_name>] -> cmd_bd_create [from exported tcl in scripts/bd/exported/<bd_name>.tcl] -> cmd_bd_generate -> cmd_bd_synth <bd_name> -> cmd_platform_create -> cmd_platform_build -> cmd_app_create<template=hello_world> -> cmd_app_build
		- fpga: xc7a200tfbg484-1
		- microblaze ip test with custom ip
		- ip's defined in .toml
		- bd define in toml
		- synth options defined in toml <bd_name>
		- platform create

	- <parallel>[cmd_ip_create <ip_name>] -> cmd_bd_create [from exported tcl in scripts/bd/exported/<bd_name>.tcl] -> cmd_bd_generate -> cmd_bd_synth <bd_name> -> cmd_platform_create -> cmd_platform_build -> cmd_app_create<template=hello_world> -> cmd_app_build
		- microblaze ip test with custom ip
		- ip's defined in .toml
		- bd define in toml
		- synth options defined in toml <bd_name>
		- platform create

	cmd_core_create
	cmd_search_core
	cmd_ip_edit
	cmd_bd_edit
	cmd_ip_config
	cmd_bd_config
	cmd_top_config
	cmd_bd_generate
	cmd_bd_export
	cmd_ip_synth
	cmd_bd_synth
	cmd_top_synth
	cmd_dcp_open
	cmd_snapshot_open
	cmd_wdb_open
	cmd_top_elaborate
	cmd_top_simulate
	cmd_snapshot_reload
	cmd_wdb_reload
	cmd_platform_build
	cmd_app_build
	cmd_program
	cmd_processor

- add debug cores. 

	```TCL
	rename exit _original_exit
	proc exit {args} {
		write_xdc -type misc -force ./test_constraints_test_exit.xdc

		_original_exit {*}$args
	}
	```



def cmd_status(cfg: XvivConfig) -> None:
    rows = []

    for synth in cfg._synth_list:
        name = synth.design_name or synth.bd_name
        bit  = synth.bitstream_file
        rows.append((
            'synth', name,
            '✓' if bit and os.path.exists(bit) else '✗',
            _mtime_str(bit)
        ))

    for sim in cfg._sim_list:
        wdb = os.path.join(sim.work_dir, f'{sim.top}.wdb')
        rows.append((
            'sim', sim.name,
            '✓' if os.path.exists(wdb) else '?',
            _mtime_str(wdb)
        ))

    # Print as aligned table
    for kind, name, status, mtime in rows:
        print(f'{status}  {kind:8s}  {name:30s}  {mtime}')

def cmd_lint(cfg: XvivConfig, *, design_name: str) -> None:
    design_cfg = cfg.get_design(design_name)

    ys_script = '\n'.join([
        *[f'read_verilog -sv {s}' for s in design_cfg.sources],
        f'hierarchy -check -top {design_cfg.top}',
        'proc',
        'opt_clean',
        'check',   # reports multi-driven signals, unconnected ports, etc.
    ])

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False) as f:
        f.write(ys_script)
        ys_path = f.name

    subprocess.run(['yosys', '-s', ys_path], check=True)

def cmd_estimate(cfg: XvivConfig, *, design_name: str) -> None:
    design_cfg = cfg.get_design(design_name)

    ys_script = '\n'.join([
        *[f'read_verilog -sv {s}' for s in design_cfg.sources],
        f'hierarchy -top {design_cfg.top}',
        'proc; opt; techmap',
        'stat',    # prints LUT/FF/memory estimates
    ])
    ...

def cmd_validate(cfg: XvivConfig) -> None:
    errors = []

    # Check all source files exist
    for design in cfg._design_list:
        for src in design.sources:
            if not os.path.exists(src):
                errors.append(f'[design/{design.name}] source missing: {src}')

    # Check formal targets reference valid designs
    for formal in cfg._formal_list:
        if formal.design_ref and cfg._get_design_cfg_optional(formal.design_ref) is None:
            errors.append(f'[formal/{formal.name}] design ref not found: {formal.design_ref}')

    # Check synth constraints exist
    for synth in cfg._synth_list:
        for c in synth.constraints:
            if not os.path.exists(c):
                errors.append(f'[synth/{synth.top}] constraint missing: {c}')

    if errors:
        for e in errors:
            print(f'ERROR: {e}')
        raise SystemExit(1)

    print(f'OK: {len(cfg._design_list)} designs, '
          f'{len(cfg._formal_list)} formal targets, '
          f'{len(cfg._synth_list)} synth runs — all valid')

def cmd_clean(cfg: XvivConfig, *, target: str | None, all: bool) -> None:
    import shutil

    if all:
        shutil.rmtree(cfg.work_dir, ignore_errors=True)
        print(f'Removed: {cfg.work_dir}')
        return

    if target:
        # Clean just one target's output
        for formal in cfg._formal_list:
            if formal.name == target:
                shutil.rmtree(formal.work_dir, ignore_errors=True)
                return
        for synth in cfg._synth_list:
            name = synth.design_name or synth.bd_name
            if name == target:
                shutil.rmtree(os.path.join(cfg.synth_dir, name), ignore_errors=True)
                return

def cmd_formal_coverage(cfg, *, formal_name: str) -> None:
    formal_cfg = cfg.get_formal(formal_name)
    cover_dir  = os.path.join(formal_cfg.work_dir, 'engine_0')

    # sby writes one trace per cover point
    traces = glob.glob(os.path.join(cover_dir, 'trace*.vcd'))

    print(f'\n=== Cover Results: {formal_name} ===')
    print(f'  Reachable cover points: {len(traces)}')
    for t in traces:
        print(f'  ✓ {os.path.basename(t)}')

    # Check for unreachable (sby logs these as FAILED COVER)
    log = os.path.join(formal_cfg.work_dir, 'logfile.txt')
    if os.path.exists(log):
        with open(log) as f:
            for line in f:
                if 'FAILED' in line and 'cover' in line.lower():
                    print(f'  ✗ {line.strip()}')

def cmd_formal_run_all(cfg: XvivConfig) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    targets  = cfg._formal_list
    status   = {f.name: 'RUNNING' for f in targets}

    def _run(formal_cfg):
        try:
            _run_formal(cfg, formal_cfg)
            status[formal_cfg.name] = 'PASS'
        except SystemExit:
            status[formal_cfg.name] = 'FAIL'

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {pool.submit(_run, f): f for f in targets}

        for fut in as_completed(futures):
            formal_cfg = futures[fut]
            icon = '✓' if status[formal_cfg.name] == 'PASS' else '✗'
            print(f'\r{icon} {formal_cfg.name:30s} {status[formal_cfg.name]}')