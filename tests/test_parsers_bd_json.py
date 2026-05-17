import json

import pytest

from xviv.parsers.bd_json import get_bd_core_list


def test_bd_json_exits_when_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        get_bd_core_list(str(tmp_path / "missing.json"))


def test_bd_json_exits_when_empty_data(tmp_path):
    bd_file = tmp_path / "bd.json"
    bd_file.write_text("{}")

    with pytest.raises(SystemExit):
        get_bd_core_list(str(bd_file))


def test_bd_json_parses_recursive_components_and_resolves_relative_xci(tmp_path):
    bd_file = tmp_path / "my_bd.json"
    payload = {
        "root": {
            "components": {
                "u0": {
                    "components": {
                        "u0_sub": {
                            "vlnv": "xilinx.com:ip:axi_gpio:2.0",
                            "xci_name": "axi_gpio_0",
                            "xci_path": "ip/axi_gpio_0/axi_gpio_0.xci",
                            "inst_hier_path": "u0/u0_sub",
                        }
                    }
                },
                "u1": {
                    "vlnv": "xilinx.com:ip:blk_mem_gen:8.4",
                    "xci_name": "blk_mem_gen_0",
                    "xci_path": "",
                    "inst_hier_path": "u1",
                },
            }
        }
    }
    bd_file.write_text(json.dumps(payload))

    out = get_bd_core_list(str(bd_file))

    assert (
        "axi_gpio_0",
        str(tmp_path / "ip/axi_gpio_0/axi_gpio_0.xci"),
        "xilinx.com:ip:axi_gpio:2.0",
        "u0/u0_sub",
    ) in out
    assert (
        "blk_mem_gen_0",
        "",
        "xilinx.com:ip:blk_mem_gen:8.4",
        "u1",
    ) in out
