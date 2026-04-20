# =============================================================================
# Command: generate_bd
# =============================================================================
proc cmd_generate_bd {} {
    global current_bd_design xviv_bd_name xviv_bd_dir xviv_wrapper_dir

    xviv_require_vars xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"
	set bd_mtime [file mtime $bd_file]
    set wrapper "$xviv_wrapper_dir/${xviv_bd_name}_wrapper.v"

    if { [file exists $wrapper] } {
        if { $bd_mtime < [file mtime $wrapper] } {
			puts "INFO: Output products are up to date"

			return
        }
    }

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file"
    }

	if { [catch {current_project} project] } {
    	xviv_create_project "in_memory_project"

	    puts "INFO: Generate Block Design"
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

	xviv_stage "Upgrade stale IPs"
    set stale_cells [get_bd_cells -hierarchical -filter {TYPE == ip}]
	if {[llength $stale_cells] > 0} {
		if {[catch {upgrade_ip $stale_cells} err]} {
			xviv_die "IP upgrade failed during generate_bd: $err";
		}
	}

	xviv_stage "Generating output products"
    reset_target all [get_files $bd_file]
    generate_target all [get_files $bd_file]

	xviv_stage "Validate design"
	validate_bd_design

	xviv_stage "Make wrapper"
    set wrapper_src [make_wrapper -files [get_files $bd_file] -top]
    if {[info exists xviv_wrapper_dir] && $xviv_wrapper_dir ne ""} {
        file mkdir $xviv_wrapper_dir

        file copy -force $wrapper_src $xviv_wrapper_dir
        puts "INFO: BD wrapper copied to $xviv_wrapper_dir/${xviv_bd_name}_wrapper.v"
    }

    puts "INFO: Generate BD complete - [xviv_elapsed]"
}