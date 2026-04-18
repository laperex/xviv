proc strip_bd_tcl {path prefix} {
    set f [open $path r]
    set data [read $f]
    close $f

    set start [string first "set bCheckIPsPassed" $data]
    set end   [string first "save_bd_design" $data]

    if {$start == -1 || $end == -1} {
        error "Could not find expected markers in exported BD TCL: $path\n\
            'set bCheckIPsPassed' found: [expr {$start != -1}]\n\
            'save_bd_design'      found: [expr {$end != -1}]"
    }

    set f [open $path w]
    puts $f [join $prefix "\n"]
    puts $f ""
    puts $f [string range $data $start [expr {$end - 1}]]
    close $f
}

proc save_bd_tcl {} {
	global xviv_bd_state_tcl xviv_bd_name

	file mkdir [file dirname $xviv_bd_state_tcl]

	write_bd_tcl -force -no_project_wrapper $xviv_bd_state_tcl
	strip_bd_tcl $xviv_bd_state_tcl "#${xviv_bd_name}\n\n"
}

proc override_save_bd_design {} {
	rename save_bd_design _xviv_save_bd_design
	proc save_bd_design {args} {
		_xviv_save_bd_design {*}$args

		save_bd_tcl
	}
}
