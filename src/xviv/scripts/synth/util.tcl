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