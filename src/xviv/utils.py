import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def _setup_logging(log_file: str = "", level_console=logging.INFO) -> None:
    root = logging.getLogger("xviv")
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level_console)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        fh = logging.FileHandler(log_file, mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)


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


def _atomic_symlink(target: str, link_path: str) -> None:
    link_dir = os.path.dirname(link_path)
    tmp_link = os.path.join(link_dir, f".tmp_{os.path.basename(link_path)}")
    rel_target = os.path.relpath(target, link_dir)
    if os.path.lexists(tmp_link):
        os.unlink(tmp_link)
    os.symlink(rel_target, tmp_link)
    os.replace(tmp_link, link_path)


def _shell_env(source_file: str) -> dict[str, str]:
    if not os.path.isfile(source_file):
        sys.exit(f"ERROR: Vitis settings not found: {source_file}")

    result = subprocess.run(
        ["bash", "-c", f'source "{source_file}" && env -0'],
        capture_output=True,
        text=True,
        check=True,
    )

    env = {}
    for entry in result.stdout.split("\0"):
        if "=" in entry:
            k, _, v = entry.partition("=")
            env[k] = v
    return env
