import glob
import os

def resolve_globs(patterns: list[str], base: str) -> list[str]:
	files: list[str] = []
	for pat in patterns:
		full_pat = os.path.join(base, pat)
		hits = sorted(glob.glob(full_pat, recursive=True))
		files.extend(os.path.abspath(h) for h in hits if os.path.isfile(h))
	return files
