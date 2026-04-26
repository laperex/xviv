proc cmd_synthesis_standalone { vlnv xci_name xci_path inst_hier_path target_dir } {
    xviv_create_project "in_memory_project"
    puts "set vlnv $vlnv"
    puts "set xci_name $xci_name"
    puts "set xci_path $xci_path"
    puts "set inst_hier_path $inst_hier_path"

    read_ip $xci_path
    generate_target synthesis [get_files $xci_path] -quiet
    set_property TOP $xci_name [current_fileset]
    update_compile_order -fileset sources_1

    file mkdir $target_dir

    synth_design -mode out_of_context -top $xci_name -name "ooc_$xci_name"
    write_checkpoint -force "$target_dir/${xci_name}.dcp"
    write_verilog    -force -mode synth_stub "$target_dir/${xci_name}.v"
}