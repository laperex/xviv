import shutil

from xviv.utils.log import DIM, RESET


def terminal_full_length_divider() -> str:
	width = shutil.get_terminal_size(fallback=(80, 24)).columns
	return "─" * width


def print_terminal_divider() -> None:
	print(f"{DIM}{terminal_full_length_divider()}{RESET}")
