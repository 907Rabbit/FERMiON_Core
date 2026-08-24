# OpenClaw / FERMiON Safe-Evolver Bridge

OpenClaw can propose a bounded evolver action through FERMiON's local
`/api/bridge` endpoint. FERMiON parses the proposal as a typed plan and then
validates it against the control-plane manifest. OpenClaw does not receive
shell, source-editing, or strategy-execution authority from this integration.

Use `self_evolver.status` for inspection without approval. The
`record_feedback`, `evolve`, and `rollback` operations are mutating and always
require explicit FERMiON approval, even if a proposal says otherwise.

Example status proposal:

```xml
<tool_call><function=fermion_plan><parameter=plan>
{"summary":"Inspect the safe evolver","actions":[{"application":"self_evolver","operation":"status","arguments":{}}],"requires_approval":false}
</parameter></function></tool_call>
```

Example approved evolution proposal. The adapter bounds `generations` to 120,
`population` to 128, and `minimum_improvement` to `[0, 1)`.

```xml
<tool_call><function=fermion_plan><parameter=plan>
{"summary":"Run a bounded strategy evolution","actions":[{"application":"self_evolver","operation":"evolve","arguments":{"seed":42,"generations":40,"population":64,"minimum_improvement":0.001}}],"requires_approval":true}
</parameter></function></tool_call>
```

The evolver writes only into FERMiON's control-plane `SelfEvolver` runtime
directory. Generated strategies are AST-whitelisted and probed in an isolated
subprocess; they are never used to modify FERMiON or OpenClaw source code.
