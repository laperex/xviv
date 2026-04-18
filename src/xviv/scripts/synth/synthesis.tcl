proc git_diff_to_file {outfile} {
    set diff ""
    catch {exec git diff HEAD} diff

    set fh [open $outfile w]
    puts -nonewline $fh $diff
    close $fh

    return [string length $diff]
}

# =============================================================================
# Command: synthesis <top_module> <sha_tag>
# =============================================================================
proc cmd_synthesis {top_module sha_tag} {
    global xviv_bd_dir xviv_build_dir xviv_synth_hooks xviv_fpga_part
    global xviv_synth_report_synth xviv_synth_report_place
    global xviv_synth_report_route xviv_synth_generate_netlist xviv_iso_timestamp

    # ------------------------------------------------------------------
    # CONFIGURATION VARIABLES (Mapped from SynthConfig dataclass)
    # ------------------------------------------------------------------
    # Global Settings
    # set max_threads         8
    set incr_synth_fallback "continue"  ;# values: continue | terminate

    # Flow Toggles
    set incremental_synth   1           ;# 1 = true, 0 = false
    set incremental_impl    1           ;# 1 = true, 0 = false

    # Synthesis Options
    set synth_directive     "default"
    set flatten_hierarchy   "rebuilt"
    set fsm_extraction      "auto"

    # Logic Optimization Options
    set run_opt_design      1
    set opt_directive       "default"

    # Placement Options
    set place_directive     "default"

    # Physical Optimization Options
    set run_phys_opt        0
    set phys_opt_directive  "default"

    # Routing Options
    set route_directive     "default"

    # Bitstream Options
    set usr_access_override ""
    # ------------------------------------------------------------------

    # Apply global thread limit
    # set_param general.maxThreads $max_threads

    set dirty     0
    set sha_short $sha_tag
    if {[string match "*_dirty" $sha_tag]} {
        set dirty 1
        set sha_short [string range $sha_tag 0 end-6]
    }

    set out_dir     "$xviv_build_dir/synth/$top_module"
	set run_dir     "$out_dir/runs/$sha_short"
    set report_dir  "$run_dir/reports"
    set netlist_dir "$run_dir/netlists"

    # Determine final USR_ACCESS value
    if {$usr_access_override ne ""} {
        set usr_access_val $usr_access_override
    } else {
        set usr_access_val [format "%s%07s" $dirty $sha_short]
    }

    file mkdir $out_dir

    foreach stub {
        synth_pre synth_post place_post route_post bitstream_post
    } { xviv_stub $stub }

    xviv_source_hooks xviv_synth_hooks
    xviv_create_project "in_memory_project"

    xviv_add_rtl_sources
	xviv_add_xdc_sources

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    synth_pre
    
    # Configure Incremental Synthesis Fallback Behavior
    if {$incr_synth_fallback eq "terminate"} {
        # set_param config_implementation {autoIncr.Synth.RejectBehavior Terminate}
    } else {
        # set_param config_implementation {autoIncr.Synth.RejectBehavior Default}
    }

    if {$incremental_synth} {
        set reference_post_synth_dcp "$out_dir/post_synth.dcp"
        if {[file exists $reference_post_synth_dcp]} {
            xviv_stage "Applying Incremental Synthesis Reference"
            read_checkpoint -incremental $reference_post_synth_dcp
        } else {
            puts "INFO: No reference post_synth DCP found at $reference_post_synth_dcp. Running standard Synthesis."
        }
    }

    xviv_stage "Synthesis - $top_module  (sha: $sha_tag)"

    synth_design -name synth_${top_module} -top $top_module \
                 -directive $synth_directive \
                 -flatten_hierarchy $flatten_hierarchy \
                 -fsm_extraction $fsm_extraction
                 
    write_checkpoint -force "$out_dir/post_synth.dcp"

    if {$xviv_synth_report_synth} {
        file mkdir $report_dir
        xviv_stage "Post-synthesis reports"
        report_timing_summary -file "$report_dir/post_synth_timing_summary.rpt"
        report_utilization    -file "$report_dir/post_synth_util.rpt"
        
        if {$incremental_synth} {
            report_incremental_reuse -file "$report_dir/post_synth_incremental_reuse.rpt"
        }
    }
    if {$xviv_synth_generate_netlist} {
        file mkdir $netlist_dir
        write_verilog -force -mode funcsim                "$netlist_dir/post_synth_functional.v"
        write_verilog -force -mode timesim -sdf_anno true "$netlist_dir/post_synth_timing.v"
    }

    synth_post

    # ------------------------------------------------------------------
    # Logic Optimization
    # NOTE: Per Vivado Critical Warning [Project 1-948], opt_design 
    # must be run BEFORE read_checkpoint -incremental in non-project flow.
    # ------------------------------------------------------------------
    if {$run_opt_design} {
        xviv_stage "Logic Optimization"
        opt_design -directive $opt_directive
    }

    # ------------------------------------------------------------------
    # Incremental Implementation Setup
    # ------------------------------------------------------------------
    if {$incremental_impl} {
        set reference_post_route_dcp "$out_dir/post_route.dcp"

        if {[file exists $reference_post_route_dcp]} {
            xviv_stage "Applying Incremental Implementation Reference"
            read_checkpoint -incremental $reference_post_route_dcp
        } else {
            puts "INFO: No reference post_route DCP found at $reference_post_route_dcp. Running standard Implementation."
        }
    }

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------
    xviv_stage "Placement"
    
    place_design -directive $place_directive
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
    # Physical Optimization
    # ------------------------------------------------------------------
    if {$run_phys_opt} {
        xviv_stage "Physical Optimization"
        phys_opt_design -directive $phys_opt_directive
    }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    xviv_stage "Routing"
    
    route_design -directive $route_directive
    write_checkpoint -force "$out_dir/post_route.dcp"

    if {$xviv_synth_report_route} {
        file mkdir $report_dir
        xviv_stage "Post-routing reports"
        report_drc            -file "$report_dir/post_route_drc.rpt"
        report_methodology    -file "$report_dir/post_route_methodology.rpt"
        report_power          -file "$report_dir/post_route_power.rpt"
        report_route_status   -file "$report_dir/post_route_status.rpt"
        report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file "$report_dir/post_route_timing_summary.rpt"
        
        if {$incremental_impl} {
            report_incremental_reuse -file "$report_dir/post_impl_incremental_reuse.rpt"
        }
    }
    if {$xviv_synth_generate_netlist} {
        file mkdir $netlist_dir
        write_verilog -force -mode funcsim                "$netlist_dir/post_impl_functional.v"
        write_verilog -force -mode timesim -sdf_anno true "$netlist_dir/post_impl_timing.v"
    }

    route_post

    # ------------------------------------------------------------------
    # USR_ACCESS & Bitstream Generation
    # ------------------------------------------------------------------
    # set stem      "${top_module}"    ;# bare filename stem, no path
	file mkdir $run_dir
	set patch_file ""

	if { $sha_tag ne "" } {
		set_property BITSTREAM.CONFIG.USR_ACCESS 0x${usr_access_val} [current_design]
		puts "INFO: USR_ACCESS = 0x${usr_access_val}"

		if { $dirty } {
			set patch_file "$run_dir/${top_module}.patch"
			git_diff_to_file $patch_file
		}
	}
	

	xviv_stage "Generating bitstream"

	write_bitstream   -force                      "$run_dir/${top_module}.bit"
	write_hw_platform -fixed -include_bit -force  "$run_dir/${top_module}.xsa"

    bitstream_post

    # ------------------------------------------------------------------
    # Build manifest
    # ------------------------------------------------------------------
    xviv_write_manifest "$run_dir/build.json"               \
        vivado_version  [version -short]                    \
        part            $xviv_fpga_part                     \
        top             $top_module                         \
        sha_tag         $sha_tag                            \
        sha_short       $sha_short                          \
        dirty           [expr {$dirty ? "true" : "false"}]  \
        mode            "global"                            \
        diff            $patch_file      \
        bitstream       "$run_dir/${top_module}.bit"        \
        xsa             "$run_dir/${top_module}.xsa"        \
        elapsed         [xviv_elapsed]                      \
		timestamp       $xviv_iso_timestamp

	if { $sha_tag ne "" } {
		xviv_update_symlink "$out_dir/${top_module}.bit"   "$run_dir/${top_module}.bit"
		xviv_update_symlink "$out_dir/${top_module}.xsa"   "$run_dir/${top_module}.xsa"
		if { $dirty } {
			xviv_update_symlink "$out_dir/${top_module}.patch" $patch_file
		}
		xviv_update_symlink "$out_dir/build.json"   "$run_dir/build.json"
	}

    puts "INFO: Build complete - [xviv_elapsed]"
}
