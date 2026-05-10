import glob
import hashlib
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

def is_stale(srcfile: str, dstfile: str, exit_on_fail=True) -> bool:
	if not os.path.exists(dstfile):
		return True

	if not os.path.exists(srcfile):
		if exit_on_fail:
			sys.exit(f"[stale_checker] ERROR: the path {srcfile} does not exist!")
		else:
			return True

	if os.path.getmtime(srcfile) > os.path.getmtime(dstfile):
		logger.info(f"[stale_checker] {srcfile}: {dstfile} newer than outputs, rebuild needed")
		return True

	logger.info(f"[stale_checker] {srcfile}: up to date, skipping")
	return False

def combined_checksum(files: list[str], algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    for path in files:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    return h.hexdigest()

def assert_file_exists(path: str) -> None:
    assert os.path.exists(path), f"File not found: {path}"