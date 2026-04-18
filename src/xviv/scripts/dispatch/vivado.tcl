# =============================================================================
# scripts/xviv.tcl  -  Unified Vivado TCL dispatcher
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
#   open_dcp     <dcp_file>             - open a checkpoint in the GUI
# =============================================================================

set script_dir [file dirname [file dirname [file normalize [info script]]]]

source "$script_dir/ip/utils.tcl"
source "$script_dir/ip/create.tcl"
source "$script_dir/ip/edit.tcl"

source "$script_dir/reports/utilisation.tcl"

source "$script_dir/core/create.tcl"
source "$script_dir/core/edit.tcl"

source "$script_dir/bd/util.tcl"
source "$script_dir/bd/create.tcl"
source "$script_dir/bd/edit.tcl"
source "$script_dir/bd/export.tcl"
source "$script_dir/bd/generate.tcl"

source "$script_dir/synth/open_dcp.tcl"
source "$script_dir/synth/synthesis.tcl"

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
            xviv_die "Required config variable \$$v is missing or empty. Check that generate_config_tcl emits it for this command."
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
        xviv_die "FPGA part '$xviv_fpga_part' is not in the installed Vivado part catalog. Check [fpga] part in project.toml."
    }

    create_project -part $xviv_fpga_part -in_memory $name

    if {[info exists xviv_board_part] && $xviv_board_part ne ""} {
        if {[info exists xviv_board_repo] && $xviv_board_repo ne ""} {
            set_param board.repoPaths [list $xviv_board_repo]
        }
        set_property board_part $xviv_board_part [current_project]
    }

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
    global xviv_rtl_files

    if {[info exists xviv_rtl_files] && [llength $xviv_rtl_files] > 0} {
        add_files -scan_for_includes $xviv_rtl_files
        set design_added 1
    } else  {
        puts "WARN: No RTL source files were added to the project."
    }

    update_compile_order -fileset sources_1
}

proc xviv_add_xdc_sources {} {
    global xviv_xdc_files
	
    if {[info exists xviv_xdc_files] && [llength $xviv_xdc_files] > 0} {
        add_files -fileset constrs_1 $xviv_xdc_files
    } else {
        puts "WARN: No XDC constraints files were added to the project."
	}
	
    update_compile_order -fileset sources_1
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
        # puts "DEBUG: No-op stub installed for optional hook: $name"
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
# Dispatch
# =============================================================================
switch -- $_cmd {
    create_ip   { cmd_create_ip }
    edit_ip     { cmd_edit_ip [lindex $::argv 2] }
    
	create_bd   { cmd_create_bd }
    edit_bd     { cmd_edit_bd [lindex $::argv 2] }
    generate_bd { cmd_generate_bd }
    export_bd   { cmd_export_bd [lindex $::argv 2] }

	create_core { cmd_create_core }

	synthesis   {
        if {$::argc < 3} {
            xviv_die "synthesis requires <top_module>"
        }
		# TODO: better versioning for .bit and .xsa
        # sha_tag is argv[3], computed by Python _git_sha_tag().
        # Defaults to "unknown" when called without a sha_tag for
        # backward compatibility with any direct Vivado invocations.
        set _sha_tag [expr {$::argc > 3 ? [lindex $::argv 3] : ""}]
        cmd_synthesis [lindex $::argv 2] $_sha_tag
    }
	synth_bd {
        if {$::argc < 5} {
            xviv_die "synth_bd requires <bd_wrapper_top> <sha_tag>"
        }
        cmd_synth_bd \
            [lindex $::argv 2] \
            [lindex $::argv 3] \
            [lindex $::argv 4]
    }
    open_dcp    {
        if {$::argc < 3} {
            xviv_die "open_dcp requires <dcp_file>"
        }
        cmd_open_dcp [lindex $::argv 2] [lindex $::argv 3]
    }
    default {
        puts stderr "XVIV ERROR: Unknown command '$_cmd'"
        puts stderr "Valid commands:"
        puts stderr "  create_ip   edit_ip"
        puts stderr "  create_bd   edit_bd   generate_bd   export_bd"
        exit 1
    }
}