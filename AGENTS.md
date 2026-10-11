# Emergence — Engineering Instructions

## Project

Emergence is an experimental AI-driven social survival simulation
written in Rust.

Agents begin as strangers with the shared objective of survival.
They must find food, gather resources, and construct shelter.

The simulation explores emergent relationships, cooperation,
competition, leadership, and conflict.

## Engineering Principles

- Prefer simple, explicit, idiomatic Rust.
- Keep modules focused and cohesive.
- Avoid premature abstractions and unnecessary dependencies.
- Prefer composition over complex inheritance-like patterns.
- Separate simulation logic from LLM integration and rendering.
- The simulation engine is authoritative over world state.
- LLMs propose decisions; the engine validates and executes them.
- Make simulation behavior deterministic where practical.
- Write tests for meaningful behavior and edge cases.
- Handle errors explicitly; avoid unnecessary unwrap() calls.
- Never silently introduce architectural changes.

## Development Workflow

For nontrivial features:

1. Architect proposes a minimal design and explains significant decisions and trade-offs.
2. Human approves the design; requested changes are incorporated before implementation.
3. Implementer writes code and tests according to the approved design and runs required validation.
4. Reviewer independently examines the implementation, separating blocking findings from optional suggestions; the Reviewer must not modify application code.
5. Implementer addresses blocking findings, and the Reviewer verifies corrections when appropriate.
6. For meaningful implementation changes, Documenter inspects the stabilized implementation and tests, then updates learning documentation, Rust concepts, architecture descriptions and diagrams, significant decisions, an exercise, understanding questions, and a learning recap. The Documenter must not modify application code.
7. Human reviews the final implementation and documentation summary.

Do not skip human approval for architectural changes.
Do not require extensive documentation updates for trivial formatting, renaming, or comment-only changes.

## Scope Control

- Implement only the requested functionality.
- Do not add speculative features.
- Do not introduce frameworks without a demonstrated need.
- Keep changes small and independently testable.

## Code Readability

- Run `rustfmt` and retain its conventional layout.
- Leave one blank line between adjacent top-level functions, methods,
  associated functions, trait methods, and tests.
- In nontrivial functions, use blank lines to separate logical phases such as
  validation, mutation, and event emission.
- Do not compress multi-branch control flow or unrelated mutations onto one
  line; prefer clearly formatted `match`/`if` blocks and named intermediates.

## Validation

Run the relevant checks before declaring implementation complete:

- cargo fmt --check
- cargo clippy --all-targets -- -D warnings
- cargo test
