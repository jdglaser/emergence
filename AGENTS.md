# Emergence — Engineering Instructions

## Project and stack

Emergence explores emergent social survival behavior in a shared 2D world.
The reboot uses Python 3.13+ for simulation and AI, with uv for project management,
pytest for tests, Ruff for formatting/linting, and Pyright in strict mode for typing.
Use pytest-asyncio when asynchronous tests are needed.

The planned interface uses Starlette and versioned WebSocket messages, with
React, TypeScript, Vite, and HTML Canvas for visualization. Introduce these only
in their approved milestones. Rust is outside the active stack.

## Architecture and determinism

- The Python world owns authoritative state; simulation rules validate and execute changes.
- Keep deterministic simulation independent of LLM calls, networking, and rendering.
- Cognition proposes validated intentions. Deterministic tasks handle movement and
  execution across ticks without an LLM call for every tile or tick.
- Keep domain, world, simulation, cognition, runtime/orchestration, and server
  responsibilities distinct; grow modules only when the current milestone needs them.
- Runtime coordinates cognition eligibility, barriers, concurrency, timeouts, and pacing.
  Server exposes state and controls without implementing simulation rules.
- Reproduce outcomes from the same initial state, seed, and recorded decisions.
  Collect contenders and apply decisions in deterministic order; use seeded randomness
  for contested outcomes and separate cosmetic randomness.
- Freeze authoritative simulation during a required cognition barrier. Resolve decisions
  or defined timeout fallbacks before advancing; keep tick time, wall time, inference
  latency, and rendering time separate.
- Pathfinding uses agent knowledge; validate actual movement against world state.
- Use small explicit task state machines. Interruptions do not automatically erase goals;
  support suspension/resumption only as required by the approved milestone.
- React displays authoritative backend state and sends controls. It neither executes
  simulation rules nor calls OpenAI. Browser interpolation is presentation only.

## Engineering and readability

- Prefer simple, explicit code, focused modules, and composition. M1 uses strict,
  frozen Pydantic models for domain validation and schema generation, as approved.
  Revalidate reconstructed records for updates; model_copy(update=...) skips validation.
- Use modern Python type hints and strict Pyright checking. Avoid blanket suppressions
  and unnecessary `Any`; explain narrow exceptions when external libraries require them.
- Treat LLM output as untrusted external input. Validate its structure before the engine
  validates intent against state. Keep credentials on the backend and out of logs.
- Prefer a maintained dependency when it materially improves correctness or readability;
  explain its cost and effect on determinism. Avoid speculative frameworks and abstractions.
- Use Ruff's conventional layout: two blank lines between top-level Python definitions
  and one between methods. Separate logical phases inside longer functions with blank
  lines; formatters cannot infer those phases.
- Keep TypeScript strict and use the formatter/linter established with the frontend.
  Separate functions and logical phases visibly; avoid compressed control flow.
- Handle errors explicitly. Keep changes focused, tested, and within the current milestone.

## Milestone workflow

1. Architect inspects the repository and proposes the smallest coherent plan, material
   decisions/trade-offs, dependencies, tests, documentation, and deferred work. No edits.
2. Stop for explicit human approval. Incorporate requested changes before implementation.
3. Implementer executes the approved scope, writes focused tests, and runs relevant checks.
4. Reviewer independently inspects correctness, boundaries, determinism, tests, and
   complexity; reports blocking findings separately from suggestions and never edits files.
5. Implementer addresses blocking findings within approved scope; Reviewer verifies fixes.
   Seek approval for material architectural changes or scope expansion.
6. Documenter inspects stable code/tests and updates README.md and docs/ as relevant.
   Explain Python and AI concepts, execution, decisions, and trade-offs clearly; include
   useful learning exercises/questions without extensive updates for trivial edits.
7. Present changes, validation, review findings, and documentation for human review.

Never proceed automatically to the next milestone or commit without explicit approval.
Do not port legacy Rust code. M0 establishes instructions and documentation only.

## Validation

Once the Python project is configured, run checks appropriate to the changed scope:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright` with strict mode configured
- `uv run pytest`

Frontend milestones establish and run their TypeScript, build, lint, and relevant test
checks. For documentation/configuration-only changes, validate syntax, links, diagrams,
and consistency; report unconfigured or unavailable checks rather than claiming they ran.
