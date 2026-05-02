# =============================================================================
# Command: create_bd
# =============================================================================
proc cmd_create_bd {} {
	global xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

	xviv_require_vars xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

	puts "INFO: Create Block Design"
	puts "INFO:   Name : $xviv_bd_name"
	puts "INFO:   Dir  : $xviv_bd_dir"

	file mkdir $xviv_bd_dir
	set bd_subdir [file join $xviv_bd_dir $xviv_bd_name]
	if {[file exists $bd_subdir]} {
		puts "WARNING: Removing existing BD directory - $bd_subdir"
		file delete -force $bd_subdir
	}

	xviv_create_project "in_memory_project"

	set bd_file [create_bd_design -dir $xviv_bd_dir $xviv_bd_name]
	puts "INFO:   BD   : $bd_file"

	if {[file exists $xviv_bd_state_tcl]} {
		puts "INFO: Importing Block Design: $xviv_bd_state_tcl"

		set parentCell ""

		source $xviv_bd_state_tcl

		xviv_refresh_bd_addresses
		validate_bd_design
		save_bd_design
		
		cmd_generate_bd
	} else {
		puts "INFO: BD hooks not found. Starting Edit GUI..."

		override_save_bd_design
		start_gui
	}

	puts "INFO: Create BD complete - [xviv_elapsed]"
}