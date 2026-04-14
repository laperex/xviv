# =============================================================================
# Command: export_bd
#
# Exports the current .bd as a fully self-contained re-runnable TCL script.
# The output path (bd_export_tcl) is supplied by the Python controller
# and already encodes the git SHA tag produced by _git_sha_tag().
# Python updates the {bd_name}.tcl symlink after this proc exits.
#
# IP version strings are preserved (no -no_ip_version flag) so the exported
# TCL recreates the BD identically on any machine with a matching Vivado +
# IP installation.
# =============================================================================
proc cmd_export_bd { bd_export_tcl } {
    global xviv_bd_name xviv_bd_dir
	
    xviv_require_vars xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file\nHas create-bd been run?"
    }

    puts "INFO: Exporting Block Design - $xviv_bd_name"
    puts "INFO: Output TCL             - $bd_export_tcl"

    xviv_create_project "in_memory_project"

    read_bd        $bd_file
    open_bd_design $bd_file

    # Upgrade stale IPs before export so captured VLNV strings are current.
    set stale_cells [get_bd_cells -hierarchical -filter {TYPE == ip}]
    if {[llength $stale_cells] > 0} {
        if {[catch {upgrade_ip $stale_cells} err]} {
            puts "WARN: IP upgrade errors during export: $err"
            puts "WARN: Exported TCL may reference outdated IP versions"
        }
    }

    file mkdir [file dirname $bd_export_tcl]

    # -no_ip_version intentionally omitted: full VLNV version pins are
    # required for bit-identical BD recreation on another machine.
    write_bd_tcl -force -no_project_wrapper $bd_export_tcl
    puts "INFO: Total elapsed: [xviv_elapsed]"
    exit 0
}