import logging
import os
import stat

logger = logging.getLogger(__name__)

def _ensure_fifo(path: str) -> None:
	if os.path.exists(path):
		if not stat.S_ISFIFO(os.stat(path).st_mode):
			os.unlink(path)
			os.mkfifo(path)
	else:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		os.mkfifo(path)


def _fifo_send(path: str, command: str) -> None:
	try:
		fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
		with os.fdopen(fd, "w") as fh:
			fh.write(command + "\n")
	except OSError as e:
		logger.warning("FIFO send failed (%s) - is xsim running?", e)