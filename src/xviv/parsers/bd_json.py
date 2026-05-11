import json
import os
import sys


def get_bd_core_list(bd_file: str) -> list[tuple[str, str, str, str]]:
	bd_dict = {}
	if not os.path.exists(bd_file):
		sys.exit(f"ERROR: BD File not found: {bd_file}")

	with open(bd_file, 'r') as f:
		bd_dict = json.loads(f.read())

	if not bd_dict:
		sys.exit(f"ERROR: BD data read from {bd_file} is empty")

	resolved_components: list[tuple[str, str, str, str]] = []

	def _recursive_find(components_dict: dict) -> None:
		if not components_dict:
			return None

		for _, val in components_dict.items():
			if isinstance(val, dict):
				_components = val.get('components', None)

				if _components is not None:
					_recursive_find(_components)

				if 'vlnv' in val.keys() and not _components:
					vlnv = val['vlnv']
					xci_name = val['xci_name']
					xci_file = val['xci_path']
					inst_hier_path = val['inst_hier_path']

					if xci_file:
						xci_file = os.path.join(os.path.dirname(bd_file), xci_file)

					
					resolved_components.append(
						(xci_name, xci_file, vlnv, inst_hier_path)
					)

	_recursive_find(bd_dict)

	return resolved_components