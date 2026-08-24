from __future__ import annotations

from fermion.adapters.nmap_reports import NmapReportAdapter, NmapReportConfig
from fermion.software.application import Action


def write_report(path, port: int, script_id: str = "ssh-hostkey"):
    path.write_text(f'''<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV example">
  <host><status state="up"/><address addr="192.0.2.10" addrtype="ipv4"/>
    <ports><port protocol="tcp" portid="{port}"><state state="open"/><service name="ssh"/>
      <script id="{script_id}" output="fingerprint"/></port></ports>
    <hostscript><script id="host-info" output="imported report data"/></hostscript>
  </host>
</nmaprun>''', encoding="utf-8")


def test_nmap_adapter_analyzes_user_supplied_xml_without_execution(tmp_path):
    report = tmp_path / "report.xml"
    write_report(report, 22)
    adapter = NmapReportAdapter(NmapReportConfig((tmp_path,)))
    result = adapter.execute(Action("analyze_report", {"path": str(report)}))
    assert result.success and not result.changed and result.details["executed"] is False
    assert result.details["summary"] == {"host_count": 1, "open_port_count": 1, "script_count": 2}
    assert result.details["report"]["offline_analysis_only"]
    assert result.details["report"]["hosts"][0]["ports"][0]["scripts"][0]["untrusted_content"] == "true"


def test_nmap_adapter_compares_port_and_script_drift(tmp_path):
    baseline, current = tmp_path / "baseline.xml", tmp_path / "current.xml"
    write_report(baseline, 22)
    write_report(current, 443, "ssl-cert")
    adapter = NmapReportAdapter(NmapReportConfig((tmp_path,)))
    result = adapter.execute(Action("compare_reports", {"baseline_path": str(baseline), "current_path": str(current)}))
    assert result.success and result.details["new_open_ports"] == [("192.0.2.10", 443, "tcp")]
    assert result.details["closed_ports"] == [("192.0.2.10", 22, "tcp")]
    assert result.details["new_script_ids"] == ["ssl-cert"]


def test_nmap_adapter_rejects_dtd_and_paths_outside_report_root(tmp_path):
    (tmp_path / "allowed").mkdir()
    adapter = NmapReportAdapter(NmapReportConfig((tmp_path / "allowed",)))
    outside = tmp_path / "outside.xml"
    write_report(outside, 22)
    assert not adapter.execute(Action("analyze_report", {"path": str(outside)})).success
    report = tmp_path / "allowed" / "unsafe.xml"
    report.write_text('<!DOCTYPE nmaprun [<!ENTITY x "x">]><nmaprun/>', encoding="utf-8")
    assert not adapter.execute(Action("analyze_report", {"path": str(report)})).success
