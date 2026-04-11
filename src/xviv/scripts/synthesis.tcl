# =============================================================================
# Command: synthesis <top_module> <sha_tag>
#
# sha_tag is computed by Python (_git_sha_tag) and passed as argv[3].
# Format: "abc1234" for a clean tree, "abc1234_dirty" for uncommitted changes.
# TCL performs no git operations.
# =============================================================================
proc cmd_synthesis {top_module sha_tag} {
    global xviv_bd_dir xviv_build_dir xviv_synth_hooks xviv_fpga_part
    global xviv_synth_report_synth xviv_synth_report_place
    global xviv_synth_report_route xviv_synth_generate_netlist
	global xviv_wrapper_files
	global xviv_wrapper_dir

    set out_dir     "$xviv_build_dir/synth/$top_module"
    set report_dir  "$out_dir/reports"
    set netlist_dir "$out_dir/netlists"

    set dirty     0
    set sha_short $sha_tag
    if {[string match "*_dirty" $sha_tag]} {
        set dirty 1

        set sha_short [string range $sha_tag 0 end-6]
    }

    set usr_access_val [format "%s%07s" $dirty $sha_short]

    file mkdir $out_dir

    foreach stub {
        synth_pre synth_post place_post route_post bitstream_post
    } { xviv_stub $stub }

    xviv_source_hooks xviv_synth_hooks
    xviv_create_project "in_memory_project"

    xviv_add_rtl_sources

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    synth_pre

    xviv_stage "Synthesis - $top_module  (sha: $sha_tag)"

	synth_design -name synth_${top_module} -top $top_module
    write_checkpoint -force "$out_dir/post_synth.dcp"

    if {$xviv_synth_report_synth} {
		file mkdir $report_dir

        xviv_stage "Post-synthesis reports"
        report_timing_summary -file "$report_dir/post_synth_timing_summary.rpt"
        report_utilization    -file "$report_dir/post_synth_util.rpt"
    }
    if {$xviv_synth_generate_netlist} {
        file mkdir $netlist_dir
		
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

    if {$xviv_synth_report_place} {
		file mkdir $report_dir
		
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

    if {$xviv_synth_report_route} {
		file mkdir $report_dir
		
        xviv_stage "Post-routing reports"
        report_drc            -file "$report_dir/post_route_drc.rpt"
        report_methodology    -file "$report_dir/post_route_methodology.rpt"
        report_power          -file "$report_dir/post_route_power.rpt"
        report_route_status   -file "$report_dir/post_route_status.rpt"
        report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file "$report_dir/post_route_timing_summary.rpt"
    }
    if {$xviv_synth_generate_netlist} {
		file mkdir $netlist_dir

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
    write_hw_platform -fixed -include_bit -force -file "$out_dir/${export_filename}.xsa"

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
        mode            "global"                            \
        bitstream       "${export_filename}.bit"            \
        xsa             "${export_filename}.xsa"            \
        elapsed         [xviv_elapsed]                      \
        timestamp       [clock format [clock seconds] -format "%Y-%m-%dT%H:%M:%SZ"]

    puts "INFO: Build complete - [xviv_elapsed]"
    exit 0
}

# =============================================================================
# Command: cmd_synth_bd  <bd_wrapper_top> <sha_tag>
#
# Per-IP args (argv[5+]) - note: no inst_name field, cell is found by REF_NAME:
#   xci_name  top_module  dcp_dir  component_xml
#   n_rtl  [rtl...]  n_inc  [inc...]  n_xdc  [xdc...]
#
# Flow
# ----
#  Phase 1 – OOC synthesis (all leaf IPs: custom + stock)
#    For each IP, synthesise out-of-context and write post_synth.dcp.
#    Skip if the DCP is newer than the IP's component.xml (nothing changed).
#
#  Phase 2 – BD wrapper synthesis
#    open_bd_design loads all IP RTL from ipshared so synth_design elaborates
#    every IP inline.  After synth_design we call:
#      update_design -cell <cell> -black_box   (hollow out the inline netlist)
#      read_checkpoint -cell <cell> <dcp>       (load the OOC DCP)
#    for every IP.  Cells are located by REF_NAME == xci_name, which works
#    for both top-level and deeply nested IPs without needing hierarchy paths.
# =============================================================================
proc cmd_synth_bd {bd_wrapper_top sha_tag} {
    global xviv_fpga_part xviv_board_part xviv_board_repo xviv_ip_repo
    global xviv_build_dir xviv_bd_dir xviv_wrapper_files xviv_xdc_files
    global xviv_synth_report_synth xviv_synth_report_place
    global xviv_synth_report_route xviv_synth_generate_netlist
	global xviv_bd_name
    # global xviv_synth_out_of_context

    set ip_args [lrange $::argv 5 end]
    set idx 0

    # Each entry: {xci_name  dcp_file  stub_v}
    set ooc_dcps [list]

    # =========================================================================
    # Phase 1: OOC synthesis for every leaf IP
    # =========================================================================
    while {$idx < [llength $ip_args]} {

        # -- Fixed fields ------------------------------------------------------
        set xci_name  [lindex $ip_args $idx]; incr idx
        set ip_top    [lindex $ip_args $idx]; incr idx
        set dcp_dir   [lindex $ip_args $idx]; incr idx
        set cxml      [lindex $ip_args $idx]; incr idx
        set xci_file  [lindex $ip_args $idx]; incr idx
        set is_xilinx [lindex $ip_args $idx]; incr idx

        # -- Variable-length lists ---------------------------------------------
        set n_rtl [lindex $ip_args $idx]; incr idx
        set rtl_files {}
        if {$n_rtl > 0} {
            set rtl_files [lrange $ip_args $idx [expr {$idx + $n_rtl - 1}]]
            incr idx $n_rtl
        }
        set n_inc [lindex $ip_args $idx]; incr idx
        set inc_dirs {}
        if {$n_inc > 0} {
            set inc_dirs [lrange $ip_args $idx [expr {$idx + $n_inc - 1}]]
            incr idx $n_inc
        }
        set n_xdc [lindex $ip_args $idx]; incr idx
        set xdc_files {}
        if {$n_xdc > 0} {
            set xdc_files [lrange $ip_args $idx [expr {$idx + $n_xdc - 1}]]
            incr idx $n_xdc
        }

        set dcp_file  "$dcp_dir/post_synth.dcp"
        set stub_v    "$dcp_dir/stub.v"

        # Skip if DCP is up to date
        if {[file exists $dcp_file] && [file exists $cxml]} {
            if {[file mtime $dcp_file] >= [file mtime $cxml]} {
                if {[file exists $stub_v]} {
                    puts "INFO: OOC DCP up to date, skipping - $xci_name"
                    lappend ooc_dcps [list $xci_name $dcp_file $stub_v]
                    continue
                }

                # DCP is current but stub.v is missing (first run after the
                # stub-generation feature was added).  Reopen the checkpoint
                # and emit the stub without re-synthesising.
                puts "INFO: DCP cached but stub.v absent - regenerating stub for $xci_name"
                catch {close_project}
                create_project -part $xviv_fpga_part -in_memory "stub_$xci_name"
                open_checkpoint $dcp_file
                write_verilog -force -mode synth_stub $stub_v
                catch {close_project}
                puts "INFO: Stub regenerated - $stub_v"
                lappend ooc_dcps [list $xci_name $dcp_file $stub_v]
                continue
            }
        }

        # -- OOC synthesis -----------------------------------------------------
        xviv_stage "OOC synthesis: $xci_name  (top: $ip_top  xilinx: $is_xilinx)"

        catch {close_project}
        create_project -part $xviv_fpga_part -in_memory "ooc_$xci_name"

        if {[info exists xviv_board_part] && $xviv_board_part ne ""} {
            if {[info exists xviv_board_repo] && $xviv_board_repo ne ""} {
                set_param board.repoPaths [list $xviv_board_repo]
            }
            set_property board_part $xviv_board_part [current_project]
        }
        set_property ip_repo_paths [list $xviv_ip_repo] [current_project]
        update_ip_catalog -rebuild -quiet

        if {$is_xilinx} {
            read_ip $xci_file
            generate_target synthesis [get_files $xci_file] -quiet
            set_property synth_checkpoint_mode None [get_files $xci_file]
        } else {
            if {[llength $rtl_files] > 0} {
                add_files -norecurse -scan_for_includes $rtl_files
            }
            if {[llength $inc_dirs] > 0} {
                set_property include_dirs $inc_dirs [current_fileset]
            }
            if {[llength $xdc_files] > 0} {
                add_files -fileset constrs_1 $xdc_files
                set_property USED_IN {out_of_context} [get_files $xdc_files]
            }
        }

        set_property TOP $ip_top [current_fileset]
        update_compile_order -fileset sources_1

        file mkdir $dcp_dir
        synth_design -mode out_of_context -top $ip_top -name "ooc_$xci_name"
        write_checkpoint -force $dcp_file
        write_verilog   -force -mode synth_stub $stub_v
        puts "INFO: OOC checkpoint written - $dcp_file  \[+[xviv_elapsed]\]"
        puts "INFO: Black-box stub written  - $stub_v"

        lappend ooc_dcps [list $xci_name $dcp_file $stub_v]
    }

    # =========================================================================
    # Phase 2: BD wrapper synthesis
    #
    # open_bd_design normally pulls every IP's generated RTL into the fileset
    # and synth_design would compile each IP inline.  Instead we:
    #   1. Disable the inline RTL for every IP that has an OOC DCP.
    #   2. Add the synth_stub .v for each such IP so synth_design sees a
    #      (* black_box *) shell rather than the full implementation.
    #   3. After synthesis, load each OOC DCP directly into its black-box cell
    #      with read_checkpoint -cell - no update_design -black_box needed.
    # =========================================================================
    xviv_stage "BD wrapper synthesis: $bd_wrapper_top"
    catch {close_project}

    # -- Resolve output paths --------------------------------------------------
    set out_dir     "$xviv_build_dir/synth/$bd_wrapper_top/ooc"
    set report_dir  "$out_dir/reports"
    set netlist_dir "$out_dir/netlists"

    set dirty     0
    set sha_short $sha_tag
    if {[string match "*_dirty" $sha_tag]} {
        set dirty 1
        set sha_short [string range $sha_tag 0 end-6]
    }
    set usr_access_val [format "%s%07s" $dirty $sha_short]
    file mkdir $out_dir

    xviv_source_hooks xviv_synth_hooks
    xviv_create_project "in_memory_project"

    # -- Load BD ---------------------------------------------------------------
    set bd_file "$xviv_bd_dir/$xviv_bd_name/$xviv_bd_name.bd"
    if {![file exists $bd_file]} {
        xviv_die "BD file not found: $bd_file - run generate-bd first"
    }
    read_bd        $bd_file
    open_bd_design $bd_file

    # -- Add BD wrapper --------------------------------------------------------
    if {[info exists xviv_wrapper_files] && [llength $xviv_wrapper_files] > 0} {
        foreach f $xviv_wrapper_files {
            if {[string match "*${bd_wrapper_top}*" $f]} {
                puts "INFO: Adding BD wrapper: $f"
                add_files $f
                break
            }
        }
    }

    # -- Add XDC ---------------------------------------------------------------
    if {[info exists xviv_xdc_files] && [llength $xviv_xdc_files] > 0} {
        add_files -fileset constrs_1 $xviv_xdc_files
        # if {$xviv_synth_out_of_context} {
        #     set_property USED_IN {out_of_context} [get_files $xviv_xdc_files]
        # }
    }

    update_compile_order -fileset sources_1

    # -- Substitute OOC IP RTL with black-box Verilog stubs -------------------
    #
    # For each IP that has an OOC DCP:
    #   - Mark every RTL file belonging to that IP as USED_IN_SYNTHESIS false
    #     so Vivado does not attempt to compile it inline.
    #   - Add the synth_stub .v so synth_design finds a (* black_box *)
    #     module declaration and leaves the cell empty.
    # -------------------------------------------------------------------------
    foreach entry $ooc_dcps {
        set xci_name [lindex $entry 0]
        set stub_v   [lindex $entry 2]

        if {![file exists $stub_v]} {
            xviv_die "Black-box stub missing for $xci_name: $stub_v"
        }

        # Suppress inline RTL for this IP
        # Bypass get_ips to catch dynamically generated sub-cores (like auto_pc, xbar).
        # We find any RTL file whose path contains the IP name, ignoring our stubs.
        set rtl_filter {FILE_TYPE =~ "Verilog*" || FILE_TYPE =~ "VHDL*" || FILE_TYPE =~ "SystemVerilog*"}
        set ip_rtl [get_files -quiet -filter "NAME =~ *${xci_name}* && NAME !~ *stub* && ($rtl_filter)"]
        
        if {[llength $ip_rtl] > 0} {
            set_property USED_IN_SYNTHESIS false $ip_rtl
            puts "INFO: Disabled inline RTL for $xci_name  ([llength $ip_rtl] file(s))"
        }

        # Add black-box stub as a synthesis source
        add_files -norecurse $stub_v
        set_property USED_IN {synthesis implementation} [get_files $stub_v]
        puts "INFO: Black-box stub registered for $xci_name  →  $stub_v"
    }

    update_compile_order -fileset sources_1

    # -- Synthesis -------------------------------------------------------------
    xviv_stage "Synthesis - $bd_wrapper_top  (sha: $sha_tag)"
    synth_design -name "synth_$bd_wrapper_top" -top $bd_wrapper_top
    write_checkpoint -force "$out_dir/post_synth.dcp"

    if {$xviv_synth_report_synth} {
        file mkdir $report_dir
        xviv_stage "Post-synthesis reports"
        report_timing_summary -file "$report_dir/post_synth_timing_summary.rpt"
        report_utilization    -file "$report_dir/post_synth_util.rpt"
    }

    # -- Load OOC DCPs into black-box cells -----------------------------------
    #
    # Cells are already black boxes from synthesis (the stub.v carries the
    # (* black_box *) pragma), so read_checkpoint -cell is all that is needed.
    # -------------------------------------------------------------------------
    foreach entry $ooc_dcps {
        set xci_name [lindex $entry 0]
        set dcp_file [lindex $entry 1]

        if {![file exists $dcp_file]} {
            xviv_die "OOC DCP missing for $xci_name: $dcp_file"
        }

        set cells [get_cells -hierarchical -filter "REF_NAME == $xci_name" -quiet]
        if {[llength $cells] == 0} {
            puts "INFO: No cells with REF_NAME=$xci_name - skipping (optimised away)"
            continue
        }

        foreach cell $cells {
            puts "INFO: Loading OOC DCP: $cell  <-  $dcp_file"
            read_checkpoint -cell $cell $dcp_file
        }
        puts "INFO: OOC DCP locked for $xci_name  \[+[xviv_elapsed]\]"
    }
	
	# xviv_stage "Logic Optimization"
    # opt_design
	
	set reference_dcp "$out_dir/post_route_reference.dcp"

    if {[file exists $reference_dcp]} {
        xviv_stage "Applying Incremental Reference Checkpoint"
        read_checkpoint -incremental $reference_dcp
    } else {
        puts "INFO: No reference DCP found at $reference_dcp. Running standard Implementation."
    }

    # -- Placement -------------------------------------------------------------
    xviv_stage "Placement"
    place_design
    write_checkpoint -force "$out_dir/post_place.dcp"

    if {$xviv_synth_report_place} {
        file mkdir $report_dir
        xviv_stage "Post-placement reports"
        report_io                        -file "$report_dir/post_place_io.rpt"
        report_clock_utilization         -file "$report_dir/post_place_clock_util.rpt"
        report_utilization -hierarchical -file "$report_dir/post_place_util_hier.rpt"
    }
	
	# Only run phys_opt_design if timing is failing
    if {[get_property SLACK [get_timing_paths]] < 0} {
        xviv_stage "Physical Optimization (Timing Failed, attempting fix)"
        phys_opt_design
        write_checkpoint -force "$out_dir/post_phys_opt.dcp"
    } else {
        puts "INFO: Timing met after placement. Skipping phys_opt_design to save time."
    }

    # -- Routing ---------------------------------------------------------------
    xviv_stage "Routing"
    route_design
    write_checkpoint -force "$out_dir/post_route.dcp"

    # -- Save the new reference for the next build -----------------------------
    # Overwrite the reference DCP so the next build uses this one as its baseline
    file copy -force "$out_dir/post_route.dcp" $reference_dcp

    if {$xviv_synth_report_route} {
        file mkdir $report_dir
        xviv_stage "Post-routing reports"
        report_drc            -file "$report_dir/post_route_drc.rpt"
        report_methodology    -file "$report_dir/post_route_methodology.rpt"
        report_power          -file "$report_dir/post_route_power.rpt"
        report_route_status   -file "$report_dir/post_route_status.rpt"
        report_timing_summary -max_paths 10 -report_unconstrained \
                              -warn_on_violation \
                              -file "$report_dir/post_route_timing_summary.rpt"
    }

    if {$xviv_synth_generate_netlist} {
        file mkdir $netlist_dir
        write_verilog -force -mode funcsim \
            "$netlist_dir/post_impl_functional.v"
        write_verilog -force -mode timesim -sdf_anno true \
            "$netlist_dir/post_impl_timing.v"
    }

    # -- USR_ACCESS ------------------------------------------------------------
    set_property BITSTREAM.CONFIG.USR_ACCESS 0x${usr_access_val} [current_design]
    puts "INFO: USR_ACCESS = 0x${usr_access_val}  (sha=${sha_short}  dirty=${dirty})"

    # -- Bitstream + XSA -------------------------------------------------------
    xviv_stage "Generating bitstream"
    set export_filename "${bd_wrapper_top}_${sha_tag}"

    write_bitstream   -force "$out_dir/${export_filename}.bit"
    write_hw_platform -fixed -include_bit -force -file "$out_dir/${export_filename}.xsa"

    xviv_update_symlink "$out_dir/${bd_wrapper_top}.bit" "${export_filename}.bit"
    xviv_update_symlink "$out_dir/${bd_wrapper_top}.xsa" "${export_filename}.xsa"

    # -- Build manifest --------------------------------------------------------
    xviv_write_manifest "$out_dir/build.json"             \
        vivado_version [version -short]                   \
        part           $xviv_fpga_part                    \
        top            $bd_wrapper_top                    \
        sha_tag        $sha_tag                           \
        sha_short      $sha_short                         \
        dirty          [expr {$dirty ? "true" : "false"}] \
        mode           "bd"                               \
        bitstream      "${export_filename}.bit"           \
        xsa            "${export_filename}.xsa"           \
        elapsed        [xviv_elapsed]                     \
        timestamp      [clock format [clock seconds] -format "%Y-%m-%dT%H:%M:%SZ"]

    puts "INFO: Build complete - [xviv_elapsed]"
    exit 0
}