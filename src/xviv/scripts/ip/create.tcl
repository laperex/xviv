# =============================================================================
# Command: create_ip
# =============================================================================
proc cmd_create_ip {} {
    global xviv_ip_name xviv_ip_vendor xviv_ip_library xviv_ip_version
    global xviv_ip_top xviv_ip_rtl xviv_ip_hooks  xviv_ip_repo

    xviv_require_vars xviv_ip_name xviv_ip_vendor xviv_ip_library xviv_ip_version xviv_ip_repo

    set ip_id     "$xviv_ip_vendor:$xviv_ip_library:$xviv_ip_name:$xviv_ip_version"
    set ip_vid    "${xviv_ip_name}_[string map {. _} $xviv_ip_version]"
    set ip_dir    "$xviv_ip_repo/$ip_vid"
    set proj_root "/dev/shm/build"

    file mkdir $xviv_ip_repo
    file mkdir $proj_root

    foreach stub {
        ipx_add_files
        ipx_merge_changes
        ipx_infer_bus_interfaces
        ipx_add_params
        ipx_add_memory_map
    } { xviv_stub $stub }

    xviv_source_hooks xviv_ip_hooks
    xviv_create_project "in_memory_project"

    xviv_stage "Scaffolding IP skeleton - $ip_vid"
    _xviv_ip_scaffold $ip_id $ip_vid $ip_dir $proj_root

    xviv_stage "Stripping default AXI-Lite scaffold"
    _xviv_ip_strip_scaffold

    xviv_stage "Adding RTL sources"

	add_files -norecurse -scan_for_includes $xviv_ip_rtl
	set_property TOP $xviv_ip_top [current_fileset]

    ipx_add_files
    update_compile_order -fileset sources_1
    ipx::merge_project_changes ports [ipx::current_core]
    ipx::merge_project_changes files [ipx::current_core]
    ipx_merge_changes
    update_compile_order -fileset sources_1

    xviv_stage "Inferring bus interfaces"
    _xviv_ip_infer_interfaces

    xviv_stage "Exposing HDL parameters"
    _xviv_ip_expose_params

    xviv_stage "Wiring AXI-Lite memory maps"
    _xviv_ip_wire_memory_maps

    xviv_stage "Finalising and saving IP"
    _xviv_ip_finalise $ip_vid

    puts "INFO: IP creation complete - [xviv_elapsed]"
    exit 0
}
