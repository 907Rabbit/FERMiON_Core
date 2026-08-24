"""Command-line interface for FERMiON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fermion_symplectic_dysib import BenchmarkConfig, promotion_decision, run_benchmark

from .adapters.llama_cpp import LlamaCppAdapter, LlamaCppConfig, LlamaServerRuntime
from .curriculum import CurriculumConfig, CurriculumRunner
from .hr.reference_193 import FermionHR193, reference_inputs
from .task import run_task
from .cognitive.discovery import discover_models
from .cognitive.runtime import CognitiveRuntime, RuntimeConfig


def main() -> None:
    # Windows PowerShell may default to cp1252; FERMiON scientific answers require UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="fermion", description="FERMiON research controller")
    parser.add_argument("--model", help="local GGUF path recorded for the cognitive session")
    parser.add_argument("--disable-cognition", action="store_true", help="ablation: run language shell without FERMiON state updates")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--trace-cognition", action="store_true", help="write structured pipeline metadata to logs/runtime.log")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("reference", help="verify and print the canonical 193-parameter specimen")
    curriculum = commands.add_parser("curriculum", help="run the six-stage local curriculum")
    curriculum.add_argument("--quick", action="store_true")
    curriculum.add_argument("--with-llama", action="store_true",
                            help="run Stage 5 through the configured llama.cpp server")
    benchmark = commands.add_parser("symplectic", help="run the Symplectic DySIB benchmark")
    benchmark.add_argument("--quick", action="store_true")
    task = commands.add_parser("run-task", help="rank, execute, validate, and record a JSON task spec")
    task.add_argument("spec")
    task.add_argument("--commit", action="store_true", help="commit declared artifacts after validation")
    llama = commands.add_parser("llama", help="manage the linked llama.cpp server")
    llama.add_argument("action", choices=("status", "start", "stop", "test", "generate"))
    llama.add_argument("--config", default="fermion.local.json")
    llama.add_argument("--goal", default="Create result.json containing the number 42")
    dashboard = commands.add_parser("dashboard", help="open the local FERMiON control console")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--no-browser", action="store_true", help="serve without opening the default browser")
    integration_verify = commands.add_parser("integration-verify", help="verify manifest, scientific gates, and provenance without executing actions")
    integration_verify.add_argument("--manifest", required=True, help="path to an immutable first-party manifest")
    integration_verify.add_argument("--gates", required=True, help="path to an immutable scientific-gate registry")
    self_evolver = commands.add_parser("self-evolver", help="run the constrained, auditable strategy evolver")
    self_evolver.add_argument("--workspace", help="runtime directory for generated strategies and audit records")
    self_evolver.add_argument("args", nargs=argparse.REMAINDER,
                              help="arguments after this command belong to the self-evolver")
    chat = commands.add_parser("chat", help="start the persistent FERMiON cognitive CLI")
    chat.add_argument("--once", help="process one message and exit")
    cognition = commands.add_parser("cognition", help="print calculated functional cognitive-access metrics")
    cognition.add_argument("--json", action="store_true")
    models = commands.add_parser("models", help="discover local GGUF models without downloading anything")
    models.add_argument("--directory", action="append", default=[])
    checkpoint = commands.add_parser("checkpoint", help="save or load cognitive state")
    checkpoint.add_argument("action", choices=("save", "load"))
    checkpoint.add_argument("name")
    args = parser.parse_args()
    if args.command is None:
        args.command = "chat"; args.once = None
    if args.command == "chat":
        runtime = CognitiveRuntime(RuntimeConfig(root=Path.cwd(), model_path=args.model, disabled=args.disable_cognition))
        def emit(message: str) -> None:
            result = runtime.process(message)
            print("\nFERMiON > " + result.response)
            if args.debug:
                print(json.dumps({"energy": result.energy, "cognition": result.cognition, "provenance": result.provenance, "generation_status": result.generation_status, "timing": result.timing}, indent=2))
        if args.once:
            emit(args.once); return
        print("FERMiON local cognitive CLI. Commands: /cognition, /route last, /capabilities, /capability ID, /capability gaps, /self audit, /llm last, /evidence last, /calculation last, /calculation verify ID, /memory verify KEY, /execution verify ID, /checkpoint save NAME, /checkpoint load NAME, /quit")
        while True:
            try: message = input("You > ").strip()
            except (EOFError, KeyboardInterrupt): print(); break
            if not message: continue
            if message in ("/quit", "/exit"): break
            parts = message.split()
            if message == "/cognition": print(json.dumps(runtime.cognition(), indent=2)); continue
            if message == "/llm last": print(json.dumps(runtime.last_llm_status(), indent=2)); continue
            if message == "/route last": print(json.dumps(runtime.last_route_status() or "NO_ROUTE", indent=2)); continue
            if message == "/capabilities": print(json.dumps(runtime.capability_records(), indent=2)); continue
            if message == "/capability gaps": print(json.dumps(runtime.capability_gaps(), indent=2)); continue
            if message == "/capability health": print(json.dumps(runtime.capability_health(), indent=2)); continue
            if message == "/capability degraded": print(json.dumps([x for x in runtime.capability_health().values() if x["health_status"] != "healthy"], indent=2)); continue
            if message == "/capability anomalies": print(json.dumps(runtime.capability_anomalies(), indent=2)); continue
            if message == "/capability diagnose": print(json.dumps(runtime.capability_diagnose(), indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/capability", "health"]: print(json.dumps(runtime.capability_health(parts[2]), indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/capability", "impact"]: print(json.dumps(runtime.capability_impact(parts[2]), indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/capability", "blockers"]: print(json.dumps(runtime.capability_blockers(parts[2]), indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/capability", "history"]: print(json.dumps(runtime.capability_history(parts[2]), indent=2)); continue
            if len(parts) == 3 and parts[:2] in (["/capability","diagnose"],["/capability","rootcause"]): print(json.dumps(runtime.capability_diagnose(parts[2]), indent=2)); continue
            if len(parts) == 3 and parts[:2] in (["/capability","recover"],["/capability","recovery-plan"]): print(json.dumps(runtime.capability_recovery(parts[2]), indent=2)); continue
            if message == "/self audit": print(json.dumps(runtime.self_audit(), indent=2)); continue
            if message == "/release readiness": print(json.dumps(runtime.release_readiness(), indent=2)); continue
            if message == "/release candidate": print(json.dumps(runtime.release_candidate(), indent=2)); continue
            if len(parts)==3 and parts[:2]==["/web","fetch"]: print(json.dumps(runtime.fetch_web(parts[2]),indent=2)); continue
            if message == "/release bundle": print(runtime.release_bundle()); continue
            if len(parts)==4 and parts[:3]==["/release","bundle","verify"]: print(json.dumps(runtime.verify_bundle(parts[3]),indent=2)); continue
            if len(parts)==4 and parts[:3]==["/release","bundle","reproduce"]: print(json.dumps(runtime.reproduce_bundle(parts[3]),indent=2)); continue
            if message == "/release blockers": print(json.dumps(runtime.release_readiness()["blockers"], indent=2)); continue
            if message == "/release versions": print(json.dumps(runtime.release_readiness()["versions"], indent=2)); continue
            if message == "/release evidence": print(json.dumps(runtime.release_readiness(), indent=2)); continue
            if len(parts) == 2 and parts[0] == "/capability": print(json.dumps(runtime.capability(parts[1]) or "CAPABILITY_NOT_FOUND", indent=2)); continue
            if message == "/evidence last": print(json.dumps(runtime.last_evidence() or "VERIFICATION_FAILED", indent=2)); continue
            if message == "/calculation last": print(json.dumps(runtime.last_calculation() or "CALCULATION_UNVERIFIED", indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/calculation", "verify"]:
                print(json.dumps(runtime.verify_calculation(parts[2]) or "CALCULATION_UNVERIFIED", indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/memory", "verify"]:
                print(json.dumps(runtime.verify_memory(parts[2]) or "VERIFICATION_FAILED", indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/execution", "verify"]:
                print(json.dumps(runtime.verify_execution(parts[2]) or "VERIFICATION_FAILED", indent=2)); continue
            if len(parts) == 3 and parts[:2] == ["/checkpoint", "save"]: print(f"Saved {runtime.save_checkpoint(parts[2])}"); continue
            if len(parts) == 3 and parts[:2] == ["/checkpoint", "load"]: print(f"Loaded {runtime.load_checkpoint(parts[2])}"); continue
            emit(message)
    elif args.command == "cognition":
        print(json.dumps(CognitiveRuntime(RuntimeConfig(root=Path.cwd(), model_path=args.model, disabled=args.disable_cognition)).cognition(), indent=2))
    elif args.command == "models":
        print(json.dumps([str(path) for path in discover_models(args.directory or None)], indent=2))
    elif args.command == "checkpoint":
        runtime = CognitiveRuntime(RuntimeConfig(root=Path.cwd(), model_path=args.model, disabled=args.disable_cognition))
        print(runtime.save_checkpoint(args.name) if args.action == "save" else runtime.load_checkpoint(args.name))
    elif args.command == "reference":
        model = FermionHR193(); trace = model(*reference_inputs())
        print(json.dumps({"parameter_count": model.parameter_count,
                          "success": trace.success.detach().tolist(),
                          "effect_energy": trace.effect_energy.detach().tolist()}, indent=2))
    elif args.command == "curriculum":
        adapter = LlamaCppAdapter(LlamaCppConfig.from_file("fermion.local.json")) if args.with_llama else None
        report = CurriculumRunner(CurriculumConfig(quick=args.quick), llama=adapter).run()
        print(json.dumps(report.to_dict(), indent=2, default=lambda value: value.value))
    elif args.command == "symplectic":
        config = (BenchmarkConfig(trajectories=16, steps=12, pretrain_epochs=1, finetune_epochs=2)
                  if args.quick else BenchmarkConfig())
        results = run_benchmark(config)
        print(json.dumps({"results": {name: asdict(metrics) for name, metrics in results.items()},
                          "promotion": asdict(promotion_decision(results))}, indent=2))
    elif args.command == "run-task":
        print(json.dumps(asdict(run_task(args.spec, commit=args.commit)), indent=2))
    elif args.command == "dashboard":
        from .dashboard import serve_dashboard
        serve_dashboard(port=args.port, open_browser=not args.no_browser)
    elif args.command == "integration-verify":
        from .cognitive.runtime_bootstrap import inspect_git_baseline, verify_integration
        root = Path.cwd()
        manifest, gates, provenance = verify_integration(root=root, manifest_path=Path(args.manifest),
                                                         gate_registry_path=Path(args.gates))
        baseline = inspect_git_baseline(root)
        print(json.dumps({"source_manifest_sha256": manifest.manifest_sha256,
                          "scientific_gate_registry_sha256": gates.registry_sha256,
                          "scientific_gates": {gate.gate_id: gate.state for gate in gates.gates},
                          "provenance_records": len(provenance.records()),
                          "git_baseline": asdict(baseline),
                          "verification": "VERIFIED" if baseline.committed and baseline.clean
                          else "VERIFIED_ARTIFACTS_GIT_BASELINE_INCOMPLETE"}, indent=2))
    elif args.command == "self-evolver":
        from .safe_self_evolver import main as self_evolver_main
        self_evolver_args = (["--workspace", args.workspace] if args.workspace else []) + args.args
        exit_code = self_evolver_main(self_evolver_args)
        if exit_code:
            raise SystemExit(exit_code)
    else:
        config = LlamaCppConfig.from_file(args.config)
        runtime = LlamaServerRuntime(config)
        if args.action == "start":
            output = asdict(runtime.start())
        elif args.action == "stop":
            output = asdict(runtime.stop())
        elif args.action == "test":
            output = {**asdict(runtime.status()), "completion": runtime.completion_probe()}
        elif args.action == "generate":
            output = {"candidates": [asdict(candidate)
                                     for candidate in LlamaCppAdapter(config).generate(args.goal, {}, 1)]}
        else:
            output = asdict(runtime.status())
        print(json.dumps(output, indent=2, default=lambda value: value.value))


if __name__ == "__main__":
    main()
