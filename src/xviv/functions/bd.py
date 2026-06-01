# import logging
# import os
# import re

# from xviv.config.params import BdCreateParams, EditParams, GenerateParams, IpCreateParams
# from xviv.config.project import XvivConfig
# from xviv.functions.core import _run_from_name_list
# from xviv.generator.tcl.commands import ConfigTclCommands

# logger = logging.getLogger(__name__)


# def parse_state_tcl_get_ip_vlnv(tcl_content: str) -> list[str]:
# 	if block_match := re.search(r'list_check_ips\s+"(.*?)"', tcl_content, re.DOTALL):
# 		raw_block = block_match.group(1)
# 		ip_list = re.findall(r"[\w.\-]+:[\w.\-]+:[\w.\-]+:[\d.]+", raw_block)

# 		return ip_list

# 	return []


# def _get_bd_list(cfg: XvivConfig, bd_name: str, recursive: bool = False):
# 	ip_list: list[str] = []

# 	bd_list: list[str] = [i.name for i in cfg._bd_list] if bd_name == "*" else [cfg.get_bd(bd_name).name]

# 	if recursive:
# 		for i in bd_list:
# 			bd_cfg = cfg.get_bd(i)

# 			if os.path.exists(bd_cfg.save_file):
# 				with open(bd_cfg.save_file, "rt") as f:
# 					for k in parse_state_tcl_get_ip_vlnv(f.read()):
# 						if ip_cfg := cfg._get_ip_cfg_optional_by_vlnv(k):
# 							if ip_cfg.name not in ip_list and not os.path.exists(ip_cfg.component_xml_file):
# 								ip_list.append(ip_cfg.name)

# 	return ip_list, bd_list


# def cmd_bd_create(cfg: XvivConfig, *, bd_name: str, params: BdCreateParams):
# 	ip_list, bd_list = _get_bd_list(cfg, bd_name=bd_name, recursive=True)

# 	if len(bd_list) > 1:
# 		if params.edit:
# 			logger.warning("For bd create with multiple jobs, disabled 'edit'")

# 		if isinstance(params.source_file, str):
# 			logger.warning("For bd create with multiple jobs, disabled 'source_file'")

# 		params.edit = False
# 		params.source_file = True

# 	if ip_list:
# 		_run_from_name_list(
# 			cfg,
# 			ip_list,
# 			lambda name: ConfigTclCommands(cfg).create_ip(name, IpCreateParams(edit=False, nogui=params.nogui)).build(),
# 			__name__,
# 		)

# 	_run_from_name_list(
# 		cfg,
# 		bd_list,
# 		lambda name: ConfigTclCommands(cfg).create_bd(name, params=params).build(),
# 		__name__,
# 	)


# def cmd_bd_edit(cfg: XvivConfig, *, bd_name: str, params: EditParams):
# 	if params.nogui:
# 		cfg.get_vivado().mode = "tcl"

# 	_run_from_name_list(
# 		cfg,
# 		[bd_name],
# 		lambda name: ConfigTclCommands(cfg).edit_bd(name, params=params).build(),
# 		__name__,
# 	)


# def cmd_bd_generate(cfg: XvivConfig, *, bd_name: str, params: GenerateParams):
# 	_, bd_list = _get_bd_list(cfg, bd_name=bd_name)

# 	_run_from_name_list(
# 		cfg,
# 		bd_list,
# 		lambda name: ConfigTclCommands(cfg).generate_bd(name, params=params).build(),
# 		__name__,
# 	)
