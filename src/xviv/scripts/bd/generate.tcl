# =============================================================================
# Command: generate_bd
# =============================================================================
proc cmd_generate_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_wrapper_dir

    xviv_require_vars xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file\nHas create-bd been run?"
    }

    puts "INFO: Generating Block Design output products - $xviv_bd_name"
    xviv_create_project "in_memory_project"

    read_bd        $bd_file
    open_bd_design $bd_file

    # Upgrade stale IPs with a catch so a single failed upgrade does not abort
    # the entire generation run.  The user is warned to verify manually.
    set stale_cells [get_bd_cells -hierarchical -filter {TYPE == ip}]
	if {[llength $stale_cells] > 0} {
		if {[catch {upgrade_ip $stale_cells} err]} {
			xviv_die "IP upgrade failed during generate_bd: $err";
		}
	}

	# replace with a different techinque
    reset_target  {synthesis simulation implementation} [get_files $bd_file]
    generate_target all                                 [get_files $bd_file]

	validate_bd_design

    set wrapper_src [make_wrapper -files [get_files $bd_file] -top]

    if {[info exists xviv_wrapper_dir] && $xviv_wrapper_dir ne ""} {
        file mkdir $xviv_wrapper_dir
        # Use TCL file copy instead of exec cp for portability
        file copy -force $wrapper_src $xviv_wrapper_dir
        puts "INFO: BD wrapper copied to $xviv_wrapper_dir/${xviv_bd_name}_wrapper.v"
    }

    puts "INFO: BD generation complete - [xviv_elapsed]"
    exit 0
}