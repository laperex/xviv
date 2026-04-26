
proc cmd_synthesis_standalone { vlnv xci_name xci_path inst_hier_path target_dir } {
	xviv_create_project "in_memory_project"

	puts "set vlnv $vlnv"
	puts "set xci_name $xci_name"
	puts "set xci_path $xci_path"
	puts "set inst_hier_path $inst_hier_path"

	read_ip $xci_path
	generate_target synthesis [get_files $xci_path] -quiet
	synth_design -mode out_of_context -top $xci_name -name "ooc_$xci_name"
	
	file mkdir target_dir

	set stub_v "$target_dir/${xci_name}.v"
	set dcp_file "$target_dir/${xci_name}.dcp"
	
	write_checkpoint -force $dcp_file
	write_verilog   -force -mode synth_stub $stub_v
}