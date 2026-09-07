# HADES 2.0

Use HADES by default in this repository, with the BALANCED policy, unless
the user opts out or selects ECO/MAX. Preserve correctness, complete the
requested work, and verify it before optimizing token usage.

- Prefer deterministic tools. Handle quick, local work directly. Do not
  spawn agents to search one symbol, read known files, or run a command.
- For multi-step work or useful delegation, use
  `.agents/skills/hades/SKILL.md`. Load the full orchestrator policy only
  in the coordinating thread, not in every worker.
- Route D0 to tools, D1 to `hades_luna`, D2/D3 to `hades_sol`, and D4 or
  unresolved architectural decisions to `hades_astra`. These are starting
  points, not a requirement to delegate work the current agent can finish
  more efficiently.
- Use minimal task capsules and file references, not conversation
  history. Delegate only independent scopes with a clear owner.
- Allow an initial attempt and one materially corrected retry; escalate
  unresolved failures with evidence. Never repeat an equivalent attempt.
- Verify with existing tools/tests first. High-risk work needs tests and
  Sol review; critical work needs tests and Sol/Astra verification.
- Do not modify unrelated work, weaken permissions, hide failures, switch
  authentication to API billing, or claim unavailable models ran.
- Keep user-facing results useful and concise: outcome, verification,
  important caveats. Never return private reasoning or routine narration.

If you are a spawned agent with a task capsule, follow your assigned role
and objective. Do not bootstrap another orchestrator or load the full
HADES core. Luna is a leaf; Sol may delegate only narrow independent work
to Luna. Report durable findings to the parent; only the coordinator
writes the shared run state.

Repository validation: `python3 -m unittest discover -s tests -p 'test_*.py'`.
Do not claim live Codex/model validation from these offline tests.
