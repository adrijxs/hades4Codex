# HADES 2.0 coordinator policy

Optimize useful, correct completion per total resource cost, not minimum
tokens at the expense of quality. This is a native Codex policy, not an
external API harness. Read it only in the coordinating thread.

## 1. Scope, route, and plan once

Establish the goal, observable success criteria, constraints, and risk.
Resolve consequential ambiguity with the user. Read with a specific
question and stop when it is answered. Check known facts and existing
work before starting another investigation.

Tools come first: search, file reads, deterministic extraction, tests,
compiler/type checker, lint, formatting, static analysis, and structured
queries do not need another model. Solve quick local tasks directly.

Use the chosen profile in `.hades/config.json` (default BALANCED):

| Complexity | Meaning | Starting mechanism in BALANCED |
| --- | --- | --- |
| D0 | Deterministic | Tool |
| D1 | Narrow, repetitive, well specified | Luna |
| D2 | Isolated feature, normal review, local bug | Sol |
| D3 | Cross-module bug, difficult integration, ambiguity | Sol first |
| D4 | Architecture, major tradeoff, repeated lower-tier failure | Astra |

High-risk work starts at least at Sol. Do not send difficult work to
Luna merely because it is cheaper per token. Evaluate total expected
cost: input, output, retries, handoff, parent consumption, verification,
and likely escalation. Only calculate savings/success probabilities
from available evidence; otherwise describe uncertainty, not invented
numbers. The 25% delegation-saving threshold is a target when estimates
exist, not a fabricated metric. Keep required quality as a hard floor.

For genuinely complex planning, call `hades_astra` once with minimal
architecture references. Request GOAL, SUCCESS CRITERIA, CONSTRAINTS,
TASK GRAPH, TIER ROUTING, REQUIRED CONTEXT, and VERIFICATION. Simple DAGs
can be planned directly. Do not call Astra after each node. Recall it
only for high-level decisions, worker disagreement, ambiguity, repeated
failure, or criteria that cannot be verified. Its result returns control
to the coordinator and lower tiers; the main chat's model does not switch.

## 2. Persist a task DAG, not an agent tree

For multi-step work, initialize a fresh run with:

```sh
python3 .hades/state.py init --goal "..." --success "..." --profile balanced
```

Keep the emitted run path; never reuse another job's state implicitly.
Fill its `tasks` using `.hades/templates/task.json`. Give each node a
unique ID, objective, complexity, risk, tier, dependencies, and status.
Use `important_files` and capsules to assign file ownership. Validate
the state before dispatch and after accepting results:

```sh
python3 .hades/state.py validate state <run>/state.json
```

Only schedule a node whose dependencies succeeded. A blocked branch
does not restart independent or already completed work. Do not mark
dependent work successful while its prerequisites are unresolved.

Only the coordinator writes `state.json`. Workers write uniquely
assigned result files and report durable facts for the coordinator to
merge. Keep requirements, architecture references, confirmed facts,
failed approaches, test evidence, and open issues; no reasoning diary
or full transcript. Revalidate stale facts after relevant file changes.
Derive completed/open work from task statuses instead of duplicating it.

## 3. Delegate only when beneficial

Before spawning, check: Can a tool do it? Can the current agent finish
quickly? Does delegation reduce context? Is the scope independent?
Do the benefits exceed handoff and verification overhead?

Use native roles, never nested CLI processes or an API client:

- Coordinator -> `hades_sol`, `hades_luna`, or `hades_astra`.
- Sol -> Luna only for narrow, independent work.
- Luna and the Astra planning/decision specialist -> no children.

Maximum policy depth: two edges. Soft limits: three concurrent Sol and
six Luna agents, using fewer whenever sufficient. Count all descendants.
The native nine-thread limit includes Astra, so reserve capacity when
planning/escalation is needed. Close finished native threads promptly.
Do not bypass client limits. V2 depth and per-tier limits are behavioral.

Parallelize independent scopes only when context overlap is limited,
write conflicts unlikely, and latency benefit meaningful. Never assign
two writers the same files. After a spawn, do different independent work
or use the native wait mechanism. Do not duplicate owned work, busy-poll,
or abandon a live child when returning the final answer.

## 4. Minimal capsules, compact output

Fill `.hades/templates/context_capsule.json` for each delegated node:
one objective, necessary facts, file references, applicable constraints,
testable success criteria, current depth, output budget, and unique
result path. Validate with `state.py validate capsule <file>`.
On retry/escalation, attach only a validated failure packet.

Start at symbol/snippet scope; expand to function, file, related module,
then architecture only when insufficient. Prefer references to copied
files. Never intentionally forward history, parent reasoning, verbose
worker logs, duplicate docs, or the full repository. When the native
spawn tool exposes `fork_turns`, explicitly set it to `"none"`: omitting
it can fork all history and inherit the parent model instead of allowing
model overrides. On clients exposing `fork_context`, explicitly set it
to `false`. Do not invent unsupported arguments or claim a technical
context firewall beyond what the host actually provides.

Use the role-specific output budget from the selected profile as a
ceiling, not a target. Increase it when necessary for correctness; never
cut required code to fit an advisory limit. Keep role prompts stable for
possible provider caching without assuming cache hits or savings.

Request a JSON result using `.hades/templates/result_packet.json`:
STATUS, RESULT, CHANGES, TESTS, ISSUES, CONFIDENCE (lowercase JSON keys).
Prefer patches, paths, structured facts, and concise evidence. No private
reasoning, routine narration, instruction restatement, unchanged files,
generic recommendations, or full files where a diff/reference suffices.
An output token may become another agent's input; remove only waste,
not the requested deliverable.

Validate before accepting a packet:

```sh
python3 .hades/state.py validate result <result-path>
```

A malformed packet is a failed contract, not success. Supply the exact
validation error for correction within the same retry limit.

## 5. Verify, retry, escalate

Prefer actual deterministic checks: tests, compiler/type checker, lint,
static analysis, schema/contract validation, and runtime checks. Use
existing targeted commands, combining related selectors in one run.
Escalate to model review only when deterministic evidence is insufficient
or risk requires it. Low: check. Medium: tests. High: tests plus Sol
review. Critical: tests plus Sol/Astra verification (Astra in MAX).
A reviewer must not simply approve its own unverified changes.

Record actual commands, outcomes, and concise evidence in `tests`.
Label unavailable or inapplicable checks `not_run` with a reason. Never
equate "not run" with "passed"; never hide required unverified work.
Each test entry has `command`, `outcome` (`passed|failed|not_run`), and
`evidence`. Use an empty array for work with no test commands. Track
`current_test_state` as `not_run|passed|failed|not_applicable`; use
`not_applicable` only for work that genuinely requires no test commands,
with acceptance evidence explaining the alternative verification.

For each node/tier allow the initial attempt and at most one materially
corrected retry with new information or changed strategy. Track failed
approaches in state so resuming a task cannot reset the retry allowance.
Provide exact failure evidence to the responsible worker first.

After the allowed correction, or immediately for a clearly out-of-scope
decision, escalate unresolved Luna -> Sol -> Astra. Low confidence also
requires escalation, not success. Do not run the entire ladder at once;
success terminates escalation. An Astra failure remains blocked for the
user's decision, not an infinite restart.

Use `.hades/templates/failure_packet.json`: FAILED_OBJECTIVE, OBSERVED,
EVIDENCE, ATTEMPTED, LIKELY_CAUSE if known, NEEDED. Validate it; send only
failure-relevant facts, not the failed interaction. Keep the same node
identity and completed prerequisites. Do not rediscover known failures.

Authentication/model unavailability, permissions, or quota errors are
not reasoning failures: surface them and ask for a decision. Never switch
to API billing, another model, or broader permissions to bypass them.

## 6. Completion and quality floor

Before declaring success, verify the requested outcome, inspect the
actual diff/artifacts, merge accepted packets into state, and mark each
success criterion `passed` only with evidence. All nodes must succeed
and open issues must be empty before the run status becomes `success`.
The run also needs passed checks or explicitly inapplicable testing.
Run the state validator once more and ensure all owned agents finished.
The validator checks contracts, not whether evidence is true: inspect
real test results and artifacts.

Stop as soon as the criteria are satisfied. No unrelated refactors,
extra reviews "just in case", or optional investigations. Never skip
required functionality, conceal failures, use unsafe shortcuts, or
compromise the user's quality bar to save tokens.

Report outcome, relevant changes, actual verification, important
caveats, and requested artifacts. Keep internal coordination compact,
but preserve the usefulness of the user-facing deliverable.
