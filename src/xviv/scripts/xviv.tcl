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
#   create_ip                           - scaffold + customise a new IP
#   edit_ip                             - open an existing IP for editing
#   create_bd                           - create a new Block Design
#   edit_bd                             - open an existing BD in the GUI
#   generate_bd                         - generate BD output products + wrapper
#   export_bd                           - export BD as a versioned re-runnable TCL
#   synthesis    <top_module> <sha_tag> - synth -> place -> route -> bitstream
#   simulate     <sim_top> [so] [dpi]   - launch Vivado simulation
#   open_dcp     <dcp_file>             - open a checkpoint in the GUI
#
# Changes from original:
#   - xviv_die: centralised error reporting with project/design context
#   - xviv_require_vars: config validation before any Vivado work starts
#   - xviv_elapsed / xviv_stage: stopwatch printed at every major stage
#   - xviv_create_project: validates part against installed catalog (get_parts)
#   - xviv_add_rtl_sources: warns when no design files are added
#   - xviv_source_hooks: catches syntax errors in hooks files with clear message
#   - xviv_stub: logs when a no-op stub is installed
#   - xviv_update_symlink: uses [file link] instead of exec ln (portable)
#   - xviv_write_manifest: writes a JSON build record after synthesis
#   - cmd_create_ip: split into _xviv_ip_* sub-procs (one per stage)
#   - cmd_synthesis: sha_tag passed from Python; no git calls in TCL
#   - cmd_generate_bd / cmd_export_bd: upgrade_ip wrapped in catch
#   - cmd_generate_bd: uses [file copy] instead of exec cp
# =============================================================================

if {$::argc < 2} {
    puts stderr "XVIV ERROR: Usage: vivado ... -source xviv.tcl -tclargs <command> <config.tcl> \[extra\]"
    exit 1
}

set _cmd        [lindex $::argv 0]
set _config_tcl [lindex $::argv 1]

if {![file exists $_config_tcl]} {
    puts stderr "XVIV ERROR: Config file not found: $_config_tcl"
    exit 1
}

source $_config_tcl

# Start the global stopwatch immediately after config is loaded so elapsed
# time covers the full command including project creation.
set _xviv_t0 [clock milliseconds]

# =============================================================================
# Shared utilities
# =============================================================================

# ---------------------------------------------------------------------------
# xviv_die  -  print a structured error message and exit 1.
#
# All error exits in this file go through here so every failure is formatted
# identically and easy to grep in CI logs.
# ---------------------------------------------------------------------------
proc xviv_die {msg} {
    puts stderr ""
    puts stderr "XVIV ERROR: $msg"
    puts stderr "  command : $::_cmd"
    catch { puts stderr "  project : [current_project]" }
    catch { puts stderr "  design  : [current_design]"  }
    puts stderr ""
    exit 1
}

# ---------------------------------------------------------------------------
# xviv_require_vars  -  assert that global config variables exist and are
# non-empty.  Call at the top of each cmd_* proc listing every variable it
# depends on.  A missing variable means a bug in generate_config_tcl or a
# wrong command/config combination.
# ---------------------------------------------------------------------------
proc xviv_require_vars {args} {
    foreach v $args {
        if {![info exists ::$v] || [set ::$v] eq ""} {
            xviv_die "Required config variable \$$v is missing or empty.\
 Check that generate_config_tcl emits it for this command."
        }
    }
}

# ---------------------------------------------------------------------------
# Stopwatch helpers.
#
# xviv_elapsed  - returns elapsed time as "Xm Ys" since script start.
# xviv_stage    - prints a timestamped stage banner to stdout.
#
# Both use the global _xviv_t0 set immediately after sourcing the config.
# ---------------------------------------------------------------------------
proc xviv_elapsed {} {
    set ms  [expr {[clock milliseconds] - $::_xviv_t0}]
    set min [expr {$ms / 60000}]
    set sec [expr {($ms % 60000) / 1000}]
    return [format "%dm%02ds" $min $sec]
}

proc xviv_stage {name} {
    puts "INFO: \[+[xviv_elapsed]\] $name"
}

# ---------------------------------------------------------------------------
# xviv_create_project  -  create an in-memory Vivado project.
#
# Validates the FPGA part string against the installed catalog via get_parts
# before creating the project.  A typo in project.toml therefore fails in
# seconds rather than after hours of synthesis.
#
# board_part and board_repo are optional; skipped when empty.
# ---------------------------------------------------------------------------
proc xviv_create_project {name} {
    global xviv_fpga_part xviv_board_part xviv_board_repo xviv_ip_repo

    # get_parts returns an empty list for unknown part strings.
    # This is the earliest point we can catch a wrong part number.
    if {[llength [get_parts $xviv_fpga_part]] == 0} {
        xviv_die "FPGA part '$xviv_fpga_part' is not in the installed Vivado part catalog.\
 Check [fpga] part in project.toml."
    }

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

# ---------------------------------------------------------------------------
# xviv_add_rtl_sources  -  add RTL + wrapper sources to sources_1,
# constraints to constrs_1.
#
# Emits a warning when no design files are added at all.  This almost always
# means a glob pattern in project.toml matched nothing, which would produce
# a confusing "top module not found" error later without this guard.
# ---------------------------------------------------------------------------
proc xviv_add_rtl_sources {} {
    global xviv_rtl_files xviv_wrapper_files xviv_constr_files

    set design_added 0

    if {[info exists xviv_rtl_files] && [llength $xviv_rtl_files] > 0} {
        add_files $xviv_rtl_files
        set design_added 1
    }
    if {[info exists xviv_wrapper_files] && [llength $xviv_wrapper_files] > 0} {
        add_files $xviv_wrapper_files
        set design_added 1
    }
    if {[info exists xviv_constr_files] && [llength $xviv_constr_files] > 0} {
        add_files -fileset constrs_1 $xviv_constr_files
    }

    if {!$design_added} {
        puts "WARN: No RTL or wrapper source files were added to the project."
        puts "WARN: Check that [sources] rtl/wrapper globs in project.toml match real files."
    }

    update_compile_order -fileset sources_1
}

# ---------------------------------------------------------------------------
# xviv_add_sim_sources  -  add simulation sources to sim_1
# ---------------------------------------------------------------------------
proc xviv_add_sim_sources {} {
    global xviv_sim_files

    if {[info exists xviv_sim_files] && [llength $xviv_sim_files] > 0} {
        foreach f $xviv_sim_files {
            add_files -fileset sim_1 $f
        }
    }
    update_compile_order -fileset sim_1
}

# ---------------------------------------------------------------------------
# xviv_refresh_bd_addresses  -  delete and reassign all BD address segments
# ---------------------------------------------------------------------------
proc xviv_refresh_bd_addresses {} {
    delete_bd_objs [get_bd_addr_segs] [get_bd_addr_segs -excluded]
    assign_bd_address
}

# ---------------------------------------------------------------------------
# xviv_source_hooks  -  source an optional hooks file referenced by variable
# var_name.  Reports a clear, actionable error on syntax failures instead of
# a raw TCL traceback.  Silently skips when the variable is empty or unset.
# ---------------------------------------------------------------------------
proc xviv_source_hooks {var_name} {
    upvar $var_name hooks_file

    if {![info exists hooks_file] || $hooks_file eq ""} { return }

    if {![file exists $hooks_file]} {
        xviv_die "Hooks file is configured but does not exist: $hooks_file"
    }

    if {[catch {source $hooks_file} err]} {
        xviv_die "Error while sourcing hooks file $hooks_file:\n  $err"
    }

    puts "INFO: Sourced hooks - $hooks_file"
}

# ---------------------------------------------------------------------------
# xviv_stub  -  install a no-op proc only if one is not already defined.
# Logs at DEBUG level so absent optional hooks are visible when tracing.
# ---------------------------------------------------------------------------
proc xviv_stub {name} {
    if {[info procs $name] eq ""} {
        puts "DEBUG: No-op stub installed for optional hook: $name"
        proc $name {} {}
    }
}

# ---------------------------------------------------------------------------
# xviv_update_symlink  -  create or replace a symbolic link using TCL's
# built-in [file link] instead of exec ln so the code works outside a
# POSIX shell environment.
#
# link_path : full path to the symlink to create/replace
# target    : symlink target, relative to the directory of link_path
# ---------------------------------------------------------------------------
proc xviv_update_symlink {link_path target} {
    catch { file delete $link_path }
    file link -symbolic $link_path $target
    puts "INFO: Symlink updated: [file tail $link_path] -> $target"
}

# ---------------------------------------------------------------------------
# xviv_write_manifest  -  write a minimal JSON build manifest at path.
#
# Accepts flat key-value pairs as args.  Written last in the synthesis flow
# so the file only exists for runs that completed successfully.
# ---------------------------------------------------------------------------
proc xviv_write_manifest {path args} {
    set fields {}
    foreach {k v} $args {
        lappend fields "  \"$k\": \"$v\""
    }
    set fh [open $path w]
    puts $fh "\{"
    puts $fh [join $fields ",\n"]
    puts $fh "\}"
    close $fh
    puts "INFO: Build manifest written - $path"
}

# =============================================================================
# IP creation sub-procs
#
# cmd_create_ip delegates each of its seven logical stages to a dedicated
# proc.  Each proc is self-contained, independently named in log output, and
# easier to read and test in isolation.
# All sub-procs are prefixed _xviv_ip_ to avoid polluting the global namespace.
# =============================================================================

# Stage 1: scaffold the default IP skeleton and open the edit project so that
# subsequent stages operate on [ipx::current_core].
proc _xviv_ip_scaffold {ip_id ip_vid ip_dir proj_root} {
    global xviv_ip_vendor xviv_ip_library xviv_ip_name xviv_ip_version xviv_ip_repo

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
}

# Stage 2: remove the boilerplate AXI-Lite interface and the stub Verilog
# files that Vivado's peripheral generator always emits.
proc _xviv_ip_strip_scaffold {} {
    foreach ifc {S00_AXI S00_AXI_RST S00_AXI_CLK} {
        catch { ipx::remove_bus_interface $ifc [ipx::current_core] }
    }
    catch { ipx::remove_memory_map     S00_AXI            [ipx::current_core] }
    catch { ipx::remove_user_parameter C_S00_AXI_BASEADDR [ipx::current_core] }
    catch { ipx::remove_user_parameter C_S00_AXI_HIGHADDR [ipx::current_core] }

    foreach f [get_files -filter {FILE_TYPE == Verilog}] {
        remove_files $f
        file delete -force $f
    }
}

# Stage 3: infer standard AXI-Stream and AXI-MM interfaces, then call the
# user hook for any additional custom inference.
proc _xviv_ip_infer_interfaces {} {
    puts "INFO: Inferring AXI-Stream interfaces"
    ipx::infer_bus_interfaces \
        xilinx.com:interface:axis_rtl:1.0  [ipx::current_core]
    puts "INFO: Inferring AXI-MM interfaces"
    ipx::infer_bus_interfaces \
        xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]

    ipx_infer_bus_interfaces
    update_compile_order -fileset sources_1
}

# Stage 4: expose every HDL parameter in the IP customisation GUI on Page 0,
# then call the user hook for reordering or grouping.
proc _xviv_ip_expose_params {} {
    foreach param [ipx::get_hdl_parameters -of_objects [ipx::current_core]] {
        set pname [get_property NAME $param]
        ipgui::add_param -name $pname -component [ipx::current_core] \
            -parent [ipgui::get_pagespec \
                -name "Page 0" -component [ipx::current_core]]
    }
    ipx_add_params
}

# Stage 5: for every AXI-Lite slave interface, create a memory map and an
# address block, then associate the map with the interface.
proc _xviv_ip_wire_memory_maps {} {
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
}

# Stage 6: bump the core revision, regenerate GUI files, verify integrity,
# and persist the component.xml.
proc _xviv_ip_finalise {ip_vid} {
    set_property core_revision 2 [ipx::current_core]
    ipx::update_source_project_archive -component [ipx::current_core]
    ipx::create_xgui_files  [ipx::current_core]
    ipx::update_checksums   [ipx::current_core]
    ipx::check_integrity    [ipx::current_core]
    ipx::save_core          [ipx::current_core]
    puts "INFO: IP saved - $ip_vid"
}

# =============================================================================
# Command: create_ip
# =============================================================================
proc cmd_create_ip {} {
    global xviv_ip_name xviv_ip_vendor xviv_ip_library xviv_ip_version
    global xviv_ip_top xviv_ip_rtl xviv_ip_hooks  xviv_ip_repo

    xviv_require_vars xviv_ip_name xviv_ip_vendor xviv_ip_library \
                      xviv_ip_version xviv_ip_repo

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

# =============================================================================
# Command: edit_ip
# =============================================================================
proc cmd_edit_ip {} {
    global xviv_ip_name xviv_ip_version xviv_ip_repo

    xviv_require_vars xviv_ip_name xviv_ip_version xviv_ip_repo

    set ip_vid    "${xviv_ip_name}_[string map {. _} $xviv_ip_version]"
    set ip_dir    "$xviv_ip_repo/$ip_vid"
    set proj_root "/dev/shm/build"

    if {![file exists "$ip_dir/component.xml"]} {
        xviv_die "IP not found at $ip_dir/component.xml - has create-ip been run?"
    }

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

# =============================================================================
# Command: edit_bd
# =============================================================================
proc cmd_edit_bd {} {
    global xviv_bd_name xviv_bd_dir

    xviv_require_vars xviv_bd_name xviv_bd_dir

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file\nHas create-bd been run?"
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
            puts "WARN: One or more IPs failed to upgrade: $err"
            puts "WARN: Continuing with generation - verify IP status manually"
        }
    }

    reset_target  {synthesis simulation implementation} [get_files $bd_file]
    generate_target all                                 [get_files $bd_file]

    set wrapper_src [make_wrapper -files [get_files $bd_file] -top]

    if {[info exists xviv_wrapper_dir] && $xviv_wrapper_dir ne ""} {
        file mkdir $xviv_wrapper_dir
        # Use TCL file copy instead of exec cp for portability
        file copy -force $wrapper_src $xviv_wrapper_dir
        puts "INFO: BD wrapper copied to $xviv_wrapper_dir"
    }

    puts "INFO: BD generation complete - [xviv_elapsed]"
    exit 0
}

# =============================================================================
# Command: export_bd
#
# Exports the current .bd as a fully self-contained re-runnable TCL script.
# The output path (xviv_bd_export_tcl) is supplied by the Python controller
# and already encodes the git SHA tag produced by _git_sha_tag().
# Python updates the {bd_name}.tcl symlink after this proc exits.
#
# IP version strings are preserved (no -no_ip_version flag) so the exported
# TCL recreates the BD identically on any machine with a matching Vivado +
# IP installation.
# =============================================================================
proc cmd_export_bd {} {
    global xviv_bd_name xviv_bd_dir xviv_bd_export_tcl

    xviv_require_vars xviv_bd_name xviv_bd_dir xviv_bd_export_tcl

    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"

    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file\nHas create-bd been run?"
    }

    puts "INFO: Exporting Block Design - $xviv_bd_name"
    puts "INFO: Output TCL             - $xviv_bd_export_tcl"

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

    file mkdir [file dirname $xviv_bd_export_tcl]

    # -no_ip_version intentionally omitted: full VLNV version pins are
    # required for bit-identical BD recreation on another machine.
    write_bd_tcl -force \
		-no_project_wrapper \
        $xviv_bd_export_tcl
        # -hier_blks [get_bd_cells -hierarchical -filter {TYPE == hier}] \

    puts "INFO: Export complete - $xviv_bd_export_tcl"
    puts "INFO: Total elapsed: [xviv_elapsed]"
    exit 0
}

# =============================================================================
# Command: synthesis <top_module> <sha_tag>
#
# sha_tag is computed by Python (_git_sha_tag) and passed as argv[3].
# Format: "abc1234" for a clean tree, "abc1234_dirty" for uncommitted changes.
# TCL performs no git operations.
# =============================================================================
proc cmd_synthesis {top_module sha_tag} {
    global xviv_bd_dir xviv_build_dir xviv_synth_hooks xviv_fpga_part

    xviv_require_vars xviv_build_dir

    set out_dir     "$xviv_build_dir/$top_module"
    set report_dir  "$out_dir/reports"
    set netlist_dir "$out_dir/netlists"

    # Decode sha_tag into components for USR_ACCESS encoding.
    # sha_tag format: "abc1234" or "abc1234_dirty"
    set dirty     0
    set sha_short $sha_tag
    if {[string match "*_dirty" $sha_tag]} {
        set dirty 1
        # Remove trailing "_dirty" (6 characters) to recover the raw SHA
        set sha_short [string range $sha_tag 0 end-6]
    }

    # USR_ACCESS: bit 31 = dirty flag, bits 27:0 = 7-hex-digit SHA.
    # Produces an 8-hex-digit string: "0abc1234" (clean) / "1abc1234" (dirty).
    set usr_access_val [format "%s%07s" $dirty $sha_short]

    file mkdir $out_dir
    file mkdir $report_dir
    file mkdir $netlist_dir

    # Lifecycle stubs - all default to no-ops
    foreach stub {
        synth_pre synth_post place_post route_post bitstream_post
    } { xviv_stub $stub }

    # Report-flag stubs - all default to enabled (return 1)
    foreach flag {report_synth report_place report_route report_netlists} {
        if {[info procs $flag] eq ""} {
            puts "DEBUG: No-op stub installed for optional report flag: $flag"
            proc $flag {} { return 1 }
        }
    }

    xviv_source_hooks xviv_synth_hooks
    xviv_create_project "in_memory_project"

    set bd_files [glob -nocomplain "$xviv_bd_dir/*/*.bd"]
    if {[llength $bd_files] > 0} { read_bd $bd_files }

    xviv_add_rtl_sources

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    synth_pre

    xviv_stage "Synthesis - $top_module  (sha: $sha_tag)"
    synth_design -name synth_${top_module} -top $top_module
    write_checkpoint -force "$out_dir/post_synth.dcp"

    if {[report_synth]} {
        xviv_stage "Post-synthesis reports"
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
    xviv_stage "Placement"
    place_design
    write_checkpoint -force "$out_dir/post_place.dcp"

    if {[report_place]} {
        xviv_stage "Post-placement reports"
        report_io                        -file "$report_dir/post_place_io.rpt"
        report_clock_utilization         -file "$report_dir/post_place_clock_util.rpt"
        report_utilization -hierarchical -file "$report_dir/post_place_util_hier.rpt"
    }

    place_post

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    xviv_stage "Routing"
    route_design
    write_checkpoint -force "$out_dir/post_route.dcp"

    if {[report_route]} {
        xviv_stage "Post-routing reports"
        report_drc            -file "$report_dir/post_route_drc.rpt"
        report_methodology    -file "$report_dir/post_route_methodology.rpt"
        report_power          -file "$report_dir/post_route_power.rpt"
        report_route_status   -file "$report_dir/post_route_status.rpt"
        report_timing_summary -max_paths 10 -report_unconstrained \
            -warn_on_violation -file "$report_dir/post_route_timing_summary.rpt"
    }
    if {[report_netlists]} {
        write_verilog -force -mode funcsim                "$netlist_dir/post_impl_functional.v"
        write_verilog -force -mode timesim -sdf_anno true "$netlist_dir/post_impl_timing.v"
    }

    route_post

    # ------------------------------------------------------------------
    # USR_ACCESS - embeds git SHA into the bitstream readable via JTAG
    # ------------------------------------------------------------------
    set_property BITSTREAM.CONFIG.USR_ACCESS 0x${usr_access_val} [current_design]
    puts "INFO: USR_ACCESS = 0x${usr_access_val}  (sha=${sha_short}  dirty=${dirty})"

    # ------------------------------------------------------------------
    # Bitstream + XSA
    # ------------------------------------------------------------------
    xviv_stage "Generating bitstream"
    set export_filename "${top_module}_${sha_tag}"

    write_bitstream   -force "$out_dir/${export_filename}.bit"
    write_hw_platform -fixed -include_bit -force \
        -file "$out_dir/${export_filename}.xsa"

    # Symlinks always point at the latest build output.
    # Targets are relative (filename only) so symlinks are portable within
    # the build directory regardless of absolute checkout path.
    # Uses [file link] instead of exec ln for cross-platform compatibility.
    xviv_update_symlink "$out_dir/${top_module}.bit" "${export_filename}.bit"
    xviv_update_symlink "$out_dir/${top_module}.xsa" "${export_filename}.xsa"

    bitstream_post

    # ------------------------------------------------------------------
    # Build manifest - written last so it only exists for complete runs.
    # Fields use [version -short] for the installed Vivado version string.
    # ------------------------------------------------------------------
    xviv_write_manifest "$out_dir/build.json"               \
        vivado_version  [version -short]                    \
        part            $xviv_fpga_part                     \
        top             $top_module                         \
        sha_tag         $sha_tag                            \
        sha_short       $sha_short                          \
        dirty           [expr {$dirty ? "true" : "false"}]  \
        bitstream       "${export_filename}.bit"            \
        xsa             "${export_filename}.xsa"            \
        elapsed         [xviv_elapsed]                      \
        timestamp       [clock format [clock seconds] \
                            -format "%Y-%m-%dT%H:%M:%SZ"]

    puts "INFO: Build complete - [xviv_elapsed]"
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

    set_property top     $sim_top       [get_filesets sim_1]
    set_property top_lib xil_defaultlib [get_filesets sim_1]
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
        xviv_die "DCP file not found: $dcp_file"
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
    export_bd   { cmd_export_bd   }
    synthesis   {
        if {$::argc < 3} {
            xviv_die "synthesis requires <top_module>"
        }
        # sha_tag is argv[3], computed by Python _git_sha_tag().
        # Defaults to "unknown" when called without a sha_tag for
        # backward compatibility with any direct Vivado invocations.
        set _sha_tag [expr {$::argc > 3 ? [lindex $::argv 3] : "unknown"}]
        cmd_synthesis [lindex $::argv 2] $_sha_tag
    }
    simulate    {
        if {$::argc < 3} {
            xviv_die "simulate requires <sim_top>"
        }
        set _sim_top [lindex $::argv 2]
        set _so_file [expr {$::argc > 3 ? [lindex $::argv 3] : ""}]
        set _dpi_lib [expr {$::argc > 4 ? [lindex $::argv 4] : ""}]
        cmd_simulate $_sim_top $_so_file $_dpi_lib
    }
    open_dcp    {
        if {$::argc < 3} {
            xviv_die "open_dcp requires <dcp_file>"
        }
        cmd_open_dcp [lindex $::argv 2]
    }
    default {
        puts stderr "XVIV ERROR: Unknown command '$_cmd'"
        puts stderr "Valid commands:"
        puts stderr "  create_ip   edit_ip"
        puts stderr "  create_bd   edit_bd   generate_bd   export_bd"
        puts stderr "  synthesis   simulate  open_dcp"
        exit 1
    }
}