import glob
import logging
import os
import sys

logger = logging.getLogger(__name__)

def resolve_globs(patterns: list[str], base: str) -> list[str]:
	files: list[str] = []
	for pat in patterns:
		full_pat = os.path.join(base, pat)
		hits = sorted(glob.glob(full_pat, recursive=True))
		files.extend(os.path.abspath(h) for h in hits if os.path.isfile(h))
	return files

def is_stale(srcfile: str, dstfile: str) -> bool:
	if not os.path.exists(dstfile):
		return False

	if not os.path.exists(srcfile):
		sys.exit(f"[stale_checker] ERROR: the path {srcfile} does not exist!")

	if os.path.getmtime(srcfile) > os.path.getmtime(dstfile):
		logger.info(f"[stale_checker] {srcfile}: {dstfile} newer than outputs, rebuild needed")
		return True

	logger.info(f"[stale_checker] {srcfile}: up to date, skipping")
	return False