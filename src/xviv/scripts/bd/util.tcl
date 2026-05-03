proc save_bd_tcl {} {
	global xviv_bd_state_tcl xviv_bd_name

	file mkdir [file dirname $xviv_bd_state_tcl]

	write_bd_tcl -force -no_project_wrapper $xviv_bd_state_tcl
	
	set path $xviv_bd_state_tcl
	set prefix "#${xviv_bd_name}\n\n"

	set f [open $path r]
    set data [read $f]
    close $f

    set start [string first "set bCheckIPsPassed" $data]
    set end   [string first "save_bd_design" $data]

    if {$start == -1 || $end == -1} {
        error "Could not find expected markers in state BD TCL"
    }

    set f [open $path w]
    puts $f [join $prefix "\n"]
    puts $f ""
    puts $f [string range $data $start [expr {$end - 1}]]
    close $f
}

rename save_bd_design _xviv_save_bd_design

proc save_bd_design {args} {
	_xviv_save_bd_design {*}$args

	save_bd_tcl
}

# proc override_save_bd_design {} {
# }

proc override_bd_exit {} {
	rename exit _xviv_exit
	proc exit {args} {
		# stop_gui

		# catch { cmd_generate_bd }

		_xviv_exit {*}$args
	}
}
