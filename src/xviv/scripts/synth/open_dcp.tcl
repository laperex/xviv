# =============================================================================
# Command: open_dcp <dcp_file>
# =============================================================================
proc cmd_open_dcp {dcp_file} {
    if {![file exists $dcp_file]} {
        xviv_die "DCP file not found: $dcp_file"
    }
    puts "INFO: Opening checkpoint - $dcp_file"
    open_checkpoint $dcp_file
    start_gui
}
