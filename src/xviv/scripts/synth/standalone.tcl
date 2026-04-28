

proc cmd_synthesis_standalone { index } {
    global xviv_bd_xci_name_list xviv_bd_xci_path_list xviv_bd_leaf_ooc_synth_dir
    set xci_name  [lindex $xviv_bd_xci_name_list $index]
    set xci_path  [lindex $xviv_bd_xci_path_list $index]
    set target_dir $xviv_bd_leaf_ooc_synth_dir

	set dcp_path  "$target_dir/${xci_name}.dcp"
	set stub_path "$target_dir/${xci_name}.v"

    puts "set index $index"
    puts "set xci_name $xci_name"
    puts "set xci_path $xci_path"

    if { ![is_stale $xci_path $target_dir $xci_name] } {
        return
    }

    xviv_create_project "in_memory_project"
    read_ip $xci_path

    generate_target synthesis [get_files $xci_path] -quiet

    set_property TOP $xci_name [current_fileset]
    update_compile_order -fileset sources_1
    file mkdir $target_dir
    synth_design -mode out_of_context -top $xci_name -name "ooc_$xci_name"
    write_checkpoint -force $dcp_path
    write_verilog    -force -mode synth_stub $stub_path
}