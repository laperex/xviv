# =============================================================================
# Command: create_core
# =============================================================================
proc cmd_create_core { gui } {
    global xviv_core_vlnv xviv_core_name xviv_core_dir

    xviv_require_vars xviv_core_vlnv xviv_core_name xviv_core_dir

    puts "INFO: Create Core"
    puts "INFO:   VLNV : $xviv_core_vlnv"
    puts "INFO:   Name : $xviv_core_name"
    puts "INFO:   Dir  : $xviv_core_dir"

    file mkdir $xviv_core_dir
	set core_subdir [file join $xviv_core_dir $xviv_core_name]
    if {[file exists $core_subdir]} {
        puts "WARNING: Removing existing BD directory - $core_subdir"
        file delete -force $core_subdir
    }

    xviv_create_project "in_memory_project"

    set xci_file [create_ip \
        -vlnv        $xviv_core_vlnv  \
        -module_name $xviv_core_name  \
        -dir         $xviv_core_dir   \
    ]
	puts "INFO:   XCI  : $xci_file"

	if { $gui } {
		cmd_edit_core $gui
	} else {
		cmd_generate_core
	}

    puts "INFO: Core creation complete - [xviv_elapsed]"
}
