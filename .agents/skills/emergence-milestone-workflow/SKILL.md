---
name: emergence-milestone-workflow
description: Deliver an Emergence milestone or meaningful feature through the repository's Architect, Implementer, Reviewer, and Documenter roles with required human plan approval.
---

# Emergence Milestone Workflow

Use this skill for a requested Emergence milestone or meaningful feature implementation. Follow the repository's `AGENTS.md` as the shared engineering standard and use the project-scoped native Codex agents in `.codex/agents/`.

## Gated lifecycle

1. Inspect the request and relevant repository state. Delegate architecture to `architect`. Its work is read-only and must return a concise minimal design, material trade-offs, dependencies, deferred work, and an implementation plan.
2. Present that proposal and stop. Do not edit files or delegate implementation until the human explicitly approves the plan. Incorporate any requested plan changes and obtain approval for the resulting plan.
3. After explicit approval, delegate the approved scope to `implementer`. Require focused tests and the checks in `AGENTS.md`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and `cargo test`.
4. Delegate an independent, read-only review to `reviewer`. Require blocking findings and optional suggestions to be reported separately.
5. Send only blocking findings to `implementer` for correction, then request a follow-up review. Repeat until the Reviewer has no blocking findings. Do not expand scope for optional suggestions.
6. Once a meaningful implementation is stable, delegate to `documenter`. It must inspect the stabilized code and tests and update only the learning documentation under `docs/`: learning guide/recap, applicable Rust concepts, architecture and diagrams, significant decisions, an exercise, and understanding questions. Trivial formatting, renaming, and comment-only changes may skip extensive documentation.
7. Return the implementation summary, files changed, validation results, review findings, and documentation outcome for human review.

## Invariants

- The simulation engine remains authoritative; cognition/LLMs may propose actions but do not mutate world state directly.
- Keep the implementation minimal, deterministic where practical, dependency-conscious, and within the approved plan. Escalate material architectural changes to the human rather than silently introducing them.
- Respect role boundaries: Architect and Reviewer never edit files; Documenter never modifies application code, tests, dependencies, or configuration.
- Human approval of a plan or implementation is not approval to commit. Never commit unless the human explicitly requests it.
