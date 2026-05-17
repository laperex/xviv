from __future__ import annotations
import dataclasses
from typing import Callable, Any

@dataclasses.dataclass
class SectionSpec:
    toml_key: str
    add_method: str

_SECTIONS: list[SectionSpec] = []

def section(toml_key: str, add_method: str):
    _SECTIONS.append(SectionSpec(toml_key=toml_key, add_method=add_method))

def get_sections() -> list[SectionSpec]:
    return list(_SECTIONS)

section("fpga",       "add_fpga_cfg")
section("ip",         "add_ip_cfg")
section("wrapper",    "add_wrapper_cfg")
section("core",       "add_core_cfg")
section("bd",         "add_bd_cfg")
section("design",     "add_design_cfg")
section("simulation", "add_sim_cfg")
section("subcore",    "add_subcore_cfg")
section("synth",      "add_synth_cfg")
section("platform",   "add_platform_cfg")
section("app",        "add_app_cfg")
section("formal",     "add_formal_cfg")