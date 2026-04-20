# =============================================================================
# Command: generate_core
# =============================================================================
proc cmd_generate_core {} {
    global current_project xviv_core_vlnv xviv_core_name xviv_core_dir
	
    xviv_require_vars xviv_core_name xviv_core_dir

	set xci_file "$xviv_core_dir/$xviv_core_name/${xviv_core_name}.xci"

	if {![file exists $xci_file]} {
        xviv_die "XCI file not found: $xci_file"
    }

	if { [catch {current_project} project] } {
		xviv_create_project "in_memory_project"

		puts "INFO: Generate Core"
		puts "INFO:   Name : $xviv_core_name"
		puts "INFO:   XCI  : $xci_file"
	}

	if { [get_files -quiet $xci_file] eq "" } {
		read_ip $xci_file
	}

	# -------------------------------

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
	puts "INFO: Generate Core Complete - [xviv_elapsed]"
}

# start_ip_gui     ;# open customize/re-customize IP GUI
# create_ip        ;# create IP instance
# delete_ip_run    ;# delete IP run
# validate_ip      ;# validate IP
# upgrade_ip       ;# upgrade IP to newer version
# report_ip_status ;# report status of all IPs
# update_ip_catalog ;# refresh IP catalog
# config_ip_cache  ;# configure IP cache
# synth_ip         ;# synthesize IP out-of-context
# generate_target  ;# generate output products
# export_ip_user_files ;# export IP user files
# import_ip        ;# import existing .xci
# read_ip          ;# read .xci in non-project mode
# copy_ip          ;# copy IP instance
# convert_ips      ;# convert legacy IP
# write_ip_tcl     ;# dump create_ip + set_property script
# get_ips          ;# query IP instances
# get_ipdefs       ;# query IP catalog definitions