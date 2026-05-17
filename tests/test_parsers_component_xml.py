from xviv.parsers.component_xml import parser


def test_component_parser_returns_entry_for_valid_xml(tmp_path):
    xml = tmp_path / "component.xml"
    xml.write_text(
        """<?xml version="1.0"?>
<spirit:component xmlns:spirit="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"
                  xmlns:xilinx="http://www.xilinx.com">
  <spirit:vendor>xilinx.com</spirit:vendor>
  <spirit:library>ip</spirit:library>
  <spirit:name>fifo_generator</spirit:name>
  <spirit:version>13.2</spirit:version>
  <spirit:description>FIFO core</spirit:description>
  <spirit:vendorExtensions>
    <xilinx:coreExtensions>
      <xilinx:displayName>FIFO Generator</xilinx:displayName>
    </xilinx:coreExtensions>
  </spirit:vendorExtensions>
</spirit:component>
"""
    )

    entry = parser(str(xml))

    assert entry is not None
    assert entry.vlnv == "xilinx.com:ip:fifo_generator:13.2"
    assert entry.display_name == "FIFO Generator"
    assert entry.description == "FIFO core"


def test_component_parser_uses_name_as_display_name_if_missing_extension(tmp_path):
    xml = tmp_path / "component.xml"
    xml.write_text(
        """<?xml version="1.0"?>
<spirit:component xmlns:spirit="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009">
  <spirit:vendor>xilinx.com</spirit:vendor>
  <spirit:library>ip</spirit:library>
  <spirit:name>axi_gpio</spirit:name>
  <spirit:version>2.0</spirit:version>
  <spirit:description>GPIO</spirit:description>
</spirit:component>
"""
    )

    entry = parser(str(xml))
    assert entry is not None
    assert entry.display_name == "axi_gpio"


def test_component_parser_returns_none_when_required_fields_missing(tmp_path):
    xml = tmp_path / "component.xml"
    xml.write_text(
        """<?xml version="1.0"?>
<spirit:component xmlns:spirit="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009">
  <spirit:vendor>xilinx.com</spirit:vendor>
  <spirit:library>ip</spirit:library>
  <spirit:name>axi_gpio</spirit:name>
</spirit:component>
"""
    )

    assert parser(str(xml)) is None


def test_component_parser_returns_none_on_malformed_xml(tmp_path):
    xml = tmp_path / "component.xml"
    xml.write_text("<spirit:component")
    assert parser(str(xml)) is None
