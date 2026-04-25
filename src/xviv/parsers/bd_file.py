import json
import os
import sys
from xviv.config.model import ProjectConfig


def get_bd_component_dict(cfg: ProjectConfig, bd_name: str) -> dict:
	bd_dir = os.path.join(cfg.bd_dir, bd_name)
	bd_file = os.path.join(bd_dir, f"{bd_name}.bd")
	bd_dict = {}

	if not os.path.exists(bd_file):
		sys.exit(f"ERROR: BD File not found: {bd_file}")

	with open(bd_file, 'r') as f:
		bd_dict = json.loads(f.read())

	if not bd_dict:
		sys.exit(f"ERROR: BD data read from {bd_file} is empty")

	resolved_components: list = []

	def _recursive_find(components_dict: dict) -> None:
		if not components_dict:
			return None

		for key, val in components_dict.items():
			if isinstance(val, dict):
				_recursive_find(val.get('components', {}))

				if 'vlnv' in val.keys():
					vlnv = val['vlnv']
					xci_name = val['xci_name']
					xci_path = val['xci_path']
					inst_hier_path = val['inst_hier_path']
					
					if xci_path:
						xci_path = os.path.join(bd_dir, xci_path)

					resolved_components.append({
						'vlnv': vlnv,
						'xci_name': xci_name,
						'xci_path': xci_path,
						'inst_hier_path': inst_hier_path,
					})
	
	_recursive_find(bd_dict)

	print(json.dumps(resolved_components, indent=4))

	return {}