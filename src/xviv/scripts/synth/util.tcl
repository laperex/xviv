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

proc is_stale { xci_path target_dir xci_name } {
    set dcp  "$target_dir/${xci_name}.dcp"
    set stub "$target_dir/${xci_name}.v"

    if { ![file exists $dcp] || ![file exists $stub] } {
        puts "\[is_stale\] $xci_name: output missing, rebuild needed"
        return 1
    }

    set xci_mtime  [file mtime $xci_path]
    set dcp_mtime  [file mtime $dcp]
    set stub_mtime [file mtime $stub]

    if { $xci_mtime > $dcp_mtime || $xci_mtime > $stub_mtime } {
        puts "\[is_stale\] $xci_name: xci newer than outputs, rebuild needed"
        return 1
    }

    puts "\[is_stale\] $xci_name: up to date, skipping"
    return 0
}