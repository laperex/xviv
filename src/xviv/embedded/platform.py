import logging
import os
import re
import glob
import sys

from xviv.config.model import ProjectConfig

logger = logging.getLogger(__name__)


def _find_elf(cfg: ProjectConfig, app_name: str) -> str:
    app_out_dir = cfg.get_app_dir(app_name)

    candidates = [
        os.path.join(app_out_dir, "Debug", f"{app_name}.elf"),
        os.path.join(app_out_dir, f"{app_name}.elf"),
    ]

    for c in candidates:
        if os.path.exists(c):
            return c

    hits = sorted(glob.glob(os.path.join(app_out_dir, "**", "*.elf"), recursive=True))

    if not hits:
        sys.exit(f"No ELF found in {app_out_dir}")

    return hits[0]


def _mb_tool(cfg: ProjectConfig, tool: str) -> str:
    return os.path.join(
        cfg.vivado.path, "gnu", "microblaze", "lin", "bin",
        f"microblaze-xilinx-elf-{tool}",
    )


def _transform_app_makefile(path: str):
    content = open(path, "rt").read()

    content = re.sub(
        r'(patsubst\s+%\.\w+,\s*)(?!build/)%.o',
        r'\1build/%.o',
        content
    )

    content = re.sub(
        r'(?<!build/)%.o(:%\.[cSs])',
        r'build/%.o\1',
        content
    )

    content = re.sub(
        r'(build/%.o:%\.[cSs]\n)(?!\t@mkdir)',
        r'\1\t@mkdir -p $(dir $@)\n',
        content
    )

    open(path, 'wt').write(content)