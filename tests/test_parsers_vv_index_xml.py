from xviv.parsers.vv_index_xml import parser


def test_vv_index_parser_returns_empty_for_missing_file(tmp_path):
    out = parser(str(tmp_path / "missing.xml"))
    assert out == {}


def test_vv_index_parser_returns_empty_for_invalid_xml(tmp_path):
    xml = tmp_path / "vv_index.xml"
    xml.write_text("<root><IP>")
    assert parser(str(xml)) == {}


def test_vv_index_parser_parses_flags_and_metadata(tmp_path):
    xml = tmp_path / "vv_index.xml"
    xml.write_text(
        """<Catalog>
  <IP>
    <VLNV value="xilinx.com:ip:axi_gpio:2.0"/>
    <DisplayName value="AXI GPIO"/>
    <Description value="General purpose IO core"/>
    <HideInGui value="true"/>
    <BoardDependent value="true"/>
    <DesignToolContexts>
      <DesignTool value="IPI"/>
    </DesignToolContexts>
    <Families>
      <Family name="zynq">
        <Part status="Not-Supported"/>
      </Family>
      <Family name="versal">
        <Part status="Supported"/>
      </Family>
    </Families>
    <UpgradesFrom>
      <Upgrade value="xilinx.com:ip:axi_gpio:1.0"/>
      <Upgrade value="xilinx.com:ip:axi_gpio:1.1"/>
    </UpgradesFrom>
  </IP>
</Catalog>
"""
    )

    out = parser(str(xml))
    assert "xilinx.com:ip:axi_gpio:2.0" in out
    e = out["xilinx.com:ip:axi_gpio:2.0"]
    assert e.display_name == "AXI GPIO"
    assert e.description == "General purpose IO core"
    assert e.hidden is True
    assert e.board_dependent is True
    assert e.ipi_only is True
    assert e.unsupported_families == frozenset({"zynq"})
    assert e.upgrades_from == (
        "xilinx.com:ip:axi_gpio:1.0",
        "xilinx.com:ip:axi_gpio:1.1",
    )


def test_vv_index_parser_skips_invalid_vlnv_entries(tmp_path):
    xml = tmp_path / "vv_index.xml"
    xml.write_text(
        """<Catalog>
  <IP><VLNV value=""/></IP>
  <IP><VLNV value="not:four:parts"/></IP>
  <IP><DisplayName value="No VLNV"/></IP>
  <IP><VLNV value="xilinx.com:ip:valid:1.0"/></IP>
</Catalog>
"""
    )

    out = parser(str(xml))
    assert list(out.keys()) == ["xilinx.com:ip:valid:1.0"]
