import shutil


def terminal_full_length_divider() -> str:
	width = shutil.get_terminal_size(fallback=(80, 24)).columns
	return "─" * width
