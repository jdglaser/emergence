# Roadmap

Every milestone requires a focused design and human approval before implementation. Completion includes relevant checks, independent review, corrections to blocking findings, and accurate documentation. Finishing a milestone does not authorize starting the next one.

| Milestone | Scope | Completion evidence | Status |
| --- | --- | --- | --- |
| M0 — Foundation | Archive/reset Rust application; establish architecture, instructions, roles, workflow, and tooling direction. | Active Rust application removed; Git and unrelated files preserved; docs and local agent instructions agree on Python/React. | Complete |
| M1 — Domain | Strict frozen Pydantic agents, positions, personality, needs, inventory, capabilities/knowledge, intention text, requests, task status, and events; minimal Python project. | 82 domain tests; uv project/lockfile; Ruff and strict Pyright checks passed; documented commands. No execution or LLM integration. | Complete |
| M2 — The Living World | Exclusive grid occupancy, terrain, permanently depleting resources, adjacent gathering, survival, shelters, ticks/events, seeded conflicts, radius-3 visibility, persistent destination movement, knowledge-limited A* and obstacle replanning/waiting. | 169 tests across domain/world/simulation; Ruff and strict Pyright checks passed; reproducible state/events, contention fairness, movement continuation and knowledge limits. No UI, LLM calls, or disk persistence. | Complete |
| M3 — Autonomous work | Extend existing movement into gather/build tasks that travel and work; richer terrain knowledge across journeys and appropriate replanning/task transitions. | Tests demonstrate composite travel/work without per-tick decisions and clear knowledge/execution boundaries. Basic A*, visibility, persistent movement, and collision replanning already exist in M2. | Planned |
| M4 — Cognition and orchestration | Test brain, async OpenAI Responses integration, validated intentions, eligibility, concurrency, timeout fallbacks, synchronized barriers, interruptions. | Tests verify no advancement during required barriers, deterministic decision application, and interruption handling. Full conversations deferred. | Planned |
| M5 — The Living Forest | Starlette, versioned WebSockets, React/TypeScript/Vite, Canvas, selection, inspection, events, controls, cognition indicators. | Integration checks show authoritative backend updates, responsive controls, and browser rendering independent of simulation ticks. | Planned |
| M6 — Memory | Formation, retrieval, memory-informed decisions, inspection. | Tests and evaluation scenarios show relevant memory reaching cognition with explicit limits. | Planned |
| M7 — Communication | Conversation requests, accept/ignore choices, task suspension/resumption, message exchange and events. | Tests show delivery, interruption choices, and appropriate task resumption. | Planned |
| M8 — Social dynamics | Relationship state, trust/affinity, social memory, cooperation/conflict, social structures. | Behavioral evaluation scenarios plus tests for explicit rules and deterministic state updates. | Planned |

These are scopes, not frozen class designs. Each Architect should choose the smallest coherent implementation for the requested milestone and identify its dependencies, tests, and deferred work.

M4 establishes generic interruption handling; M7 adds conversation-specific behavior. M1 represents suspended task status but defines no formal goal or interruption model. M2 executes movement state across ticks; M3 extends task execution to composite work. Cognition will maintain descriptive intention text and select the next primitive request; deterministic tasks execute it.

See [architecture](ARCHITECTURE.md) for boundaries and [engineering instructions](../AGENTS.md) for the approval/review workflow.
