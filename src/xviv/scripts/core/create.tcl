proc find_prop_prefix {ip bare_name} {
    set candidates [list \
        "CONFIG.$bare_name" \
        $bare_name \
    ]
    set all_props [list_property [get_ips $ip]]
    foreach candidate $candidates {
        if {[lsearch $all_props $candidate] != -1} {
            return $candidate
        }
    }

    foreach p $all_props {
        if {[string match "*.$bare_name" $p] || $p eq $bare_name} {
            return $p
        }
    }
    return ""
}

proc apply_ip_config {ip raw_list} {
    set dict {}
    foreach {key val} $raw_list {
        set prop [find_prop_prefix $ip $key]
        if {$prop eq ""} {
            puts "SKIP (not found): $key"
            continue
        }
        if {[get_property IS_READ_ONLY [get_property_definition $prop [get_ips $ip]]]} {
            puts "SKIP (read-only): $prop"
            continue
        }
        lappend dict $prop $val
    }
    if {[llength $dict] > 0} {
        set_property -dict $dict [get_ips $ip]
        puts "Applied: $dict"
    }
}

# =============================================================================
# Command: create_core
# =============================================================================
proc cmd_create_core { gui } {
    global xviv_core_vlnv xviv_core_name xviv_core_dir

    xviv_require_vars xviv_core_vlnv xviv_core_name xviv_core_dir

    puts "INFO: Creating catalog core"
    puts "INFO:   VLNV : $xviv_core_vlnv"
    puts "INFO:   Name : $xviv_core_name"
    puts "INFO:   Dir  : $xviv_core_dir"

    file mkdir $xviv_core_dir

    xviv_create_project "in_memory_project"

	file delete -force $xviv_core_dir/$xviv_core_name
    set xci_file [create_ip \
        -vlnv        $xviv_core_vlnv  \
        -module_name $xviv_core_name  \
        -dir         $xviv_core_dir   \
    ]

    puts "INFO: XCI: $xci_file"

    xviv_stage "Generating output products"
    generate_target all [get_files $xci_file]

	set out_file [file normalize "[file dirname $xci_file]/${xviv_core_name}.sim.f"]
	set fd [open $out_file w]

	foreach f [get_files \
			-of_objects [get_ips $xviv_core_name] \
			-filter {USED_IN =~ "*simulation*"}] {
		puts $fd [file normalize $f]
	}

	close $fd
	puts "INFO: Wrote sim fileset $out_file"
    puts "INFO: Core creation complete - [xviv_elapsed]"
}
