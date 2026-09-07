---
name: hades
description: Use HADES 2.0 for repository work requiring a task graph, cost-aware Codex delegation, context capsules, shared state, verification, or failure escalation. Default policy is BALANCED. For trivial direct tasks use tools without spawning agents.
---

# HADES 2.0 - native Codex workflow

Use the repository root as the base for all paths below.

1. Check whether this is a coordinator request or an assigned worker
   capsule. Workers follow their native role; do not load the core again.
2. For quick deterministic or local work, use tools/direct execution,
   verify, and stop. No mandatory planning call, run file, or subagent.
3. For multi-step work, read `.hades/HADES_ORCHESTRATOR.md` and
   `.hades/config.json`. Use BALANCED unless the user selects ECO/MAX.
4. Use Codex's native `hades_astra`, `hades_sol`, and `hades_luna` roles.
   A skill cannot manufacture models or bypass account availability.
   If the client does not expose these roles, stop delegated execution,
   report the limitation, and ask before substituting direct execution.
5. Keep the ChatGPT subscription login. Never use an API key, external
   provider, nested `codex exec` process, or alternate model as an
   unannounced workaround. Leave sandbox and approval settings intact.
6. Use the templates under `.hades/templates/`. Initialize isolated
   shared state with `python3 .hades/state.py init --goal ... --success ...`.
   Validate packets and the DAG with `python3 .hades/state.py validate`.
   Tell the user if the local validator cannot run.

Do not forward this entire skill or core policy to workers. Their native
role instructions plus a minimal capsule are sufficient. Return only
the useful outcome, actual verification, and unresolved caveats.

## Learnings

Codex V2 may fork all history and inherit the parent model when
`fork_turns` is omitted. For minimal-capsule delegation, explicitly use
`fork_turns="none"` when supported; older clients may expose
`fork_context=false` instead. See the core policy for the dispatch rules.
