
import json
import os
import subprocess
import sys

import tomllib

from xviv.config import model
from xviv.config.project import XvivConfig
from xviv.utils.tools import find_vivado_dir_path


def resolve_config_completer(prefix, parsed_args, **kwargs) -> str:
	return resolve_config(getattr(parsed_args, "config", ""))

def resolve_config(explicit: str) -> str:
	if os.path.exists(explicit):
		return explicit
	for candidate in ("project.cue", "project.toml"):
		if os.path.exists(candidate):
			return candidate
	sys.exit("ERROR: neither project.cue nor project.toml found in current directory.")

def load_config(path: str) -> XvivConfig:
	return (
		XvivConfig(path, 'build', [
			'/home/laperex/Programming/Vivado/vivado-boards/new/board_files'
		])
		.add_vivado_cfg(
			path=find_vivado_dir_path()
		)

		.add_fpga_cfg(
			name='pynq',
			fpga_part = "xc7z020clg400-1",
			board_part = "tul.com.tw:pynq-z2:part0:1.0"
		)
		.add_fpga_cfg(
			name = 'custom',
			fpga_part = "xc7a200tfbg484-1"
		)
		
		.add_ip_cfg(
			name = 'ip_inrange',
			vendor = 'laperex.org',
			library = 'custom_axi_ip',
			version = '1.0',

			sources = [
				'srcs/rtl/axi_types.sv',
				'srcs/rtl/axi_lite_slave.sv',

				'srcs/rtl/cv_types.sv',
				'srcs/rtl/cv_inrange.sv',

				'srcs/rtl/ip_inrange.sv'
			]
		)
		.add_ip_cfg(
			name = 'ip_rgb_to_hsv',
			vendor = 'laperex.org',
			library = 'custom_axi_ip',
			version = '1.0',

			sources = [
				'srcs/rtl/axi_types.sv',
				'srcs/rtl/axi_lite_slave.sv',

				'srcs/rtl/cv_types.sv',
				'srcs/rtl/cv_rgb_to_hsv.sv',

				'srcs/rtl/ip_rgb_to_hsv.sv'
			]
		)
		
		.add_core_cfg(
			name = 'clk_wiz',
			vlnv = 'clk_wiz:6.0'
		)
		.add_core_cfg(
			name = 'ip_inrange',
			vlnv = 'ip_inrange:1.0'
		)
		
		.add_bd_cfg(
			name = 'bd_image_processing'
		)
		.add_bd_cfg(
			name = 'bd_blaze_test',
			fpga_ref = 'custom'
		)

		.add_synth_cfg(
			bd_name = 'bd_blaze_test'
		)
	)