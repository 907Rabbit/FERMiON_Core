"""Loopback lifecycle for the vendored God's Eye View globe.

The globe is third-party Cesium/OSINT UI. FERMiON may start and stop a
localhost Vite process; it does not import GEV source, proxy its feeds, or
treat globe output as authority.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELATIVE_APP = Path("fermion") / "God's Eye View" / "gods-eye-view"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_PORT = 4173


def _default_state_dir() -> Path:
    preferred = Path("G:/tmp/fermion-control/gods-eye-view")
    if Path("G:/").exists():
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    root = Path(os.environ.get("TEMP", ".")) / "fermion-gev"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class GodsEyeViewStatus:
    configured: bool
    tree_present: bool
    node_present: bool
    dependencies_installed: bool
    running: bool
    healthy: bool
    pid: int | None
    url: str
    host: str
    port: int


class GodsEyeViewRuntime:
    """Own a localhost-only Vite process for the vendored globe."""

    def __init__(self, source_root: Path | None = None, state_dir: Path | None = None, *,
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        if host not in LOOPBACK_HOSTS:
            raise ValueError("God's Eye View may bind only to localhost.")
        self.source_root = (source_root or PROJECT_ROOT).resolve()
        self.tree = self.source_root / RELATIVE_APP
        self.host = "127.0.0.1" if host == "localhost" else host
        self.port = int(port)
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid God's Eye View port")
        self.state_dir = Path(state_dir) if state_dir is not None else _default_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path = self.state_dir / "gods-eye-view.pid"
        self.stdout_path = self.state_dir / "gods-eye-view.stdout.log"
        self.stderr_path = self.state_dir / "gods-eye-view.stderr.log"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    @property
    def vite_js(self) -> Path:
        return self.tree / "node_modules" / "vite" / "bin" / "vite.js"

    def node_executable(self) -> str | None:
        return shutil.which("node")

    def health(self, timeout: float = 2.0) -> bool:
        request = urllib.request.Request(self.url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return 200 <= int(response.status) < 400
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def _port_open(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.3):
                return True
        except OSError:
            return False

    def status(self, *, network: bool = False) -> GodsEyeViewStatus:
        pid = self._pid()
        running = self._process_exists(pid)
        healthy = self.health(timeout=0.6) if network else False
        return GodsEyeViewStatus(
            configured=self.tree.is_dir(),
            tree_present=self.tree.is_dir(),
            node_present=self.node_executable() is not None,
            dependencies_installed=self.vite_js.is_file(),
            running=healthy or running,
            healthy=healthy,
            pid=pid if running else None,
            url=self.url,
            host=self.host,
            port=self.port,
        )

    def start(self, wait_seconds: float = 120.0) -> GodsEyeViewStatus:
        if not self.tree.is_dir():
            raise FileNotFoundError(f"God's Eye View tree is missing: {self.tree}")
        self._ensure_dependencies()
        if self.health():
            return self.status(network=True)
        if self._port_open():
            raise RuntimeError(f"port {self.port} is occupied by a process that is not God's Eye View")
        node = self.node_executable()
        if not node:
            raise RuntimeError("Node.js was not found on PATH")
        command = [node, str(self.vite_js.resolve()), "--host", self.host, "--port", str(self.port),
                   "--strictPort"]
        environment = os.environ.copy()
        environment["HOST"] = self.host
        environment["PORT"] = str(self.port)
        environment["BROWSER"] = "none"
        environment["PUPPETEER_SKIP_DOWNLOAD"] = "1"
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        stdout = self.stdout_path.open("a", encoding="utf-8")
        stderr = self.stderr_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command, cwd=str(self.tree), env=environment, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True, creationflags=creationflags,
            )
        finally:
            stdout.close()
            stderr.close()
        self.pid_path.write_text(str(process.pid), encoding="ascii")
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.health():
                return self.status(network=True)
            if process.poll() is not None:
                raise RuntimeError(
                    f"God's Eye View exited with code {process.returncode}; see {self.stderr_path}"
                )
            time.sleep(0.5)
        raise TimeoutError(f"God's Eye View did not become healthy within {wait_seconds:g} seconds")

    def stop(self) -> GodsEyeViewStatus:
        pid = self._pid()
        if pid is not None and self._process_exists(pid):
            if os.name == "nt":
                name = self._windows_process_name(pid)
                if name.lower() not in {"node.exe", "node"}:
                    raise RuntimeError(f"refusing to stop PID {pid}: expected node.exe, found {name or 'unknown'}")
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, text=True, check=False)
            else:
                os.kill(pid, signal.SIGTERM)
            for _ in range(40):
                if not self._process_exists(pid):
                    break
                time.sleep(0.25)
        self.pid_path.unlink(missing_ok=True)
        return self.status(network=True)

    def open_browser(self) -> GodsEyeViewStatus:
        current = self.status(network=True)
        if not current.healthy:
            raise RuntimeError("God's Eye View is not healthy on localhost; start it first.")
        webbrowser.open(self.url)
        return current

    def _ensure_dependencies(self) -> None:
        if self.vite_js.is_file():
            return
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found on PATH")
        environment = os.environ.copy()
        environment["PUPPETEER_SKIP_DOWNLOAD"] = "1"
        environment["PUPPETEER_SKIP_CHROMIUM_DOWNLOAD"] = "1"
        completed = subprocess.run(
            [npm, "install", "--ignore-scripts"],
            cwd=str(self.tree),
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0 or not self.vite_js.is_file():
            raise RuntimeError(f"npm install failed for God's Eye View: {completed.stderr[-2000:]}")

    def _pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _process_exists(pid: int | None) -> bool:
        if pid is None:
            return False
        if os.name == "nt":
            return GodsEyeViewRuntime._windows_process_name(pid) != ""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _windows_process_name(pid: int) -> str:
        completed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                   capture_output=True, text=True)
        if completed.returncode != 0 or "No tasks" in completed.stdout:
            return ""
        rows = list(csv.reader(io.StringIO(completed.stdout)))
        return rows[0][0] if rows and rows[0] else ""


class GodsEyeViewAdapter(ApplicationInterface):
    """status is read-only; start/stop/open mutate the local globe process only."""

    _CAPABILITIES = (
        CapabilityDefinition("status", False, True, "Report the localhost globe without launching it."),
        CapabilityDefinition("start", True, True, "Start the vendored globe on 127.0.0.1 only."),
        CapabilityDefinition("stop", True, True, "Stop the FERMiON-managed globe process."),
        CapabilityDefinition("open", True, True, "Open the localhost globe in the system browser."),
    )

    def __init__(self, source_root: Path | None = None, state_dir: Path | None = None) -> None:
        self._runtime = GodsEyeViewRuntime(source_root=source_root, state_dir=state_dir)

    def observe(self) -> Observation:
        return Observation(time.time(), "gods_eye_view", asdict(self._runtime.status(network=False)),
                           {"interface": "loopback-lifecycle"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("gods_eye_view", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "status":
                return ActionResult(action.action_id, True, False, asdict(self._runtime.status(network=True)))
            if action.operation == "start":
                return ActionResult(action.action_id, True, True, asdict(self._runtime.start()))
            if action.operation == "stop":
                return ActionResult(action.action_id, True, True, asdict(self._runtime.stop()))
            return ActionResult(action.action_id, True, True, asdict(self._runtime.open_browser()))
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if result.details.get("host") not in {None, "127.0.0.1", "localhost", "::1"}:
            return VerificationResult(False, expected_effect, observed, "God's Eye View must remain on localhost")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self.observe().state
        digest = hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        running = bool(checkpoint.logical_state.get("running"))
        try:
            if running:
                self._runtime.start()
            else:
                self._runtime.stop()
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            return RollbackResult(False, checkpoint.checkpoint_id, checkpoint.digest, str(error))
        return RollbackResult(True, checkpoint.checkpoint_id, self.checkpoint().digest)
