# =============================================================================
# IP creation sub-procs
#
# cmd_create_ip delegates each of its seven logical stages to a dedicated
# proc.  Each proc is self-contained, independently named in log output, and
# easier to read and test in isolation.
# All sub-procs are prefixed _xviv_ip_ to avoid polluting the global namespace.
# =============================================================================

# Stage 1: scaffold the default IP skeleton and open the edit project so that
# subsequent stages operate on [ipx::current_core].
proc _xviv_ip_scaffold {ip_vlnv ip_vid ip_dir proj_root} {
    global xviv_ip_vendor xviv_ip_library xviv_ip_name xviv_ip_version xviv_ip_repo

    create_peripheral $xviv_ip_vendor $xviv_ip_library $xviv_ip_name \
        $xviv_ip_version -dir $xviv_ip_repo
    add_peripheral_interface S00_AXI \
        -interface_mode slave -axi_type lite [ipx::find_open_core $ip_vlnv]
    generate_peripheral [ipx::find_open_core $ip_vlnv] -force
    write_peripheral    [ipx::find_open_core $ip_vlnv]

    ipx::edit_ip_in_project -upgrade true -name "edit_$ip_vid" \
        -directory "$proj_root/$ip_vid" "$ip_dir/component.xml"
    current_project "in_memory_project"
    close_project
    current_project "edit_$ip_vid"
}

# done
# Stage 2: remove the boilerplate AXI-Lite interface and the stub Verilog
# files that Vivado's peripheral generator always emits.
proc _xviv_ip_strip_scaffold {} {
    foreach ifc {S00_AXI S00_AXI_RST S00_AXI_CLK} {
        catch { ipx::remove_bus_interface $ifc [ipx::current_core] }
    }
    catch { ipx::remove_memory_map     S00_AXI            [ipx::current_core] }
    catch { ipx::remove_user_parameter C_S00_AXI_BASEADDR [ipx::current_core] }
    catch { ipx::remove_user_parameter C_S00_AXI_HIGHADDR [ipx::current_core] }

    foreach f [get_files -filter {FILE_TYPE == Verilog}] {
        remove_files $f
        file delete -force $f
    }
}

# done
# Stage 3: infer standard AXI-Stream and AXI-MM interfaces, then call the
# user hook for any additional custom inference.
proc _xviv_ip_infer_interfaces {} {
    puts "INFO: Inferring AXI-Stream interfaces"
#
    ipx::infer_bus_interfaces \
        xilinx.com:interface:axis_rtl:1.0  [ipx::current_core]
    puts "INFO: Inferring AXI-MM interfaces"

#
    ipx::infer_bus_interfaces \
        xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]

    ipx_infer_bus_interfaces

#
    update_compile_order -fileset sources_1
}

# Stage 4: expose every HDL parameter in the IP customisation GUI on Page 0,
# then call the user hook for reordering or grouping.
proc _xviv_ip_expose_params {} {
    foreach param [ipx::get_user_parameters -of_objects [ipx::current_core]] {
		set pname [get_property NAME $param]

		set pvalue [get_property VALUE $param]

		set display_name $pname

		set widget [ipgui::add_param \
			-name $pname \
			-display_name $display_name \
			-component [ipx::current_core] \
			-parent [ipgui::get_pagespec -name "Page 0" -component [ipx::current_core]]]

		set_property TOOLTIP "Parameter: $display_name" $widget

		# Print the name and value to the console
		puts "Name: $pname | Value: $pvalue"
	}
    ipx_add_params
}

# Stage 5: for every AXI-Lite slave interface, create a memory map and an
# address block, then associate the map with the interface.
proc _xviv_ip_wire_memory_maps {} {
    foreach ifc [ipx::get_bus_interfaces -of_objects [ipx::current_core]] {
        set ifc_name [get_property NAME $ifc]
        set ifc_mode [get_property BUS_TYPE_NAME $ifc]
        set ifc_intf [get_property INTERFACE_MODE $ifc]
        puts "INFO: Bus IF  $ifc_name \[$ifc_intf\]: $ifc_mode"

        if {$ifc_intf eq "slave" && [string match *axi_lite* $ifc_mode]} {
            ipx::add_memory_map "$ifc_name" [ipx::current_core]
            set ab [ipx::add_address_block "${ifc_name}_reg" [ipx::get_memory_maps "$ifc_name" -of_objects [ipx::current_core]]]
            ipx::add_address_block_parameter OFFSET_BASE_PARAM $ab
            ipx::add_address_block_parameter OFFSET_HIGH_PARAM $ab
            set_property usage register $ab
            set_property slave_memory_map_ref "$ifc_name" \
                [ipx::get_bus_interfaces "$ifc_name" \
                    -of_objects [ipx::current_core]]
        }
    }
    ipx_add_memory_map
    update_compile_order -fileset sources_1
}

# Stage 6: bump the core revision, regenerate GUI files, verify integrity,
# and persist the component.xml.
proc _xviv_ip_finalise {ip_vid} {
    set_property core_revision 2 [ipx::current_core]
    ipx::update_source_project_archive -component [ipx::current_core]
    ipx::create_xgui_files  [ipx::current_core]
    ipx::update_checksums   [ipx::current_core]
    ipx::check_integrity    [ipx::current_core]
    ipx::save_core          [ipx::current_core]
    puts "INFO: IP saved - $ip_vid"
}
