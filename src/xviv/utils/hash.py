import hashlib
import os

def sha512_file(file) -> str:
	if os.path.exists(file):
		h = hashlib.sha512()

		with open(file, "rb") as f:
			for chunk in iter(lambda: f.read(1024 * 1024), b""):
				h.update(chunk)

		return h.hexdigest()

	return ""