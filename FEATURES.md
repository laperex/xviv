- find use for export_bd

- change config synth:
	old: xviv config --synth -> generates synth config for top module only 
	new: xviv config --synth (--bd <bd_name> | --ip <ip_name> | --top <top_name>) -> generates synth config for all targets

- project guide in search core
	link to project guide - html / pdf as a column in xviv search <query>
	
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