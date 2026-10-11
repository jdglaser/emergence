# Architectural decisions

These decisions guide the reboot. Domain, world, and simulation are implemented through M2; cognition and presentation describe planned direction. Milestone plans may refine details with human approval.

| Decision | Reason and trade-off |
| --- | --- |
| Start fresh with Python and React. | Python makes AI orchestration approachable; React/Canvas supports a clear interactive interface. The archived Rust implementation supplies lessons, not code to port. Rust optimization requires profiling evidence later. |
| Use Python 3.13+, uv, Ruff, pytest, and strict Pyright. | M1 configures dependency management, formatting/linting, tests, and static checking. pytest-asyncio is added when async tests need it. |
| Use strict, frozen Pydantic domain models. | Runtime constraints and schema generation share typed definitions. This adds one runtime dependency; frozen fields and immutable collections prevent ordinary mutation. Updates require validated reconstruction, since `model_copy(update=...)` bypasses validation. Generated schemas still need provider-specific compatibility checks in M4. |
| Keep needs on the same upward scale. | Hunger 0 means starving and 100 full; energy and health also improve upward. M2 adds bounded decay and health damage after hunger/energy reach zero. |
| Separate capability knowledge from requirements. | The shared catalog defines one-food eating and five-wood/suitable-site shelter costs. Agents initially know every capability even when unaffordable; simulation checks executability against actual state. |
| Keep Python authoritative. | Simulation owns rules and updates world state. Cognition proposes intentions; server/browser transport and display outcomes. This makes engine tests independent of providers and rendering. |
| Separate intention text, primitive requests, and accepted tasks. | Future cognition maintains descriptive intention text and selects a typed request. M2 movement tasks retain a destination and progress across ticks; other actions finish in one tick. Composite work and interruptions arrive later. |
| Route using journey knowledge and validate against actual state. | M2 A* receives observed passable tiles, with radius-3 square visibility. Journey knowledge refreshes locally and preserves earlier observations. Dynamic obstructions cause rerouting or waiting without erasing the destination. Exhaustion/death can fail travel; richer knowledge is deferred. |
| Allow one agent per tile with atomic movement. | Following, swaps, and closed cycles execute when all required occupants successfully leave. Seeded equal-weight lotteries select competing claims once; dependency pruning removes blocked winners without rerolling or promoting losers. Stationary and dead agents remain obstacles. |
| Remove depleted sources permanently. | Sources block occupancy and are gathered cardinally from adjacent tiles. The final unit removes the source; underlying terrain determines passability. No automatic regeneration is implemented. |
| Keep persistence in memory for M2. | Validated immutable world snapshots survive between ticks and old snapshots remain unchanged. Disk save/load and RNG checkpoint restoration need later scope. |
| Treat interruptions as explicit choices. | A conversation request should not erase an existing goal. Tasks can suspend/resume where appropriate, with concrete policies defined in their milestones. |
| Resolve required cognition at synchronized barriers. | All required decisions use a consistent snapshot and are applied in deterministic order. This simplifies reproducibility but pauses authoritative progression while a slow request reaches its timeout/fallback. |
| Promise conditional determinism. | Replay requires initial state, seed, and recorded decisions/fallbacks; it cannot assume identical live LLM output. Seeded conflicts and stable ordering keep execution repeatable. Cosmetic randomness stays independent. |
| Use Starlette and a versioned WebSocket protocol for the interface. | A small async server can publish state/events and accept controls. React owns UI state; Canvas draws the world using animation frames. API credentials and model calls stay on the backend. |

The reset archive is `../emergence-rust-archive-20261011-m0/repository-before-reset.tar.gz`. Git history and unrelated local artifacts were preserved. Legacy launchers, secrets, and logs are excluded from the active application design.

New entries should record decisions that change how the system behaves or can be extended. Routine file moves and milestone completion belong in [the roadmap](ROADMAP.md), not a growing historical narrative here.
