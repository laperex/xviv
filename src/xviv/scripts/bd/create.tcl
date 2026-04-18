# =============================================================================
# Command: create_bd
# =============================================================================
proc cmd_create_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

    xviv_require_vars xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

    xviv_stub bd_design_config

	set bd_subdir [file join $xviv_bd_dir $xviv_bd_name]
    if {[file exists $bd_subdir]} {
        puts "WARNING: Removing existing BD directory - $bd_subdir"
        file delete -force $bd_subdir
    }

    file mkdir $xviv_bd_dir

    puts "INFO: Creating Block Design - $xviv_bd_name"
    puts "INFO: Output directory      - $xviv_bd_dir"

    xviv_create_project "in_memory_project"
    create_bd_design -dir $xviv_bd_dir $xviv_bd_name

	if {[file exists $xviv_bd_state_tcl]} {
		puts "INFO: Importing Block Design: $xviv_bd_state_tcl"

    	source $xviv_bd_state_tcl

		xviv_refresh_bd_addresses
		validate_bd_design
		save_bd_design
	} else {
		puts "INFO: BD hooks not found. Starting GUI..."
		puts "INFO: Tip: Save your design with 'xviv export --bd <bd_name>'."
		puts "INFO: Tip: Enable automation with 'xviv config --bd <bd_name>'."

		override_save_bd_design
		start_gui
	}
}