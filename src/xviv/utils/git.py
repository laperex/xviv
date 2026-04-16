import subprocess

def _git_sha_tag() -> tuple[str, bool, str]:
	try:
		sha = subprocess.check_output(
			["git", "rev-parse", "--short=7", "HEAD"],
			stderr=subprocess.DEVNULL,
		).decode().strip()
	except Exception:
		return "unknown", False, "unknown"

	try:
		status = subprocess.check_output(
			["git", "status", "--porcelain"],
			stderr=subprocess.DEVNULL,
		).decode().strip()
		dirty = len(status) > 0
	except Exception:
		dirty = False

	tag = f"{sha}_dirty" if dirty else sha
	return sha, dirty, tag