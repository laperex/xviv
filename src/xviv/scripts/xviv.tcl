# =============================================================================
# scripts/xviv.tcl  -  Unified Vivado TCL dispatcher
#
# Invoked exclusively by the Python controller (xviv).  Do not call directly.
#
# Usage:
#   vivado -mode (batch|tcl) -nolog -nojournal -notrace -quiet \
#          -source scripts/xviv.tcl \
#          -tclargs <command> <generated_config.tcl> [extra args...]
#
# Commands:
#   create_ip                          - scaffold + customise a new IP
#   edit_ip                            - open an existing IP for editing
#   create_bd                          - create a new Block Design
#   edit_bd                            - open an existing BD in the GUI
#   generate_bd                        - generate BD output products + wrapper
#   synthesis    <top_module>          - synth -> place -> route -> bitstream
#   simulate     <sim_top> [so] [dpi]  - launch Vivado simulation
#   open_dcp     <dcp_file>            - open a checkpoint in the GUI
# =============================================================================

if {$::argc < 2} {
    puts stderr "ERROR: Usage: vivado ... -source xviv.tcl -tclargs <command> <config.tcl> \[extra\]"
    exit 1
}

set _cmd        [lindex $::argv 0]
set _config_tcl [lindex $::argv 1]

if {![file exists $_config_tcl]} {
    puts stderr "ERROR: Config file not found: $_config_tcl"
    exit 1
}

source $_config_tcl

# =============================================================================
# Shared utilities
# =============================================================================

# Create an in-memory Vivado project.
# board_part is optional: if xviv_board_part is empty the proc skips it.
proc xviv_create_project {name} {
    global xviv_fpga_part xviv_board_part xviv_board_repo xviv_ip_repo

    create_project -in_memory $name

    if {[info exists xviv_board_part] && $xviv_board_part ne ""} {
        if {[info exists xviv_board_repo] && $xviv_board_repo ne ""} {
            set_param board.repoPaths [list $xviv_board_repo]
        }
        set_property board_part $xviv_board_part [current_project]
    }

    set_part $xviv_fpga_part
    set_property ip_repo_paths [list $xviv_ip_repo] [current_project]
    update_ip_catalog -rebuild
}

# Add RTL + wrapper sources to sources_1, constraints to constrs_1
proc xviv_add_rtl_sources {} {
    global xviv_rtl_files xviv_wrapper_files xviv_constr_files

    if {[info exists xviv_rtl_files]     && [llength $xviv_rtl_files]     > 0} {
        add_files $xviv_rtl_files
    }
    if {[info exists xviv_wrapper_files] && [llength $xviv_wrapper_files] > 0} {
        add_files $xviv_wrapper_files
    }
    if {[info exists xviv_constr_files]  && [llength $xviv_constr_files]  > 0} {
        add_files -fileset constrs_1 $xviv_constr_files
    }
    update_compile_order -fileset sources_1
}

# Add sim sources to sim_1
proc xviv_add_sim_sources {} {
    global xviv_sim_files

    if {[info exists xviv_sim_files] && [llength $xviv_sim_files] > 0} {
        foreach f $xviv_sim_files {
            add_files -fileset sim_1 $f
        }
    }
    update_compile_order -fileset sim_1
}

# Refresh BD address segments
proc xviv_refresh_bd_addresses {} {
    delete_bd_objs [get_bd_addr_segs] [get_bd_addr_segs -excluded]
    assign_bd_address
}

# Source an optional hook file; silently skip if the variable is empty/missing
proc xviv_source_hooks {var_name} {
    upvar $var_name hooks_file
    if {[info exists hooks_file] && $hooks_file ne "" && [file exists $hooks_file]} {
        puts "INFO: Sourcing hooks - $hooks_file"
        source $hooks_file
    }
}

# Define a no-op stub for a proc only if it is not already defined.
# Call this before sourcing a hooks file so missing procs never cause crashes.
proc xviv_stub {name} {
    if {[info procs $name] eq ""} {
        proc $name {} {}
    }
}

# =============================================================================
# Command: create_ip
# =============================================================================
proc cmd_create_ip {} {
    global xviv_ip_name xviv_ip_vendor xviv_ip_library xviv_ip_version
    global xviv_ip_top  xviv_ip_hooks  xviv_ip_repo

    set ip_id    "$xviv_ip_vendor:$xviv_ip_library:$xviv_ip_name:$xviv_ip_version"
    set ip_vid   "${xviv_ip_name}_[string map {. _} $xviv_ip_version]"
    set ip_dir   "$xviv_ip_repo/$ip_vid"
    set proj_root "/dev/shm/build"

    file mkdir $xviv_ip_repo
    file mkdir $proj_root

    # Define no-op stubs so hooks file is always optional
    foreach stub {
        ipx_add_files
        ipx_merge_changes
        ipx_infer_bus_interfaces
        ipx_add_params
        ipx_add_memory_map
    } { xviv_stub $stub }

    # Source hooks - any defined proc above will be overridden
    xviv_source_hooks xviv_ip_hooks

    xviv_create_project "in_memory_project"

    # ------------------------------------------------------------------
    # 1. Scaffold the IP skeleton
    # ------------------------------------------------------------------
    create_peripheral $xviv_ip_vendor $xviv_ip_library $xviv_ip_name \
        $xviv_ip_version -dir $xviv_ip_repo
    add_peripheral_interface S00_AXI \
        -interface_mode slave -axi_type lite [ipx::find_open_core $ip_id]
    generate_peripheral -driver [ipx::find_open_core $ip_id] -force
    write_peripheral    [ipx::find_open_core $ip_id]

    ipx::edit_ip_in_project -upgrade true -name "edit_$ip_vid" \
        -directory "$proj_root/$ip_vid" "$ip_dir/component.xml"
    current_project "in_memory_project"
    close_project
    current_project "edit_$ip_vid"

    # ------------------------------------------------------------------
    # 2. Strip the default AXI-Lite scaffold
    # ------------------------------------------------------------------
    foreach ifc {S00_AXI S00_AXI_RST S00_AXI_CLK} {
        catch { ipx::remove_bus_interface $ifc [ipx::current_core] }
    }
    catch { ipx::remove_memory_map        S00_AXI            [ipx::current_core] }
    catch { ipx::remove_user_parameter    C_S00_AXI_BASEADDR [ipx::current_core] }
    catch { ipx::remove_user_parameter    C_S00_AXI_HIGHADDR [ipx::current_core] }

    foreach f [get_files -filter {FILE_TYPE == Verilog}] {
        remove_files $f
        file delete -force $f
    }

    # ------------------------------------------------------------------
    # 3. Hook: add the real RTL sources
    # ------------------------------------------------------------------
    ipx_add_files
    update_compile_order -fileset sources_1

    ipx::merge_project_changes ports [ipx::current_core]
    ipx::merge_project_changes files [ipx::current_core]

    ipx_merge_changes
    update_compile_order -fileset sources_1

    # ------------------------------------------------------------------
    # 4. Infer standard bus interfaces
    # ------------------------------------------------------------------
    puts "INFO: Inferring AXI-Stream interfaces"
    ipx::infer_bus_interfaces \
        xilinx.com:interface:axis_rtl:1.0  [ipx::current_core]
    puts "INFO: Inferring AXI-MM interfaces"
    ipx::infer_bus_interfaces \
        xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]

    ipx_infer_bus_interfaces
    update_compile_order -fileset sources_1

    # ------------------------------------------------------------------
    # 5. Expose HDL parameters in the IP GUI
    # ------------------------------------------------------------------
    foreach param [ipx::get_hdl_parameters -of_objects [ipx::current_core]] {
        set pname [get_property NAME $param]
        ipgui::add_param -name $pname -component [ipx::current_core] \
            -parent [ipgui::get_pagespec \
                -name "Page 0" -component [ipx::current_core]]
    }

    ipx_add_params

    # ------------------------------------------------------------------
    # 6. Wire memory maps for AXI-Lite slave interfaces
    # ------------------------------------------------------------------
    foreach ifc [ipx::get_bus_interfaces -of_objects [ipx::current_core]] {
        set ifc_name [get_property NAME $ifc]
        set ifc_mode [get_property BUS_TYPE_NAME $ifc]
        set ifc_intf [get_property INTERFACE_MODE $ifc]
        puts "INFO: Bus IF  $ifc_name \[$ifc_intf\]: $ifc_mode"

        if {$ifc_intf eq "slave" && [string match *axi_lite* $ifc_mode]} {
            ipx::add_memory_map "$ifc_name" [ipx::current_core]
            set ab [ipx::add_address_block "${ifc_name}_reg" \
                [ipx::get_memory_maps "$ifc_name" \
                    -of_objects [ipx::current_core]]]
            ipx::add_address_block_parameter OFFSET_BASE_PARAM $ab
            ipx::add_address_block_parameter OFFSET_HIGH_PARAM $ab
            set_property usage register $ab
            set_property slave_memory_map_ref "$ifc_name" \
                [ipx::get_bus_interfaces "$ifc_name" \
                    -of_objects [ipx::current_core]]
        }
    }

    ipx_add_memory_map
    update_compile_order -fileset sources_1

    # ------------------------------------------------------------------
    # 7. Finalise and save
    # ------------------------------------------------------------------
    set_property core_revision 2 [ipx::current_core]
    ipx::update_source_project_archive -component [ipx::current_core]
    ipx::create_xgui_files  [ipx::current_core]
    ipx::update_checksums   [ipx::current_core]
    ipx::check_integrity    [ipx::current_core]
    ipx::save_core          [ipx::current_core]

    puts "INFO: IP creation successful - $ip_vid"
    exit 0
}

# =============================================================================
# Command: edit_ip
# =============================================================================
proc cmd_edit_ip {} {
    global xviv_ip_name xviv_ip_version xviv_ip_repo

    set ip_vid    "${xviv_ip_name}_[string map {. _} $xviv_ip_version]"
    set ip_dir    "$xviv_ip_repo/$ip_vid"
    set proj_root "/dev/shm/build"

    file mkdir $proj_root
    xviv_create_project "in_memory_project"
    start_gui
    ipx::edit_ip_in_project -upgrade true -name "edit_$ip_vid" \
        -directory "$proj_root/$ip_vid" "$ip_dir/component.xml"
    current_project "in_memory_project"
    close_project
    current_project "edit_$ip_vid"
}

# =============================================================================
# Command: create_bd
# =============================================================================
proc cmd_create_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_bd_hooks

    xviv_stub bd_design_config

    xviv_source_hooks xviv_bd_hooks

    file mkdir $xviv_bd_dir

    puts "INFO: Creating Block Design - $xviv_bd_name"
    puts "INFO: Output directory      - $xviv_bd_dir"

    xviv_create_project "in_memory_project"

    create_bd_design -dir $xviv_bd_dir $xviv_bd_name

    bd_design_config ""
}

# =============================================================================
# Command: edit_bd
# =============================================================================
proc cmd_edit_bd {} {
    global xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        puts stderr "ERROR: BD file not found - $bd_file"
        exit 1
    }

    puts "INFO: Editing Block Design - $xviv_bd_name"
    xviv_create_project "in_memory_project"
    start_gui
    add_files      $bd_file
    open_bd_design $bd_file
}

# =============================================================================
# Command: generate_bd
# =============================================================================
proc cmd_generate_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_wrapper_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        puts stderr "ERROR: BD file not found - $bd_file"
        exit 1
    }

    puts "INFO: Generating Block Design output products - $xviv_bd_name"
    xviv_create_project "in_memory_project"

    read_bd        $bd_file
    open_bd_design $bd_file
    upgrade_ip [get_bd_cells -hierarchical -filter {TYPE == ip}]
    reset_target  {synthesis simulation implementation} [get_files $bd_file]
    generate_target all                                 [get_files $bd_file]

    set wrapper_src [make_wrapper -files [get_files $bd_file] -top]

    if {[info exists xviv_wrapper_dir] && $xviv_wrapper_dir ne ""} {
        file mkdir $xviv_wrapper_dir
        exec cp $wrapper_src $xviv_wrapper_dir
        puts "INFO: BD wrapper copied to $xviv_wrapper_dir"
    }

    exit 0
}

# =============================================================================
# Command: synthesis <top_module>
# =============================================================================
proc cmd_synthesis {top_module} {
    global xviv_bd_dir xviv_build_dir xviv_synth_hooks

    set out_dir     "$xviv_build_dir/$top_module"
    set report_dir  "$out_dir/reports"
    set netlist_dir "$out_dir/netlists"

	# short SHA (7 hex digits = 28 bits)
	set sha_short [exec git rev-parse --short=7 HEAD]

	# uncommitted changes (dirty flag)
	set dirty 0
	catch {
		set status [exec git status --porcelain]
		if {[string length $status] > 0} {
			set dirty 1
		}
	}

	# Pack into 32 bits: bit 31 = dirty, bits 27:0 = SHA (7 hex digits)
	set usr_access_val [format "%s%07s" $dirty $sha_short]


    file mkdir $out_dir
    file mkdir $report_dir
    file mkdir $netlist_dir

    # Lifecycle stubs
    foreach stub {
        synth_pre
        synth_post
        place_post
        route_post
        bitstream_post
    } { xviv_stub $stub }

    # Report flag stubs - all default to enabled (return 1)
    foreach flag {
        report_synth
        report_place
        report_route
        report_netlists
    } {
        if {[info procs $flag] eq ""} {
            proc $flag {} { return 1 }
        }
    }

    xviv_source_hooks xviv_synth_hooks

    xviv_create_project "in_memory_project"

    set bd_files [glob -nocomplain "$xviv_bd_dir/*/*.bd"]
    if {[llength $bd_files] > 0} { read_bd $bd_files }

    xviv_add_rtl_sources

    synth_pre

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    puts "INFO: Synthesis - $top_module"
    synth_design -name synth_${top_module} -top $top_module
    write_checkpoint -force "$out_dir/post_synth.dcp"

    if {[report_synth]} {
        puts "INFO: Post-synthesis reports"
        report_timing_summary -file "$report_dir/post_synth_timing_summary.rpt"
        report_utilization    -file "$report_dir/post_synth_util.rpt"
    }
    if {[report_netlists]} {
        write_verilog -force -mode funcsim                "$netlist_dir/post_synth_functional.v"
        write_verilog -force -mode timesim -sdf_anno true "$netlist_dir/post_synth_timing.v"
    }

    synth_post

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------
    puts "INFO: Placement"
    place_design
    write_checkpoint -force "$out_dir/post_place.dcp"

    if {[report_place]} {
        puts "INFO: Post-placement reports"
        report_io                    -file "$report_dir/post_place_io.rpt"
        report_clock_utilization     -file "$report_dir/post_place_clock_util.rpt"
        report_utilization -hierarchical -file "$report_dir/post_place_util_hier.rpt"
    }

    place_post

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    puts "INFO: Routing"
    route_design
    write_checkpoint -force "$out_dir/post_route.dcp"

    if {[report_route]} {
        puts "INFO: Post-routing reports"
        report_drc            -file "$report_dir/post_route_drc.rpt"
        report_methodology    -file "$report_dir/post_route_methodology.rpt"
        report_power          -file "$report_dir/post_route_power.rpt"
        report_route_status   -file "$report_dir/post_route_status.rpt"
        report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation \
                              -file "$report_dir/post_route_timing_summary.rpt"
    }
    if {[report_netlists]} {
        write_verilog -force -mode funcsim                "$netlist_dir/post_impl_functional.v"
        write_verilog -force -mode timesim -sdf_anno true "$netlist_dir/post_impl_timing.v"
    }

    route_post

	set_property BITSTREAM.CONFIG.USR_ACCESS 0x${usr_access_val} [current_design]

	puts "USR_ACCESS set to: 0x${usr_access_val} (dirty=${dirty}, sha=${sha_short})"

    # ------------------------------------------------------------------
    # Bitstream + XSA
    # ------------------------------------------------------------------
    puts "INFO: Generating bitstream"
    write_bitstream -force "$out_dir/${top_module}_${dirty}_${sha_short}.bit"
    puts "INFO: Generating XSA platform"
    write_hw_platform -fixed -include_bit -force -file "$out_dir/${top_module}_${dirty}_${sha_short}.xsa"

    bitstream_post

    exit 0
}

# =============================================================================
# Command: simulate <sim_top> [so_file] [dpi_lib_dir]
# =============================================================================
proc cmd_simulate {sim_top so_file dpi_lib_dir} {
    global xviv_fpga_part xviv_board_part xviv_board_repo
    global xviv_ip_repo   xviv_bd_dir

    set proj_dir "/dev/shm/build"

    create_project "in_memory_sim" $proj_dir -force -part $xviv_fpga_part

    if {[info exists xviv_board_part] && $xviv_board_part ne ""} {
        if {[info exists xviv_board_repo] && $xviv_board_repo ne ""} {
            set_param board.repoPaths [list $xviv_board_repo]
        }
        set_property board_part $xviv_board_part [current_project]
    }

    set_property ip_repo_paths [list $xviv_ip_repo] [current_project]
    update_ip_catalog -rebuild

    set bd_files [glob -nocomplain "$xviv_bd_dir/*/*.bd"]
    if {[llength $bd_files] > 0} { read_bd $bd_files }

    xviv_add_rtl_sources
    xviv_add_sim_sources

    set_property top       $sim_top       [get_filesets sim_1]
    set_property top_lib   xil_defaultlib [get_filesets sim_1]
    update_compile_order -fileset sim_1

    set_property xsim.simulate.runtime 7000ns [current_fileset -simset]

    if {$so_file ne "" && $dpi_lib_dir ne ""} {
        set_property -name {xsim.elaborate.xelab.more_options} \
            -value "-sv_lib $so_file --sv_root $dpi_lib_dir" \
            -objects [get_filesets sim_1]
    }

    launch_simulation
}

# =============================================================================
# Command: open_dcp <dcp_file>
# =============================================================================
proc cmd_open_dcp {dcp_file} {
    if {![file exists $dcp_file]} {
        puts stderr "ERROR: DCP not found - $dcp_file"
        exit 1
    }
    puts "INFO: Opening checkpoint - $dcp_file"
    open_checkpoint $dcp_file
    start_gui
}

# =============================================================================
# Dispatch
# =============================================================================
switch -- $_cmd {
    create_ip   { cmd_create_ip }
    edit_ip     { cmd_edit_ip   }
    create_bd   { cmd_create_bd }
    edit_bd     { cmd_edit_bd   }
    generate_bd { cmd_generate_bd }
    synthesis   {
        if {$::argc < 3} {
            puts stderr "ERROR: synthesis requires <top_module>"
            exit 1
        }
        cmd_synthesis [lindex $::argv 2]
    }
    simulate    {
        if {$::argc < 3} {
            puts stderr "ERROR: simulate requires <sim_top>"
            exit 1
        }
        set _sim_top  [lindex $::argv 2]
        set _so_file  [expr {$::argc > 3 ? [lindex $::argv 3] : ""}]
        set _dpi_lib  [expr {$::argc > 4 ? [lindex $::argv 4] : ""}]
        cmd_simulate $_sim_top $_so_file $_dpi_lib
    }
    open_dcp    {
        if {$::argc < 3} {
            puts stderr "ERROR: open_dcp requires <dcp_file>"
            exit 1
        }
        cmd_open_dcp [lindex $::argv 2]
    }
    default {
        puts stderr "ERROR: Unknown command '$_cmd'"
        puts stderr "Valid: create_ip  edit_ip  create_bd  edit_bd  generate_bd"
        puts stderr "       synthesis  simulate  open_dcp"
        exit 1
    }
}