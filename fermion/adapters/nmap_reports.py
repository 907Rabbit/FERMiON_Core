"""Offline-only analysis of user-supplied Nmap XML reports."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class NmapReportConfig:
    roots: tuple[Path, ...]
    max_file_size: int = 25 * 1024 * 1024
    max_script_output: int = 8_000


class NmapReportAdapter(ApplicationInterface):
    """Parse Nmap XML as untrusted offline data; scanning is intentionally absent."""

    _CAPABILITIES = (
        CapabilityDefinition("analyze_report", False, True, "Summarize a user-supplied Nmap XML report offline."),
        CapabilityDefinition("compare_reports", False, True, "Compare two user-supplied Nmap XML reports offline."),
    )

    def __init__(self, config: NmapReportConfig) -> None:
        self.config = config
        self.roots = tuple(root.resolve() for root in config.roots if root.exists())
        if not self.roots:
            raise ValueError("Nmap report adapter requires at least one existing report root")
        self._last_state: dict[str, Any] = {"last_path": None, "last_sha256": None}

    def _path(self, value: Any) -> Path:
        path = Path(str(value)).resolve()
        if not path.is_file() or path.suffix.lower() != ".xml" or not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError("report must be an existing .xml file inside configured report roots")
        if path.stat().st_size > self.config.max_file_size:
            raise ValueError(f"report exceeds the {self.config.max_file_size} byte limit")
        return path

    def _parse(self, value: Any) -> dict[str, Any]:
        path = self._path(value)
        data = path.read_bytes()
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("Nmap XML DTD/entity declarations are not permitted")
        try:
            root = ET.fromstring(data)
        except ET.ParseError as error:
            raise ValueError(f"invalid Nmap XML: {error}") from error
        if root.tag != "nmaprun":
            raise ValueError("XML document is not an Nmap report")
        digest = hashlib.sha256(data).hexdigest()
        hosts: list[dict[str, Any]] = []
        script_ids: set[str] = set()
        for host in root.findall("host"):
            address = next((node.get("addr") for node in host.findall("address") if node.get("addrtype") in {"ipv4", "ipv6"}), None)
            names = [node.get("name") for node in host.findall("hostnames/hostname") if node.get("name")]
            ports: list[dict[str, Any]] = []
            for port in host.findall("ports/port"):
                state = port.find("state")
                service = port.find("service")
                scripts = self._scripts(port.findall("script"), script_ids)
                ports.append({"protocol": port.get("protocol"), "port": int(port.get("portid", "0")),
                              "state": state.get("state") if state is not None else "unknown",
                              "service": service.get("name") if service is not None else None, "scripts": scripts})
            host_scripts = self._scripts(host.findall("hostscript/script"), script_ids)
            hosts.append({"address": address, "hostnames": names,
                          "state": (host.find("status").get("state") if host.find("status") is not None else "unknown"),
                          "ports": ports, "host_scripts": host_scripts})
        self._last_state = {"last_path": str(path), "last_sha256": digest}
        return {
            "path": str(path), "sha256": digest, "scanner": root.get("scanner"), "args": root.get("args"),
            "start": root.get("startstr") or root.get("start"), "hosts": hosts, "script_ids": sorted(script_ids),
            "offline_analysis_only": True, "untrusted_content": True,
        }

    def _scripts(self, nodes: list[ET.Element], script_ids: set[str]) -> list[dict[str, str]]:
        scripts = []
        for node in nodes:
            script_id = node.get("id", "unknown")
            script_ids.add(script_id)
            output = node.get("output", "")
            if len(output) > self.config.max_script_output:
                output = output[:self.config.max_script_output] + "… [truncated]"
            scripts.append({"id": script_id, "output": output, "untrusted_content": "true"})
        return scripts

    @staticmethod
    def _open_ports(report: dict[str, Any]) -> set[tuple[str | None, int, str | None]]:
        return {(host["address"], port["port"], port["protocol"])
                for host in report["hosts"] for port in host["ports"] if port["state"] == "open"}

    def observe(self) -> Observation:
        return Observation(time.time(), "nmap-reports", dict(self._last_state),
                           {"interface": "offline-xml-analysis", "execution": "disabled"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("nmap-reports", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "analyze_report":
                report = self._parse(action.arguments["path"])
                summary = {"host_count": len(report["hosts"]),
                           "open_port_count": len(self._open_ports(report)), "script_count": len(report["script_ids"])}
                return ActionResult(action.action_id, True, False, {"report": report, "summary": summary,
                                                                     "executed": False})
            baseline = self._parse(action.arguments["baseline_path"])
            current = self._parse(action.arguments["current_path"])
            baseline_ports, current_ports = self._open_ports(baseline), self._open_ports(current)
            return ActionResult(action.action_id, True, False, {
                "baseline": {"path": baseline["path"], "sha256": baseline["sha256"]},
                "current": {"path": current["path"], "sha256": current["sha256"]},
                "new_open_ports": sorted(current_ports - baseline_ports), "closed_ports": sorted(baseline_ports - current_ports),
                "new_script_ids": sorted(set(current["script_ids"]) - set(baseline["script_ids"])),
                "offline_analysis_only": True, "untrusted_content": True, "executed": False,
            })
        except (KeyError, OSError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(result.details.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed,
                                  "" if matches else "Nmap report analysis differs from expectation")

    def checkpoint(self) -> Checkpoint:
        state = dict(self._last_state)
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        expected = hashlib.sha256(json.dumps(checkpoint.logical_state, sort_keys=True).encode("utf-8")).hexdigest()
        if expected != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self.checkpoint().digest, "checkpoint digest mismatch")
        self._last_state = dict(checkpoint.logical_state)
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
