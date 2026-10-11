# Significant decisions

This is chronological by implemented milestone. It records source/test evidence, not reconstructed meeting history. “Inferred” means rationale is a reading of the code rather than an explicit record; “unknown” means the source does not establish it.

## Milestone 1 — Core domain model

### Data-only domain values

**Decision evidenced:** agents, actions, activities, needs, inventory, and world primitives are structs/enums in [`src/domain`](../src/domain); no domain type ticks, calls providers, or renders.

**Rationale:** inferred — this makes shared vocabulary testable and prevents a proposed action from directly changing physical state. Original discussion is unavailable.

### Proposed actions and physical activities differ

**Decision evidenced:** [`Action`](../src/domain/action.rs) and [`Activity`](../src/domain/agent.rs) are different enums, while agent state holds `Option<Activity>`.

**Rationale:** inferred — a command may be rejected whereas an activity records engine-accepted work. The type split and later engine events directly support this reading.

### Agent IDs support ordering

**Decision evidenced:** `AgentId` derives `Ord` ([`agent.rs`](../src/domain/agent.rs)).

**Rationale:** directly required by the `BTreeMap`/`BTreeSet` use in Milestone 2. Why a tuple newtype was selected over another ID representation is unknown.

## Milestone 2 — World and simulation engine

### One authoritative mutable-state owner

**Decision evidenced:** [`Simulation`](../src/simulation/engine.rs) keeps world, agents, pending/running work, sites, and tick count private; callers use submission, ticking, events, and read-only queries.

**Rationale:** inferred — central validation keeps callers, including cognition, from creating inconsistent physical state. Exact prior deliberation is unavailable.

### Ordered standard-library collections

**Decision evidenced:** [`World`](../src/domain/world.rs) and `Simulation` use `BTreeMap`/`BTreeSet`; tick derives pending/running IDs from them.

**Rationale:** inferred — sorted iteration provides reproducible processing without a dependency. Performance tradeoffs or benchmarks are unknown.

### Minimal asymmetric resource policy

**Decision evidenced:** gathering validates at start/completion; building deducts wood and reserves its tile at start ([`engine.rs`](../src/simulation/engine.rs)). Tests cover depleted completion and construction conflict.

**Rationale:** behavior is direct evidence; reasons for omitting a generic gather reservation are not separately documented. Do not read this as a general resource-locking framework.

### Events are outputs, not another state store

**Decision evidenced:** typed [`Event`](../src/simulation/event.rs) values leave submission/ticks, while mutations occur inside the engine.

**Rationale:** inferred — observers can react without owning authoritative state. Event sourcing is not implemented or evidenced.

## Milestone 3 — Cognition and orchestration

### Provider-independent brain contract

**Decision evidenced:** [`Brain`](../src/cognition/brain.rs) consumes `Observation` and returns `AgentDecision`; OpenAI and deterministic brains implement it.

**Rationale:** inferred — deterministic testing and HTTP can remain outside simulation. Comparisons with other provider abstractions are unknown.

### Observation is an owned, limited snapshot

**Decision evidenced:** [`Observation::from_simulation`](../src/cognition/observation.rs) copies focal/radius-limited nearby data.

**Rationale:** inferred — this safely crosses async work without retaining a `Simulation` borrow. Original design discussion is unknown.

### One outstanding monotonic request ID per agent

**Decision evidenced:** scheduler `Slot` has `next_request_id`/`outstanding`, and response handling compares IDs ([`scheduler.rs`](../src/cognition/scheduler.rs)).

**Rationale:** direct evidence of the stale-result mechanism. No generation counter exists; reasons for alternative designs are unknown.

### Tick cooldowns versus elapsed timeout

**Decision evidenced:** `eligible_at_tick` compares with `tick_count`, while Tokio `timeout` wraps `brain.decide` ([`scheduler.rs`](../src/cognition/scheduler.rs)).

**Rationale:** inferred — retry policy follows simulation time while external work needs real-time bounding. No live-provider reliability study is present.

### Strict schema stays at the provider edge

**Decision evidenced:** [`OpenAiBrain`](../src/cognition/openai.rs) strictifies Schemars output, prompts the Responses API, and parses output; `into_action` converts DTO to domain action.

**Rationale:** inferred — provider JSON remains outside the engine. Parser/schema unit tests exist; live API behavior is not established.

## Architecture refactor — Deterministic simulation time and cognition barriers

### Implemented: cognition is resolved at an awaited simulation boundary

**Decision evidenced:** [`CognitionScheduler::resolve_required`](../src/cognition/scheduler.rs) builds all eligible observations, spawns bounded tasks, awaits their handles, and only then returns; [`main.rs`](../src/main.rs) calls `Simulation::tick` after awaiting that method.

**Rationale:** directly established by the refactor's code and scheduler test `barrier_waits_without_advancing_simulation_time`: a delayed decision consumes wall-clock time while the tick count remains unchanged. Inferred design consequence: unlike the replaced detached/background request lifecycle, provider latency cannot make one agent experience extra simulated ticks before its decision is handled.

### Implemented: concurrent requests, deterministic application

**Decision evidenced:** request tasks are launched before handles are awaited; an `Arc<Semaphore>` bounds active calls; task handles and responses are held in `BTreeMap<AgentId, _>` ([`scheduler.rs`](../src/cognition/scheduler.rs)). The `requests_are_concurrent_and_limited` test observes a peak of two active requests with a concurrency limit of two.

**Rationale:** inferred — independent cognition can overlap in real time without letting response arrival order decide action-submission order. The implementation does not claim deterministic external-provider response content, only deterministic ordering of state transitions for supplied results.

### Implemented: compact per-agent request state

**Decision evidenced:** `SlotState` contains `NeedsDecision`, `Outstanding { request_id }`, `Resolved`, and `Cooldown { eligible_at_tick }`; `Slot` stores a single monotonic `next_request_id` ([`scheduler.rs`](../src/cognition/scheduler.rs)). No response channel, retained background-task collection, or generation counter appears in the scheduler.

**Rationale:** direct evidence of the current simplified mechanism. A response is accepted only for the matching outstanding request and a currently eligible agent. Whether future cancellation or more elaborate stale-result policies require additional state is deferred.

### Implemented: separate simulation and elapsed-time policies

**Decision evidenced:** cooldown promotion compares `eligible_at_tick` with `Simulation::tick_count`, while `tokio::time::timeout` wraps `brain.decide` ([`scheduler.rs`](../src/cognition/scheduler.rs)).

**Rationale:** inferred — retry eligibility belongs to repeatable world time; external I/O needs a real-duration bound. The documented tradeoff is explicit in implementation behavior: the slowest outstanding request can stall real-time loop progress at a barrier. No adaptive timeout, cancellation, or throughput policy is implemented.
