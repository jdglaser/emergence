---
name: emergence-milestone-workflow
description: Deliver an Emergence milestone or meaningful feature through Architect, Implementer, Reviewer, and Documenter roles with human plan approval.
---

# Emergence Milestone Workflow

Use the repository's AGENTS.md for shared standards, docs/ROADMAP.md for milestone
scope, and native roles in .codex/agents/. The active direction is Python simulation
and cognition with React/TypeScript/Canvas presentation; do not port archived Rust code.

## Gated lifecycle

1. Delegate read-only investigation to `architect`: minimal design, material trade-offs,
   dependencies, tests, documentation, and deferred work for the requested milestone.
2. Present the plan and stop for explicit human approval before edits or implementation.
   Incorporate the human's refinements; existing approval authorizes the refined scope.
3. Delegate the approved plan to `implementer`. Require focused tests and applicable
   AGENTS.md checks: `uv run ruff format --check .`, `uv run ruff check .`,
   `uv run pyright` in strict mode, and `uv run pytest` once Python tooling is configured.
   Frontend changes use established frontend checks; M0 validates instructions/config/docs.
4. Delegate independent read-only review to `reviewer`. Separate blockers from suggestions.
5. Send blockers to `implementer`, then request verification. Repeat until no blockers
   remain. Material scope or architecture changes require human approval; optional
   suggestions do not expand the current milestone.
6. Delegate meaningful stable changes to `documenter` for README.md and docs/ only.
   Ground approachable Python/AI explanations, architecture/diagrams, decisions, and
   learning exercises/questions in code and tests. Trivial edits need no extensive rewrite.
7. Report changed files, actual validation, review findings, and documentation for human
   review. Stop at the requested milestone; do not start the next one automatically.

## Boundaries

- Architect and Reviewer never edit files. Documenter never edits code, tests, dependencies,
  or configuration. Implementer follows approved scope and AGENTS.md.
- Python state and simulation rules are authoritative; cognition proposes intentions,
  runtime coordinates execution/barriers, and server/frontend expose state and controls.
- Keep deterministic execution testable from initial state, seed, and recorded decisions.
- Approval to implement is not approval to commit. Commit only on an explicit request.
