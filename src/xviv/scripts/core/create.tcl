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
    # fuzzy fallback — search for suffix match
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
proc cmd_create_core {} {
	global xviv_core_vlnv xviv_core_name xviv_core_dir

	xviv_create_project "in_memory_project"
	
	file mkdir $xviv_core_dir
	
	set xci_file "$xviv_core_dir/$xviv_core_name/${xviv_core_name}.xci"

	create_ip -vlnv $xviv_core_vlnv -module_name $xviv_core_name -dir $xviv_core_dir
	generate_target {instantiation_template} [get_files $xci_file]

	generate_target all [get_files  $xci_file]
	catch { config_ip_cache -export [get_ips -all $xviv_core_name] }

	# synth_ip [get_ips -all $xviv_core_name]
	# set_property -dict [list CLKOUT2_USED {true} MMCM_CLKOUT1_DIVIDE {10} NUM_OUT_CLKS {2} CLKOUT2_JITTER {130.958} CLKOUT2_PHASE_ERROR {98.575}] [get_ips clk_wiz_5]
}


# create_ip -vlnv user.org:user:ip_rgb_to_hsv:1.0 -module_name ip_rgb_to_hsv_3 -dir ./build/core
# -> /home/laperex/Programming/image_processing/build/core/ip_rgb_to_hsv_3/ip_rgb_to_hsv_3.xci
# generate_target {instantiation_template} [get_files /home/laperex/Programming/image_processing/build/core/ip_rgb_to_hsv_3/ip_rgb_to_hsv_3.xci]
# -> INFO: [IP_Flow 19-1686] Generating 'Instantiation Template' target for IP 'ip_rgb_to_hsv_3'...
# generate_target all [get_files  /home/laperex/Programming/image_processing/build/core/ip_rgb_to_hsv_3/ip_rgb_to_hsv_3.xci]

# create_ip -vlnv xilinx.com:ip:clk_wiz:6.0 -module_name clk_wiz_5 -dir ./build/core
# generate_target {instantiation_template} [get_files /home/laperex/Programming/image_processing/build/core/clk_wiz_5/clk_wiz_5.xci]
# generate_target all [get_files  /home/laperex/Programming/image_processing/build/core/clk_wiz_5/clk_wiz_5.xci]
# catch { config_ip_cache -export [get_ips -all clk_wiz_5] }
# export_ip_user_files -of_objects [get_files /home/laperex/Programming/image_processing/build/core/clk_wiz_5/clk_wiz_5.xci] -no_script -sync -force -quiet
# synth_ip [get_ips -all clk_wiz_5]


# create_ip -vlnv user.org:user:ip_rgb_to_hsv:1.0 -module_name ip_rgb_to_hsv_7 -dir ./build/core
# generate_target {instantiation_template} [get_files /home/laperex/Programming/image_processing/build/core/ip_rgb_to_hsv_7/ip_rgb_to_hsv_7.xci]
# generate_target all [get_files  /home/laperex/Programming/image_processing/build/core/ip_rgb_to_hsv_7/ip_rgb_to_hsv_7.xci]
# catch { config_ip_cache -export [get_ips -all ip_rgb_to_hsv_7] }
# synth_ip [get_ips -all ip_rgb_to_hsv_7]

# search by keyword
# help customize
# help ip

# # list all commands matching a pattern
# lsearch -all -inline [info commands] "*ip*"
# lsearch -all -inline [info commands] "*custom*"

# # include namespace commands (like ipgui::)
# namespace children ::

# Window opened or changed: Window { id: 142, title: Some("Vivado 2025.2"), app_id: Some("Vivado"), pid: Some(2158713), workspace_id: Some(4), is_focused: true, is_floating: false, is_urgent: false, layout: WindowLayout { pos_in_scrolling_layout: Some((2, 1)), tile_size: (3.0, 1561.0), window_size: (1, 1559), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) }, focus_timestamp: Some(Timestamp { secs: 249727, nanos: 921222713 }) }
# Window layouts changed: [(6, WindowLayout { pos_in_scrolling_layout: Some((3, 1)), tile_size: (2550.0, 1561.0), window_size: (2548, 1559), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) }), (7, WindowLayout { pos_in_scrolling_layout: Some((4, 1)), tile_size: (2550.0, 1561.0), window_size: (2548, 1559), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) }), (8, WindowLayout { pos_in_scrolling_layout: Some((5, 1)), tile_size: (2550.0, 1561.0), window_size: (2548, 1559), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) })]
# Window opened or changed: Window { id: 142, title: Some("Customize IP"), app_id: Some("Vivado"), pid: Some(2158713), workspace_id: Some(4), is_focused: true, is_floating: false, is_urgent: false, layout: WindowLayout { pos_in_scrolling_layout: Some((2, 1)), tile_size: (3.0, 1561.0), window_size: (1, 1559), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) }, focus_timestamp: Some(Timestamp { secs: 249727, nanos: 921222713 }) }
# Window layouts changed: [(142, WindowLayout { pos_in_scrolling_layout: Some((2, 1)), tile_size: (1002.0, 902.0), window_size: (1000, 900), tile_pos_in_workspace_view: None, window_offset_in_tile: (1.0, 1.0) })]
# Workspace 4: active window changed to Some(141)