"""Local-only FERMiON operations dashboard.

The dashboard intentionally has no third-party web dependency.  It exposes a
small, local control surface for the frozen reference specimen, regression
checks, and the opt-in desktop gate.  It never accepts arbitrary shell input.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_MARKER = "windows_ui"
LLM_CONTROL_OPERATIONS = frozenset({"reference", "regression", "live_gate", "llm_stop"})


@dataclass
class DashboardJob:
    """A single whitelisted operation started from the local dashboard."""

    identifier: str
    operation: str
    command: tuple[str, ...]
    started_at: float = field(default_factory=time.time)
    status: str = "running"
    return_code: int | None = None
    output: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "operation": self.operation,
            "command": list(self.command),
            "started_at": self.started_at,
            "status": self.status,
            "return_code": self.return_code,
            "output": self.output,
        }


class DashboardController:
    """Owns the dashboard's operation allow-list and in-memory job history."""

    def __init__(self, project_root: Path = PROJECT_ROOT, python: str = sys.executable) -> None:
        self.project_root = project_root
        self.python = python
        self.jobs: dict[str, DashboardJob] = {}
        self._lock = threading.Lock()
        self._runtime = None
        self._control_plane = None

    @staticmethod
    def _temp_root() -> Path:
        preferred = Path("G:/tmp/fermion-dashboard")
        if preferred.drive and Path(preferred.drive + "/").exists():
            preferred.mkdir(parents=True, exist_ok=True)
            return preferred
        return Path(os.environ.get("TEMP", ".")) / "fermion-dashboard"

    def command_for(self, operation: str, *, live_confirmed: bool = False) -> tuple[str, ...]:
        """Return a fixed command; unsupported operations are rejected."""
        if operation == "reference":
            return (self.python, "-m", "fermion", "reference")
        if operation == "regression":
            temp = self._temp_root() / f"regression-{uuid.uuid4().hex}"
            return (self.python, "-m", "pytest", "-q", "-m", "not windows_ui",
                    "-p", "no:cacheprovider", "--basetemp", str(temp))
        if operation == "live_gate":
            if not live_confirmed:
                raise PermissionError("Live UI execution requires explicit confirmation.")
            temp = self._temp_root() / f"live-{uuid.uuid4().hex}"
            return (self.python, "-m", "pytest", "-p", "no:cacheprovider",
                    "--basetemp", str(temp), "-m", LIVE_MARKER, "-v")
        if operation in {"llm_start", "llm_stop"}:
            return ("internal", "llama-server", operation.removeprefix("llm_"))
        raise ValueError(f"Unsupported dashboard operation: {operation}")

    def runtime(self):
        """Create the loopback model runtime lazily, keeping its logs off C:."""
        if self._runtime is None:
            from .adapters.llama_cpp import LlamaCppConfig, LlamaServerRuntime

            config = LlamaCppConfig.from_file(self.project_root / "fermion.local.json")
            self._runtime = LlamaServerRuntime(config, state_dir=self._temp_root() / "llama")
        return self._runtime

    def control_plane(self):
        if self._control_plane is None:
            from .cognitive.runtime_bootstrap import shared_control_plane
            self._control_plane = shared_control_plane(self.project_root)
        return self._control_plane

    def start(self, operation: str, *, live_confirmed: bool = False) -> DashboardJob:
        command = self.command_for(operation, live_confirmed=live_confirmed)
        job = DashboardJob(uuid.uuid4().hex, operation, command)
        with self._lock:
            self.jobs[job.identifier] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job

    def _run(self, job: DashboardJob) -> None:
        if job.operation in {"llm_start", "llm_stop"}:
            try:
                status = self.runtime().start() if job.operation == "llm_start" else self.runtime().stop()
                job.output = json.dumps({"running": status.running, "healthy": status.healthy,
                                         "model_path": status.model_path}, indent=2)
                job.return_code = 0
                job.status = "passed"
            except Exception as error:
                job.status = "failed"
                job.output = f"{type(error).__name__}: {error}"
            return
        environment = os.environ.copy()
        temp = str(self._temp_root())
        environment["TEMP"] = temp
        environment["TMP"] = temp
        if job.operation == "live_gate":
            environment["FERMION_LIVE_UI"] = "1"
        try:
            completed = subprocess.run(
                job.command,
                cwd=self.project_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300 if job.operation != "live_gate" else 90,
            )
            job.return_code = completed.returncode
            job.output = completed.stdout[-30_000:]
            job.status = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as error:
            job.status = "timed_out"
            job.output = (error.stdout or "")[-30_000:]
        except Exception as error:  # display failure without expanding capability
            job.status = "failed"
            job.output = f"{type(error).__name__}: {error}"

    def status(self) -> dict[str, Any]:
        disk = shutil.disk_usage(self.project_root)
        model: dict[str, Any]
        try:
            runtime_status = self.runtime().status()
            model = {"configured": runtime_status.configured, "running": runtime_status.running,
                     "healthy": runtime_status.healthy, "path": runtime_status.model_path}
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            model = {"configured": False, "running": False, "healthy": False, "error": str(error)}
        return {
            "core": {"parameters": 193, "state": "frozen reference"},
            "project": str(self.project_root),
            "live_ui_armed": os.environ.get("FERMION_LIVE_UI") == "1",
            "disk": {"free_gb": round(disk.free / 1024 ** 3, 2), "drive": self.project_root.drive},
            "model": model,
            "safety": {
                "ownership": "dynamic / fail closed",
                "mutations": "EXCLUSIVE or SHARED_AUTHORIZED only",
                "live_gate": "explicit confirmation required",
            },
        }

    def get_job(self, identifier: str) -> DashboardJob | None:
        with self._lock:
            return self.jobs.get(identifier)

    def assistant(self, message: str, *, execute_authorized: bool = False,
                  live_confirmed: bool = False) -> dict[str, Any]:
        """Ask the loopback model for one bounded FERMiON control decision.

        The model can name only an operation from ``LLM_CONTROL_OPERATIONS``.
        The controller, not model text, validates and launches that operation.
        """
        message = message.strip()
        if not message:
            raise ValueError("Enter a question for the local model.")
        if len(message) > 4_000:
            raise ValueError("Message is limited to 4,000 characters.")
        runtime = self.runtime()
        if not runtime.health(timeout=0.5):
            raise RuntimeError("Local model is not running. Start it from the Model panel first.")
        config = runtime.config
        context = json.dumps({"canonical_core": "193 parameters / frozen",
                              "ownership": "dynamic; fail closed",
                              "execution": "only dashboard-approved operations may run"})
        tools = ", ".join(sorted(LLM_CONTROL_OPERATIONS))
        prompt = (
            "You are the local FERMiON controller interface. You may request at most one registered "
            "FERMiON operation when the user explicitly asks for it. Registered operations are: "
            f"{tools}. You cannot invent commands, bypass ownership, or grant approval. "
            "The live_gate operation requires a separate live confirmation and is never a substitute for "
            "the ownership checks. Return JSON only with keys reply (string) and operation (one registered "
            "operation or null). Be concise and state uncertainty.\n"
            f"System context: {context}\nUser: {message}\nAssistant:"
        )
        payload = json.dumps({"prompt": prompt, "temperature": config.temperature,
                              "n_predict": config.max_tokens}).encode("utf-8")
        request = urllib.request.Request(config.endpoint or "", payload,
                                         {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                data = json.loads(response.read())
        except urllib.error.URLError as error:
            raise RuntimeError(f"Local model request failed: {error.reason}") from error
        raw_reply = str(data.get("content") or data.get("choices", [{}])[0].get("text", "")).strip()
        if not raw_reply:
            raise RuntimeError("Local model returned an empty response.")
        reply, operation = self._parse_control_reply(raw_reply)
        result: dict[str, Any] = {"reply": reply, "operation": operation, "executed": False}
        if operation == "live_gate" and not live_confirmed:
            result["requires_live_confirmation"] = True
            return result
        if operation and execute_authorized:
            job = self.start(operation, live_confirmed=live_confirmed)
            result.update({"executed": True, "job": job.as_dict()})
        return result

    def agent(self, message: str, *, execute: bool = False) -> dict[str, Any]:
        """Plan and, only when directly authorized, execute adapter operations."""
        message = message.strip()
        if not message:
            raise ValueError("Describe the program task you want FERMiON to perform.")
        if len(message) > 4_000:
            raise ValueError("Message is limited to 4,000 characters.")
        runtime = self.runtime()
        if not runtime.health(timeout=0.5):
            raise RuntimeError("Local model is not running. Start it from the Model panel first.")
        plane = self.control_plane()
        manifest = json.dumps(plane.manifest(), sort_keys=True)
        from .cognitive.tool_bridge import ToolCallParseError, parse_qwen_bridge_plan, qwen_bridge_instruction
        bridge_instruction = qwen_bridge_instruction(plane.manifest())
        prompt = (
            "You are FERMiON's program-control planner. Convert the user's request into a single JSON object, "
            "with no prose or markdown. Use only the applications and capabilities in the manifest. "
            "Never invent a program, command, file path, or capability. Each action must contain application, "
            "operation, arguments, and optionally expected_effect. Use requires_approval=true whenever any "
            "action changes state. If the request cannot be done using the manifest, return an empty actions array "
            "and explain why in summary.\n"
            f"Manifest: {manifest}\n{bridge_instruction}\nUser request: {message}\nJSON or bridge markup:"
        )
        config = runtime.config
        payload = json.dumps({"prompt": prompt, "temperature": 0.1,
                              "n_predict": config.max_tokens}).encode("utf-8")
        request = urllib.request.Request(config.endpoint or "", payload,
                                         {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                data = json.loads(response.read())
        except urllib.error.URLError as error:
            raise RuntimeError(f"Local model request failed: {error.reason}") from error
        raw = str(data.get("content") or data.get("choices", [{}])[0].get("text", "")).strip()
        try:
            encoded_plan = self._extract_json_object(raw)
        except ValueError:
            try:
                encoded_plan = json.dumps(parse_qwen_bridge_plan(raw))
            except ToolCallParseError as error:
                raise ValueError("The local model did not return a valid FERMiON JSON or bridge plan.") from error
        plan = plane.parse_plan(message, encoded_plan)
        validation = plane.validate(plan)
        output: dict[str, Any] = {"plan": asdict(plan), "validation": asdict(validation), "executed": False}
        if execute and validation.valid:
            report = plane.execute(plan, approved=True)
            output.update({"executed": True, "report": report.to_dict()})
        return output

    def bridge(self, markup: str, *, execute: bool = False) -> dict[str, Any]:
        """Validate an OpenClaw text bridge proposal through FERMiON's control plane."""
        from .cognitive.tool_bridge import ToolCallParseError, parse_qwen_bridge_plan
        if not markup.strip():
            raise ValueError("Paste one FERMiON bridge plan.")
        try:
            payload = parse_qwen_bridge_plan(markup)
        except ToolCallParseError as error:
            raise ValueError(f"Invalid FERMiON bridge plan: {error}") from error
        plane = self.control_plane()
        plan = plane.parse_plan("OpenClaw bridge proposal", json.dumps(payload))
        validation = plane.validate(plan)
        result: dict[str, Any] = {"plan": asdict(plan), "validation": asdict(validation), "executed": False}
        if execute and validation.valid:
            result.update({"executed": True, "report": plane.execute(plan, approved=True).to_dict()})
        return result

    @staticmethod
    def _extract_json_object(text: str) -> str:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return json.dumps(value)
        raise ValueError("The local model did not return a JSON control plan.")

    @staticmethod
    def _parse_control_reply(raw_reply: str) -> tuple[str, str | None]:
        decoder = json.JSONDecoder()
        for index, character in enumerate(raw_reply):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(raw_reply[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                operation = payload.get("operation")
                operation = operation if operation in LLM_CONTROL_OPERATIONS else None
                reply = str(payload.get("reply", "")).strip() or raw_reply
                return reply, operation
        return raw_reply, None


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FERMiON Console</title><style>
:root{--bg:#0b1017;--panel:#111a25;--panel2:#0d1520;--line:#263446;--text:#e8eef6;--muted:#91a1b5;--cyan:#66e4de;--amber:#ffbf6a;--red:#ff8282;--green:#86e5a1}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.shell{max-width:1260px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid var(--line);padding-bottom:20px}.brand{font-size:24px;letter-spacing:.16em;font-weight:700}.brand small{display:block;font-size:11px;letter-spacing:.1em;color:var(--cyan);margin-top:4px}.stamp{color:var(--muted);font-size:12px}.grid{display:grid;grid-template-columns:1.06fr .94fr;gap:18px;margin-top:18px}.panel{background:var(--panel);border:1px solid var(--line);padding:20px}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.13em}.value{font-size:26px;margin:4px 0 0}.ok{color:var(--green)}.warn{color:var(--amber)}.rule{height:1px;background:var(--line);margin:18px 0}.statusline{display:flex;gap:16px;flex-wrap:wrap}.statusline div{min-width:140px}.operations{margin-top:18px}.row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;border-top:1px solid var(--line);padding:15px 0}.row:first-child{border-top:0}.row p{margin:4px 0;color:var(--muted);font-size:13px}button{border:1px solid #3c5a70;color:var(--text);background:#182838;border-radius:3px;padding:9px 13px;font:inherit;font-weight:600;cursor:pointer}button:hover{border-color:var(--cyan);color:var(--cyan)}button.live{border-color:#725333;background:#2a2118}button:disabled{opacity:.5;cursor:not-allowed}.notice{margin-top:14px;color:var(--amber);font-size:12px}.check{display:flex;gap:8px;align-items:flex-start;color:var(--muted);font-size:12px;margin:12px 0}input{accent-color:var(--amber)}pre{margin:12px 0 0;min-height:360px;max-height:520px;overflow:auto;padding:14px;background:#091018;border:1px solid var(--line);color:#c6d4e3;font:12px/1.5 Cascadia Code,Consolas,monospace;white-space:pre-wrap}.history{margin-top:12px;color:var(--muted);font-size:12px}@media(max-width:760px){.grid{grid-template-columns:1fr}.top{align-items:start;gap:12px;flex-direction:column}.shell{padding:15px}}
</style></head><body><main class="shell"><header class="top"><div class="brand">FERMiON<small>Local control console / 127.0.0.1 only</small></div><div class="stamp" id="project">Loading local state…</div></header><section class="grid"><div><section class="panel"><div class="label">Canonical core</div><div class="value"><span id="parameters">—</span> parameters <span class="ok">/ frozen</span></div><div class="rule"></div><div class="statusline"><div><span class="label">Ownership</span><br><span id="ownership">—</span></div><div><span class="label">Mutations</span><br><span id="mutations">—</span></div><div><span class="label">Project disk</span><br><span id="disk">—</span></div></div></section><section class="panel operations"><div class="label">Operations</div><div class="row"><div><strong>Reference specimen</strong><p>Verify the canonical 193-parameter execution.</p></div><button onclick="run('reference')">Run reference</button></div><div class="row"><div><strong>Deterministic regression</strong><p>Runs non-live tests with cache disabled and temporary data on G: when available.</p></div><button onclick="run('regression')">Run tests</button></div><div class="row"><div><strong>Live Notepad gate</strong><p>May open Notepad and type only after exclusive target ownership is verified.</p><label class="check"><input id="confirm" type="checkbox">I understand this starts the opt-in desktop experiment.</label></div><button class="live" onclick="run('live_gate')">Run live gate</button></div><div class="notice">Live mutations remain vetoed unless ownership is EXCLUSIVE or SHARED_AUTHORIZED.</div></section></div><section class="panel"><div class="label">Run inspector</div><div class="value" id="runTitle">No run selected</div><pre id="output">Select a safe operation. Results stay local to this computer.</pre><div class="history" id="history"></div></section></section></main><script>
let active;const output=document.getElementById('output'), title=document.getElementById('runTitle');
async function state(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('parameters').textContent=s.core.parameters;document.getElementById('project').textContent=s.project;document.getElementById('ownership').textContent=s.safety.ownership;document.getElementById('mutations').textContent=s.safety.mutations;document.getElementById('disk').textContent=s.disk.drive+' '+s.disk.free_gb+' GB free'}
async function run(operation){if(operation==='live_gate'&&!document.getElementById('confirm').checked){output.textContent='Live gate not started: explicit confirmation is required.';return}const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation,live_confirmed:document.getElementById('confirm').checked})});const data=await r.json();if(!r.ok){output.textContent=data.error;return}active=data.id;title.textContent='Running: '+operation;output.textContent='$ '+data.command.join(' ')+'\n\nRunning…';poll()}
async function poll(){if(!active)return;const j=await fetch('/api/jobs/'+active).then(r=>r.json());output.textContent='$ '+j.command.join(' ')+'\n\n'+(j.output||'Running…');document.getElementById('history').textContent='Status: '+j.status+(j.return_code===null?'':' · exit '+j.return_code);if(j.status==='running')setTimeout(poll,600);else title.textContent='Completed: '+j.operation+' / '+j.status}
state();</script></body></html>'''


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FERMiON Console</title>
<style>
:root{--bg:#091018;--panel:#101a26;--panel2:#0c141e;--line:#273649;--text:#e9eff7;--muted:#91a3b8;--cyan:#66e4de;--amber:#ffc06a;--red:#ff8989;--green:#86e5a1}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.shell{max-width:1320px;margin:auto;padding:26px}.top{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid var(--line);padding-bottom:19px}.brand{font-size:24px;letter-spacing:.16em;font-weight:700}.brand small{display:block;font-size:11px;letter-spacing:.1em;color:var(--cyan);margin-top:4px}.stamp{color:var(--muted);font-size:12px;max-width:50%;text-align:right}.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;margin-top:18px}.panel{background:var(--panel);border:1px solid var(--line);padding:20px}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.13em}.value{font-size:24px;margin:4px 0 0}.ok{color:var(--green)}.warn{color:var(--amber)}.rule{height:1px;background:var(--line);margin:18px 0}.statusline{display:flex;gap:16px;flex-wrap:wrap}.statusline div{min-width:135px}.operations{margin-top:18px}.row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;border-top:1px solid var(--line);padding:15px 0}.row:first-child{border-top:0}.row p{margin:4px 0;color:var(--muted);font-size:13px}button{border:1px solid #3c5a70;color:var(--text);background:#182838;border-radius:3px;padding:9px 13px;font:inherit;font-weight:600;cursor:pointer}button:hover{border-color:var(--cyan);color:var(--cyan)}button.live{border-color:#725333;background:#2a2118}button:disabled{opacity:.5;cursor:not-allowed}.notice{margin-top:14px;color:var(--amber);font-size:12px}.check{display:flex;gap:8px;align-items:flex-start;color:var(--muted);font-size:12px;margin:12px 0}input{accent-color:var(--amber)}pre{margin:12px 0 0;min-height:280px;max-height:480px;overflow:auto;padding:14px;background:#081019;border:1px solid var(--line);color:#c6d4e3;font:12px/1.5 Cascadia Code,Consolas,monospace;white-space:pre-wrap}.history{margin-top:12px;color:var(--muted);font-size:12px}.model{margin-top:18px;border-left:3px solid var(--cyan);padding-left:14px}.model .value{font-size:17px}textarea{width:100%;min-height:96px;resize:vertical;margin-top:12px;padding:11px;border:1px solid var(--line);border-radius:3px;background:var(--panel2);color:var(--text);font:14px/1.4 inherit}.assistantActions{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:10px}.hint{font-size:12px;color:var(--muted)}.reply{min-height:130px}.badge{font-size:11px;padding:3px 7px;border:1px solid var(--line);color:var(--muted);margin-left:8px}details{margin-top:12px;color:var(--muted)}summary{cursor:pointer;color:var(--cyan)}details pre{min-height:120px;max-height:320px}@media(max-width:760px){.grid{grid-template-columns:1fr}.top{align-items:start;gap:12px;flex-direction:column}.stamp{max-width:100%;text-align:left}.shell{padding:15px}}
</style></head><body><main class="shell"><header class="top"><div class="brand">FERMiON<small>Local control console / 127.0.0.1 only</small></div><div class="stamp" id="project">Loading local state…</div></header>
<section class="grid"><div><section class="panel"><div class="label">Canonical core</div><div class="value"><span id="parameters">—</span> parameters <span class="ok">/ frozen</span></div><div class="rule"></div><div class="statusline"><div><span class="label">Ownership</span><br><span id="ownership">—</span></div><div><span class="label">Mutations</span><br><span id="mutations">—</span></div><div><span class="label">Project disk</span><br><span id="disk">—</span></div></div><div class="model"><span class="label">Local language model</span><div class="value"><span id="modelState">Checking…</span><span class="badge" id="modelName">—</span></div><p class="hint">The model plans through registered adapters; FERMiON validates, executes, verifies, and audits the result.</p><button onclick="run('llm_start')">Start model</button> <button onclick="run('llm_stop')">Stop model</button></div></section>
<section class="panel operations"><div class="label">Verified operations</div><div class="row"><div><strong>Reference specimen</strong><p>Verify the canonical 193-parameter execution.</p></div><button onclick="run('reference')">Run reference</button></div><div class="row"><div><strong>Deterministic regression</strong><p>Runs non-live tests with cache disabled and temporary data on G: when available.</p></div><button onclick="run('regression')">Run tests</button></div><div class="row"><div><strong>Live Notepad gate</strong><p>May open Notepad and type only after exclusive target ownership is verified.</p><label class="check"><input id="confirm" type="checkbox">I understand this starts the opt-in desktop experiment.</label></div><button class="live" onclick="run('live_gate')">Run live gate</button></div><div class="notice">Live mutations remain vetoed unless ownership is EXCLUSIVE or SHARED_AUTHORIZED.</div></section></div>
<div><section class="panel"><div class="label">FERMiON program agent</div><div class="value">Describe what you want done <span class="badge">plan → validate → execute</span></div><textarea id="message" placeholder="Example: Create notes.txt containing the project status, then append a dated next step and open it in Notepad."></textarea><label class="check"><input id="authorize" type="checkbox">Approve execution of the validated plan for this request.</label><div class="assistantActions"><span class="hint">LLM plans only through registered adapters; every action is audited and verified.</span><button onclick="runAgent()">Plan / execute</button></div><pre class="reply" id="reply">Start the local model. FERMiON will answer in plain language; open the details only when you need the plan and audit record.</pre><details><summary>Plan &amp; audit details</summary><pre id="details">No plan yet.</pre></details><details><summary>OpenClaw bridge plan</summary><textarea id="bridgeMarkup" placeholder="Paste one &lt;tool_call&gt;&lt;function=fermion_plan&gt;… bridge plan from Crestodian."></textarea><label class="check"><input id="bridgeAuthorize" type="checkbox">Approve execution of this validated bridge plan.</label><button onclick="runBridge()">Validate / execute bridge plan</button><pre id="bridgeDetails">No bridge plan yet.</pre></details></section>
<section class="panel" style="margin-top:18px"><div class="label">Run inspector</div><div class="value" id="runTitle">No run selected</div><pre id="output">Select a verified operation. Results stay local to this computer.</pre><div class="history" id="history"></div></section></div></section></main>
<script>
let active;const output=document.getElementById('output'),title=document.getElementById('runTitle');
async function state(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('parameters').textContent=s.core.parameters;document.getElementById('project').textContent=s.project;document.getElementById('ownership').textContent=s.safety.ownership;document.getElementById('mutations').textContent=s.safety.mutations;document.getElementById('disk').textContent=s.disk.drive+' '+s.disk.free_gb+' GB free';const m=s.model;document.getElementById('modelState').textContent=m.healthy?'ready':m.running?'starting':'stopped';document.getElementById('modelState').className=m.healthy?'ok':m.running?'warn':'';document.getElementById('modelName').textContent=m.path?m.path.split('\\').pop():'not configured'}
async function run(operation){if(operation==='live_gate'&&!document.getElementById('confirm').checked){output.textContent='Live gate not started: explicit confirmation is required.';return}const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation,live_confirmed:document.getElementById('confirm').checked})});const data=await r.json();if(!r.ok){output.textContent=data.error;return}active=data.id;title.textContent='Running: '+operation;output.textContent='$ '+data.command.join(' ')+'\n\nRunning…';poll()}
async function poll(){if(!active)return;const j=await fetch('/api/jobs/'+active).then(r=>r.json());output.textContent='$ '+j.command.join(' ')+'\n\n'+(j.output||'Running…');document.getElementById('history').textContent='Status: '+j.status+(j.return_code===null?'':' · exit '+j.return_code);if(j.status==='running')setTimeout(poll,700);else{title.textContent='Completed: '+j.operation+' / '+j.status;state()}}
function agentSummary(data){const actions=data.plan?.actions||[],names=actions.map(a=>a.application+'.'+a.operation);if(!data.validation?.valid)return 'I could not validate that plan: '+(data.validation.reasons||[]).join('; ');if(!data.executed)return 'Plan ready: '+(data.plan.summary||names.join(', ')||'no action')+'. Check approval to execute it.';const records=data.report?.records||[];const listed=records.flatMap(r=>r.result?.details?.programs||[]);if(listed.length)return 'I can run: '+listed.map(p=>p.alias.replace(/_/g,' ')).join(', ')+'. No program was opened.';const failed=records.find(r=>!r.verification?.success);if(failed)return 'The plan stopped because '+(failed.verification.reason||failed.result.error||'verification failed')+'. FERMiON rolled back reversible changes.';return 'Completed '+records.length+' action'+(records.length===1?'':'s')+': '+names.join(', ')+'. All recorded checks passed.'}
async function runAgent(){const box=document.getElementById('message'),reply=document.getElementById('reply'),details=document.getElementById('details'),message=box.value.trim();if(!message)return;reply.textContent='FERMiON is building a typed plan…';const r=await fetch('/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,execute:document.getElementById('authorize').checked})});const data=await r.json();if(!r.ok){reply.textContent='Request not sent: '+data.error;return}reply.textContent=agentSummary(data);details.textContent=JSON.stringify(data,null,2);if(data.executed){title.textContent='FERMiON plan executed';output.textContent='Plan completed. Expand “Plan & audit details” for the full trace.'}}
async function runBridge(){const box=document.getElementById('bridgeMarkup'),details=document.getElementById('bridgeDetails'),markup=box.value.trim();if(!markup)return;details.textContent='FERMiON is validating the bridge plan…';const r=await fetch('/api/bridge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markup,execute:document.getElementById('bridgeAuthorize').checked})});const data=await r.json();details.textContent=r.ok?JSON.stringify(data,null,2):'Bridge rejected: '+data.error;if(data.executed){title.textContent='FERMiON bridge plan executed';output.textContent='Bridge plan completed. Inspect bridge details for the audit trace.'}}
state();
</script></body></html>'''


def make_handler(controller: DashboardController):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/status":
                self._json(HTTPStatus.OK, controller.status())
            elif self.path.startswith("/api/jobs/"):
                job = controller.get_job(self.path.rsplit("/", 1)[-1])
                self._json(HTTPStatus.OK, job.as_dict()) if job else self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown job."})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/api/run", "/api/assistant", "/api/agent", "/api/bridge"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/assistant":
                    self._json(HTTPStatus.OK, controller.assistant(
                        str(payload.get("message", "")),
                        execute_authorized=bool(payload.get("execute_authorized")),
                        live_confirmed=bool(payload.get("live_confirmed")),
                    ))
                    return
                if self.path == "/api/agent":
                    self._json(HTTPStatus.OK, controller.agent(
                        str(payload.get("message", "")), execute=bool(payload.get("execute"))
                    ))
                    return
                if self.path == "/api/bridge":
                    self._json(HTTPStatus.OK, controller.bridge(
                        str(payload.get("markup", "")), execute=bool(payload.get("execute"))
                    ))
                    return
                job = controller.start(str(payload.get("operation", "")), live_confirmed=bool(payload.get("live_confirmed")))
                self._json(HTTPStatus.ACCEPTED, job.as_dict())
            except (ValueError, PermissionError, RuntimeError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

        def log_message(self, _format: str, *_args: object) -> None:
            return
    return Handler


def serve_dashboard(*, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Run the local dashboard until interrupted with Ctrl+C."""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Dashboard may bind only to localhost.")
    server = ThreadingHTTPServer((host, port), make_handler(DashboardController()))
    address = f"http://{host}:{port}/"
    print(f"FERMiON dashboard: {address}")
    print("Press Ctrl+C to stop the local dashboard.")
    if open_browser:
        threading.Timer(0.25, webbrowser.open, args=(address,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFERMiON dashboard stopped.")
    finally:
        server.server_close()
