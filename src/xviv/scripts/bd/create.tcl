# =============================================================================
# Command: create_bd
# =============================================================================
proc cmd_create_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_bd_hooks

    xviv_require_vars xviv_bd_name xviv_bd_dir

    xviv_stub bd_design_config
    xviv_source_hooks xviv_bd_hooks

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
    bd_design_config ""
}