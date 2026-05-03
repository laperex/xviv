# =============================================================================
# Command: edit_bd
# =============================================================================
proc cmd_edit_bd { gui } {
    global current_bd_design xviv_bd_name xviv_bd_dir xviv_wrapper_dir

    xviv_require_vars xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file"
    }

	if { [catch {current_project} project] } {
    	xviv_create_project "in_memory_project"

	    puts "INFO: Edit Block Design"
		puts "INFO:   Name : $xviv_bd_name"
		puts "INFO:   BD   : $bd_file"
	}

	if { [get_files -quiet $bd_file] eq "" } {
	    read_bd $bd_file
	}

	if { [catch {current_bd_design} current] || $current ne $xviv_bd_name } {
		open_bd_design $bd_file
	}

	# -------------------------------

	if {![info exists xviv_bd_state_tcl] || $xviv_bd_state_tcl eq ""} {
		save_bd_tcl
	}

	override_save_bd_design
	save_bd_design

	# override_bd_exit

	if { $gui } {
    	start_gui
	}
}