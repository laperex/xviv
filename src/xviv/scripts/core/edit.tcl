# =============================================================================
# Command: edit_core
# =============================================================================
proc cmd_edit_core { gui } {
    global current_project xviv_core_dir xviv_core_vlnv xviv_core_name xviv_core_params

    set xci_file "$xviv_core_dir/$xviv_core_name/${xviv_core_name}.xci"

	if { [catch {current_project} project] } {
		xviv_create_project "in_memory_project"

		puts "INFO: Edit Core"

		puts "INFO:   VLNV : $xviv_core_vlnv"
		puts "INFO:   Name : $xviv_core_name"
		puts "INFO:   Dir  : $xviv_core_dir"
		puts "INFO:   XCI  : $xci_file"
	}

	if { [get_files -quiet $xci_file] eq "" } {
		read_ip $xci_file
	}

	# -------------------------------

	if { $gui } {
		set current_ip [get_ips $xviv_core_name]
		set config_list [start_ip_gui -ip $current_ip]

		puts "INFO:   Changes : [expr {[llength $config_list] / 2}]"
		foreach {key val} $config_list {
			xviv_assert {[llength $val] == 1} "Expected single-element value for CONFIG.$key, got: $val"
			puts "INFO:   CONFIG.$key = [lindex $val 0]"
			set_property CONFIG.$key [lindex $val 0] $current_ip
		}

		cmd_generate_core
	}
}