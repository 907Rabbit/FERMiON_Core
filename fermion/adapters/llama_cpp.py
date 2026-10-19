"""Local llama.cpp candidate generation; outputs are proposals, never labels."""

from __future__ import annotations

import json
import ast
import csv
import io
import os
import re
import signal
import subprocess
import time
import urllib.request
import urllib.error
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion.hr.contracts import CandidateProgram, ProgramKind


def strip_model_reasoning(text: str) -> str:
    """Keep public output only; discard complete or unfinished thought sections.

    Closing markers can arrive without an opening marker when a model template
    supplies the opening tag.  Everything through the last closing marker is
    private in that case as well.  Never return the discarded text to callers.
    """
    if not isinstance(text, str):
        return ""
    closing = list(re.finditer(r"</(?:think|thinking|analysis)\s*>", text, re.I))
    if closing:
        text = text[closing[-1].end():]
    opening = re.search(r"<(?:think|thinking|analysis)\s*>", text, re.I)
    if opening:
        text = text[:opening.start()]
    return text.strip()


def without_provider_reasoning(value: Any) -> Any:
    """Copy structured metadata without provider-private reasoning fields.

    FERMiON's own structured `reasoning` diagnostics are separate from provider
    reasoning and remain available. Public completion text is filtered above.
    """
    if isinstance(value, dict):
        return {key: without_provider_reasoning(item) for key, item in value.items()
                if key not in {"reasoning_content", "reasoning_details", "thinking_content"}}
    if isinstance(value, (list, tuple)):
        return [without_provider_reasoning(item) for item in value]
    return value


def _public_content(value: object) -> str:
    if isinstance(value, str):
        return strip_model_reasoning(value)
    if isinstance(value, list):
        # Provider reasoning/thinking blocks and their signatures are never text.
        parts = [item["text"] for item in value
                 if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
                 and isinstance(item.get("text"), str)]
        return strip_model_reasoning("\n".join(parts))
    return ""


def public_completion_text(payload: object) -> str:
    """Extract public text from native or compatible responses by allow-list.

    Never fall back to reasoning_content, reasoning, thinking, or reasoning
    details, including when public content is missing or empty.
    """
    if not isinstance(payload, dict):
        return ""
    output = payload.get("output")
    if isinstance(output, list):
        return strip_model_reasoning("\n".join(
            _public_content(item.get("content")) for item in output
            if isinstance(item, dict) and item.get("type") == "message"
        ))
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    if isinstance(choice, dict):
        message = choice.get("message")
        if isinstance(message, dict):
            # An explicit empty chat answer must stay empty, even if another
            # compatibility field happens to contain an intermediate draft.
            return _public_content(message.get("content"))
        if "text" in choice:
            return _public_content(choice["text"])
    return _public_content(payload.get("content"))


@dataclass(frozen=True)
class LlamaCppConfig:
    endpoint: str | None = "http://127.0.0.1:8080/completion"
    executable: str | None = None
    server_executable: str | None = None
    model_path: str | None = None
    model_identifier: str | None = None
    timeout_seconds: float = 60.0
    final_timeout_seconds: float | None = None
    temperature: float = 0.4
    max_tokens: int = 128
    host: str = "127.0.0.1"
    port: int = 8080
    context_size: int = 256
    batch_size: int = 16
    micro_batch_size: int = 16
    threads: int = 4
    gpu_layers: int = 0
    reasoning_budget: int | None = None
    reasoning_format: str | None = None
    candidate_mode: str = "structured"
    api_key: str | None = None
    embeddings_identifier: str | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "LlamaCppConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload["llama_cpp"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LlamaCppAdapter:
    def __init__(self, config: LlamaCppConfig | None = None):
        self.config = config or LlamaCppConfig()

    def generate(self, goal: str, observation: dict[str, Any], count: int = 3) -> list[CandidateProgram]:
        if self.config.candidate_mode == "source":
            return self._generate_sources(goal, observation, count)
        prompt = self._prompt(goal, observation, count)
        schema = self._candidate_schema(count)
        text = self._server(prompt, schema) if self.config.endpoint else self._cli(prompt, schema)
        try:
            return self._parse(text, count)
        except (ValueError, json.JSONDecodeError):
            repair = ("[INST] Rewrite the following as valid JSON only. Preserve the program semantics, "
                      "escape every string correctly, and return one JSON array with no prose:\n"
                      f"{text[:1200]} [/INST]")
            repaired = self._server(repair, schema) if self.config.endpoint else self._cli(repair, schema)
            return self._parse(repaired, count)

    def _generate_sources(self, goal: str, observation: dict[str, Any], count: int) -> list[CandidateProgram]:
        candidates = []
        state = json.dumps(observation, sort_keys=True, default=str)[:240]
        for index in range(count):
            prompt = ("[INST] Write only a short executable Python program, at most 8 lines. "
                      "No explanation and no JSON. Use files relative to the current directory. "
                      f"Task: {goal}. State: {state} [/INST]")
            text = self._server(prompt) if self.config.endpoint else self._cli(prompt)
            source = self._extract_python(text)
            artifacts = self._infer_artifacts(source)
            risky = any(name in source for name in ("subprocess", "socket", "shutil.rmtree", "os.remove"))
            candidates.append(CandidateProgram(
                f"llama-source-{index}", source, ProgramKind.PYTHON,
                declared_artifacts=artifacts, estimated_cost=min(len(source) / 1000.0, 1.0),
                estimated_risk=0.7 if risky else 0.1, reversible=not risky, provenance="llama.cpp"))
        return candidates

    def _server(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        request_data: dict[str, Any] = {"prompt": prompt, "temperature": self.config.temperature,
                                        "n_predict": self.config.max_tokens}
        if schema is not None:
            request_data["json_schema"] = schema
        payload = json.dumps(request_data).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._authorization()}
        request = urllib.request.Request(self.config.endpoint or "", payload, headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            result = json.loads(response.read())
        return public_completion_text(result)

    def _cli(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        if not self.config.executable or not self.config.model_path:
            raise RuntimeError("llama.cpp CLI requires executable and model_path")
        command = [self.config.executable, "-m", self.config.model_path,
                   "-p", prompt, "-n", str(self.config.max_tokens),
                   "-c", str(self.config.context_size), "-b", str(self.config.batch_size),
                   "-ub", str(self.config.micro_batch_size), "-t", str(self.config.threads),
                   "-ngl", str(self.config.gpu_layers), "--no-warmup"]
        if schema is not None:
            command.extend(("--json-schema", json.dumps(schema, separators=(",", ":"))))
        completed = subprocess.run(command,
                                   capture_output=True, text=True,
                                   timeout=self.config.timeout_seconds, check=True)
        return strip_model_reasoning(completed.stdout)

    @staticmethod
    def _prompt(goal: str, observation: dict[str, Any], count: int) -> str:
        state = json.dumps(observation, sort_keys=True, default=str)[:400]
        return (f"[INST] JSON only, no prose or markdown. Generate {count} Python candidate(s) for: {goal}. "
                "Return an array of objects with keys id, source, declared_artifacts, estimated_cost, "
                f"estimated_risk, reversible. Escape source correctly. State: {state} [/INST]")

    @staticmethod
    def _candidate_schema(count: int) -> dict[str, Any]:
        properties = {
            "id": {"type": "string", "maxLength": 32},
            "source": {"type": "string", "maxLength": 160},
            "declared_artifacts": {"type": "array", "maxItems": 4,
                                   "items": {"type": "string", "maxLength": 64}},
            "estimated_cost": {"type": "number", "minimum": 0},
            "estimated_risk": {"type": "number", "minimum": 0, "maximum": 1},
            "reversible": {"type": "boolean"},
        }
        return {"type": "array", "minItems": 1, "maxItems": max(1, count),
                "items": {"type": "object", "properties": properties,
                          "required": list(properties), "additionalProperties": False}}

    @staticmethod
    def _extract_python(text: str) -> str:
        if "```" in text:
            pieces = text.split("```")
            if len(pieces) >= 3:
                source = pieces[1]
                if source.lstrip().startswith("python"):
                    source = source.lstrip()[6:].lstrip("\r\n")
                source = source.strip()
                ast.parse(source)
                return source
        stripped = text.strip()
        try:
            ast.parse(stripped)
            return stripped
        except SyntaxError:
            lines = stripped.splitlines()
            starts = ("import ", "from ", "open(", "with ", "def ", "class ", "print(")
            for start in range(len(lines)):
                if not lines[start].lstrip().startswith(starts):
                    continue
                for end in range(len(lines), start, -1):
                    candidate = "\n".join(lines[start:end]).strip()
                    try:
                        ast.parse(candidate)
                        return candidate
                    except SyntaxError:
                        continue
        raise ValueError("llama.cpp did not return valid Python source")

    @staticmethod
    def _infer_artifacts(source: str) -> tuple[str, ...]:
        artifacts: set[str] = set()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    artifacts.add(node.args[0].value.replace("\\", "/"))
            if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("write"):
                owner = node.func.value
                if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name) and owner.func.id == "Path":
                    if isinstance(owner.args[0], ast.Constant) and isinstance(owner.args[0].value, str):
                        artifacts.add(owner.args[0].value.replace("\\", "/"))
        return tuple(sorted(artifacts))

    @staticmethod
    def _parse(text: str, count: int) -> list[CandidateProgram]:
        decoder = json.JSONDecoder()
        items = None
        for start, character in enumerate(text):
            if character != "[":
                continue
            try:
                value, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, list):
                items = value
                break
        if items is None:
            raise ValueError("llama.cpp response did not contain a valid JSON candidate array")
        candidates = []
        for index, item in enumerate(items[:count]):
            if not isinstance(item, dict) or "source" not in item:
                continue
            candidates.append(CandidateProgram(
                str(item.get("id", f"llama-{index}")), str(item["source"]), ProgramKind.PYTHON,
                declared_artifacts=tuple(item.get("declared_artifacts", ())),
                estimated_cost=float(item.get("estimated_cost", 0.5)),
                estimated_risk=float(item.get("estimated_risk", 0.5)),
                reversible=bool(item.get("reversible", True)), provenance="llama.cpp"))
        if not candidates:
            raise ValueError("llama.cpp returned no candidates")
        return candidates

    def _authorization(self) -> dict[str, str]:
        return ({"Authorization": f"Bearer {self.config.api_key}"}
                if self.config.api_key else {})


@dataclass(frozen=True)
class LlamaServerStatus:
    configured: bool
    running: bool
    healthy: bool
    pid: int | None
    endpoint: str | None
    model_path: str | None


class LlamaServerRuntime:
    """Lifecycle manager for a loopback-only llama-server process."""

    def __init__(self, config: LlamaCppConfig, state_dir: str | Path = ".fermion"):
        self.config = config
        self.state_dir = Path(state_dir)
        self.pid_path = self.state_dir / "llama-server.pid"
        self.stdout_path = self.state_dir / "llama-server.stdout.log"
        self.stderr_path = self.state_dir / "llama-server.stderr.log"

    def health(self, timeout: float = 2.0) -> bool:
        """Recognize both llama.cpp and OpenAI-compatible local servers.

        llama.cpp reports ``{"status": "ok"}`` at ``/health``.  LM Studio's
        compatible server instead advertises readiness through ``/v1/models``.
        The latter is useful when FERMiON is configured to consume an already
        running local server rather than own its executable lifecycle.
        """
        base = f"http://{self.config.host}:{self.config.port}"
        for endpoint in (f"{base}/health", f"{base}/v1/models"):
            try:
                request = urllib.request.Request(endpoint, headers=self._authorization())
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
                if payload.get("status") == "ok" or (
                    isinstance(payload.get("data"), list) and bool(payload["data"])
                ):
                    return True
            except (OSError, ValueError, urllib.error.URLError):
                continue
        return False

    def status(self) -> LlamaServerStatus:
        pid = self._pid()
        healthy = self.health()
        configured = bool(self.config.endpoint) or bool(self.config.server_executable and self.config.model_path)
        return LlamaServerStatus(configured,
                                 healthy or self._process_exists(pid), healthy, pid,
                                 self.config.endpoint, self.config.model_path)

    def start(self, wait_seconds: float = 180.0) -> LlamaServerStatus:
        if self.health():
            return self.status()
        if self._lm_studio_available() and self.config.model_identifier:
            self._load_lm_studio_model()
            if self.health():
                return self.status()
            raise RuntimeError("LM Studio accepted the model load request but no loaded model is available.")
        executable = Path(self.config.server_executable or "")
        model = Path(self.config.model_path or "")
        if not executable.is_file():
            raise ValueError(f"llama-server executable not found: {executable}")
        if not model.is_file():
            raise ValueError(f"GGUF model not found: {model}")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        command = [str(executable), "-m", str(model), "--host", self.config.host,
                   "--port", str(self.config.port), "-c", str(self.config.context_size),
                   "-b", str(self.config.batch_size), "-ub", str(self.config.micro_batch_size),
                   "-t", str(self.config.threads), "-ngl", str(self.config.gpu_layers), "--no-warmup"]
        if self.config.reasoning_budget is not None:
            command.extend(("--reasoning-budget", str(self.config.reasoning_budget)))
        if self.config.reasoning_format:
            command.extend(("--reasoning-format", self.config.reasoning_format))
        if self.config.api_key:
            command.extend(("--api-key", self.config.api_key))
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        stdout = self.stdout_path.open("a", encoding="utf-8")
        stderr = self.stderr_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=executable.parent, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, close_fds=True,
                                       creationflags=creationflags)
        finally:
            stdout.close(); stderr.close()
        self.pid_path.write_text(str(process.pid), encoding="ascii")
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.health():
                return self.status()
            if process.poll() is not None:
                raise RuntimeError(f"llama-server exited with code {process.returncode}; see {self.stderr_path}")
            time.sleep(1.0)
        raise TimeoutError(f"llama-server did not become healthy within {wait_seconds:g} seconds")

    def _lm_studio_available(self) -> bool:
        """Return whether an LM Studio v1 model-management endpoint is available."""
        endpoint = f"http://{self.config.host}:{self.config.port}/api/v1/models"
        try:
            request = urllib.request.Request(endpoint, headers=self._authorization())
            with urllib.request.urlopen(request, timeout=2.0) as response:
                payload = json.loads(response.read())
            return isinstance(payload.get("models"), list)
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def _load_lm_studio_model(self) -> None:
        """Load the configured downloaded model through LM Studio's local REST API."""
        if not self.config.model_identifier:
            raise ValueError("LM Studio model_identifier is not configured")
        endpoint = f"http://{self.config.host}:{self.config.port}/api/v1/models/load"
        payload = json.dumps({
            "model": self.config.model_identifier,
            "context_length": self.config.context_size,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._authorization()}
        request = urllib.request.Request(endpoint, payload, headers)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"LM Studio model load failed (HTTP {error.code}): {detail[:500]}") from error
        if result.get("status") != "loaded":
            raise RuntimeError(f"LM Studio did not confirm the model load: {result}")

    def stop(self) -> LlamaServerStatus:
        pid = self._pid()
        if pid is not None and self._process_exists(pid):
            if os.name == "nt":
                name = self._windows_process_name(pid)
                if name.lower() != "llama-server.exe":
                    raise RuntimeError(f"refusing to stop PID {pid}: expected llama-server.exe, found {name}")
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, text=True, check=True)
            else:
                os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not self._process_exists(pid):
                    break
                time.sleep(0.25)
        self.pid_path.unlink(missing_ok=True)
        return self.status()

    def completion_probe(self) -> str:
        payload = json.dumps({"prompt": "[INST] Output exactly the single word READY. [/INST]",
                              "n_predict": 8, "temperature": 0.0}).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._authorization()}
        request = urllib.request.Request(self.config.endpoint or "", payload, headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return str(json.loads(response.read()).get("content", "")).strip()

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
            return LlamaServerRuntime._windows_process_name(pid) != ""
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

    def _authorization(self) -> dict[str, str]:
        return ({"Authorization": f"Bearer {self.config.api_key}"}
                if self.config.api_key else {})
