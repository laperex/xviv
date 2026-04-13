# =============================================================================
# Command: edit_ip
# =============================================================================
proc cmd_edit_ip {} {
    global xviv_ip_name xviv_ip_version xviv_ip_repo

    xviv_require_vars xviv_ip_name xviv_ip_version xviv_ip_repo

    # set ip_vid    "${xviv_ip_name}_[string map {. _} $xviv_ip_version]"
	set ip_vid    "${xviv_ip_name}"
    set ip_dir    "$xviv_ip_repo/$ip_vid"
    set proj_root "/dev/shm/build"

    if {![file exists "$ip_dir/component.xml"]} {
        xviv_die "IP not found at $ip_dir/component.xml - has create-ip been run?"
    }

    file mkdir $proj_root
    xviv_create_project "in_memory_project"
    start_gui
    ipx::edit_ip_in_project -upgrade true -name "edit_$ip_vid" -directory "$proj_root/$ip_vid" "$ip_dir/component.xml"
    current_project "in_memory_project"
    close_project
    current_project "edit_$ip_vid"
}