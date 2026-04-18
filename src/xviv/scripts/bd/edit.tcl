# =============================================================================
# Command: edit_bd
# =============================================================================
proc cmd_edit_bd { gui } {
    global xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

    xviv_require_vars xviv_bd_name xviv_bd_dir xviv_bd_state_tcl

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file\nHas create-bd been run?"
    }

    puts "INFO: Editing Block Design - $xviv_bd_name"
    xviv_create_project "in_memory_project"

    add_files      $bd_file
    open_bd_design $bd_file

	if {![info exists xviv_bd_state_tcl] || $xviv_bd_state_tcl eq ""} {
		save_bd_tcl
	}

	override_save_bd_design
	save_bd_design

	if { $gui } {
    	start_gui
	}
}