import json
import os
import sys
from xviv.config.project import XvivConfig


def get_bd_core_dict(cfg: XvivConfig, bd_name: str) -> list[dict]:
	bd_dir = os.path.join(cfg.bd_dir, bd_name)
	bd_file = os.path.join(bd_dir, f"{bd_name}.bd")
	bd_dict = {}

	if not os.path.exists(bd_file):
		sys.exit(f"ERROR: BD File not found: {bd_file}")

	with open(bd_file, 'r') as f:
		bd_dict = json.loads(f.read())

	if not bd_dict:
		sys.exit(f"ERROR: BD data read from {bd_file} is empty")

	resolved_components: list[dict] = []

	def _recursive_find(components_dict: dict) -> None:
		if not components_dict:
			return None

		for key, val in components_dict.items():
			if isinstance(val, dict):
				_components = val.get('components', None)

				if _components is not None:
					_recursive_find(_components)

				if 'vlnv' in val.keys() and not _components:
					vlnv = val['vlnv']
					xci_name = val['xci_name']
					xci_path = val['xci_path']
					inst_hier_path = val['inst_hier_path']

					if xci_path:
						xci_path = os.path.join(bd_dir, xci_path)

					resolved_components.append({
						'vlnv': vlnv,
						'xci_name': xci_name,
						'xci_file': xci_path,
						'inst_hier_path': inst_hier_path,
					})
	
	_recursive_find(bd_dict)

	return resolved_components