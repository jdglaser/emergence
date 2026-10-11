# Emergence learning guide

This guide follows the code in the order it was built. It targets an experienced Python, TypeScript, or Java engineer new to Rust. Planned work is never described as implemented. Use [Architecture](ARCHITECTURE.md) for the cross-cutting view and [Rust concepts](RUST_CONCEPTS.md) for language details.

## Milestone 1 — Core domain model

### What was built

The domain layer provides typed descriptions of an agent and the commands it might propose: [`Agent`, `AgentId`, needs, inventory, and personality](../src/domain/agent.rs), plus [`Action`, `Direction`, and `ResourceKind`](../src/domain/action.rs). `Activity` is separate from `Action`: `AgentState.current_activity` is `Option<Activity>`.

### Why it is needed and how it fits

The simulation needs unambiguous data before it can validate movement or gathering. These types contain no ticking, provider calls, persistence, or rendering. They are shared vocabulary: simulation owns/changes them later, while cognition proposes `Action` values. A proposal therefore does not masquerade as a successful world change.

### Concrete execution flow

1. Construct `AgentId(1)`, a distinct type instead of a bare integer.
2. Put personality, `SurvivalNeeds`, and `Inventory` into an `Agent` ([`agent_contains_its_domain_data`](../src/domain/agent.rs)).
3. Represent idle state as `AgentState { current_activity: None }`; accepted work becomes `Some(Activity::Gathering)` ([`state_distinguishes_idle_and_active_agents`](../src/domain/agent.rs)).
4. Represent a proposal independently, for example `Action::Speak { message, recipient: vec![AgentId(2)] }`; recipients are explicit ([`speech_has_explicit_recipients`](../src/domain/action.rs)).

### Rust concepts in context

This milestone introduces data-carrying enums, `Option`, newtypes, and derives. See [Structs, enums, and `Option`](RUST_CONCEPTS.md#structs-enums-and-option) and [Newtypes and derives](RUST_CONCEPTS.md#newtypes-and-derives).

### Decisions and complexity

Essential complexity: distinct ID, command, and activity concepts. Incidental complexity intentionally avoided: no generic entity abstraction, ECS, executor, or validation framework. Speech and resource-giving are modeled but not executed.

### Understand before proceeding

- An enum variant carries exactly the data that command needs.
- `Option<Activity>` reports whether work exists; it does not track progress.
- `AgentId: Ord` enables the deterministic maps used next.

### Safe exercise (10–20 minutes)

Add a test that creates an agent with `Some(Activity::Moving)` and asserts its name, ID, and activity are retained. Do not add fields or behavior.

Hints: copy the construction pattern in [`agent.rs`](../src/domain/agent.rs); `assert_eq!` works because the types derive `PartialEq`/`Eq`; run the project checks afterward.

### Questions

1. Why is `Activity` not another `Action` variant?
2. What does `Option<Activity>` express that an “idle” string would not?

#### Answers

1. An action is proposed and can be rejected; an activity is work already accepted by the engine.
2. It makes idle/active a closed compiler-checked state rather than a string convention.

## Milestone 2 — World and simulation engine

### What was built

[`World`](../src/domain/world.rs) adds a bounded grid, positions, resource nodes, and shelter positions. [`Simulation`](../src/simulation/engine.rs) privately owns agents, pending commands, running work, construction-site reservations, and tick count. [`Rules`](../src/simulation/rules.rs) holds tunable values; [`Event`](../src/simulation/event.rs) reports outcomes.

### Why it is needed and how it fits

This is the authoritative physical layer. Callers may request commands, but only the engine changes inventory, position, needs, activity, and shelters. It creates the seam that cognition later uses without bypassing validation.

### Concrete execution flow: multi-tick gather

1. `submit_action` stores a gather for an existing, non-busy agent; duplicate/busy attempts get rejection events ([`Simulation::submit_action`](../src/simulation/engine.rs)).
2. `tick` increments time, starts pending work in `AgentId` order, applies survival changes, then advances active work ([`Simulation::tick`](../src/simulation/engine.rs)).
3. Start-time validation confirms a matching node under the agent, marks `Activity::Gathering`, stores private remaining work, and emits `ActivityStarted`.
4. Completion checks again before decrementing the node and adding inventory. Two agents can start on one unit but only one finishes; the other gets `ResourceUnavailable` ([`gathering_revalidates_resource_at_completion`](../src/simulation/engine.rs)).
5. Completion clears activity and emits `ActivityCompleted`.

### Rust concepts in context

Study [Ownership, borrowing, and mutation](RUST_CONCEPTS.md#ownership-borrowing-and-mutation), [Ordered collections and deterministic iteration](RUST_CONCEPTS.md#ordered-collections-and-deterministic-iteration), and [Pattern matching, `Result`, and safe arithmetic](RUST_CONCEPTS.md#pattern-matching-result-and-safe-arithmetic).

### Decisions and complexity

Essential: one mutation authority, deterministic order, lifecycle state, and completion-time resource validation. Private `Running` and `sites` are incidental mechanics. Gathering does not reserve resources; building spends wood and reserves only a tile. This is deliberately narrower than a generic reservation system.

### Understand before proceeding

- `submit_action` is not execution; most validation happens on a tick.
- `BTreeMap` determines repeatable start/completion order.
- Events report outcomes; they are not another mutable state store.

### Safe exercise (10–20 minutes)

Add an eating test: give an agent food/hunger, submit `Action::Eat`, tick once, and assert `Ate`, one fewer food, and configured hunger reduction.

Hints: reuse `sim()` and `agent()` in [`engine.rs`](../src/simulation/engine.rs); `Eat` starts during `tick`; use `Rules::default().eat_hunger_reduction`, not `20`.

### Questions

1. Why can two agents start gathering one resource but only one finish?
2. Why are building tiles reserved while nodes are not?
3. Why return `AgentBusy` instead of queueing a second command?

#### Answers

1. Availability is checked at start and intentionally rechecked at completion.
2. That is the implemented minimal policy: construction reserves a site; gathering has no general reservation system.
3. A future decision is expected after the activity completes.

## Milestone 3 — Cognition and orchestration

### What was built

Current source contains a provider-independent [`Brain`](../src/cognition/brain.rs), typed decision DTOs in [`decision.rs`](../src/cognition/decision.rs), radius-limited observations in [`observation.rs`](../src/cognition/observation.rs), an async scheduler in [`scheduler.rs`](../src/cognition/scheduler.rs), a deterministic delayed brain, and an OpenAI Responses API adapter. [`main.rs`](../src/main.rs) uses the deterministic brain, not a live API.

### Why it is needed and how it fits

Cognition chooses commands without putting provider state in the simulation domain. It observes an owned snapshot, returns a typed proposal, and delegates acceptance to the engine. The scheduler now makes that handoff at a **synchronized cognition barrier**: it finishes the decisions required at one simulation boundary before the caller advances a tick.

The replaced background-request arrangement could let the outer loop keep ticking while a slow request was still thinking. Its agent then experienced more hunger/energy/world time before it could propose an action than an agent whose request returned quickly. That is a simulation-time latency bias: network or provider delay changes which simulated opportunities an agent receives. The barrier deliberately trades wall-clock throughput for equal simulation-time treatment.

### Concrete execution flow: one cognition boundary

1. `resolve_required` reads the current tick, promotes reached cooldowns, and visits agents in `AgentId` order. For each eligible `NeedsDecision` slot, it builds an owned observation from the same unchanged simulation state ([`Observation::from_simulation`](../src/cognition/observation.rs), [`CognitionScheduler::resolve_required`](../src/cognition/scheduler.rs)).
2. It assigns that agent's next monotonically increasing request ID and changes the slot to `Outstanding`. It then starts Tokio tasks for all gathered requests. A semaphore limits active `Brain::decide` calls, and Tokio `timeout` bounds each call by real elapsed time.
3. The barrier awaits every task. It stores their results in a `BTreeMap<AgentId, _>`, so a response that arrives first does not get applied first.
4. It walks that ordered result map and, only for the matching outstanding request while the engine still says the agent is eligible, converts the DTO and calls `Simulation::submit_action`. An accepted action marks the slot `Resolved`; failure or rejection moves it to `Cooldown { eligible_at_tick }`.
5. Only after the awaited method returns does the outer loop call `Simulation::tick`; then `observe_events` turns completed activities and successful eating into the next `NeedsDecision` state, while rejection takes cooldown precedence ([`main.rs`](../src/main.rs), [`scheduler.rs`](../src/cognition/scheduler.rs)).

For example, at tick 12, Aster and Birch can both be idle and eligible. The scheduler snapshots both at tick 12, starts both requests concurrently, and Birch may answer first. If Aster is slower, tick 12 still does not become tick 13 until Aster's response or timeout is handled. Their actions are nevertheless submitted Aster-then-Birch when IDs sort that way. The engine then advances exactly one tick. Neither agent loses simulated time merely because its cognition took longer in real time.

### Simulation time versus wall-clock time

`Simulation::tick_count` is simulation time: it changes only when [`Simulation::tick`](../src/simulation/engine.rs) is called. `eligible_at_tick` therefore makes retry policy reproducible in terms of world turns. `tokio::time::timeout`, deterministic-brain delays, and the optional `EMERGENCE_TICK_INTERVAL_MS` sleep are wall-clock concerns. A slowest request can stall the demonstration's real time, but cannot advance needs or activity progress while the barrier is waiting.

### Rust concepts in context

Read [Traits and the async boundary](RUST_CONCEPTS.md#traits-trait-objects-and-async-futures), [Tokio barriers and deterministic async collection](RUST_CONCEPTS.md#tokio-barriers-and-deterministic-async-collection), and [Serialization and boundary DTOs](RUST_CONCEPTS.md#serialization-schema-and-boundary-dtos). The simulation itself does not require Tokio or HTTP APIs.

### Decisions and complexity

Essential: snapshots before await, bounded concurrency, a tick-stable barrier, deterministic action application, and engine validation. The simplified `Slot` holds only `NeedsDecision`, `Outstanding { request_id }`, `Resolved`, or tick-based `Cooldown`; it does not retain a background response channel, a long-lived request task, or a separate generation counter. `OpenAiBrain` strictifies a Schemars schema and tests schema/parser behavior ([`openai.rs`](../src/cognition/openai.rs)); live network integration is not demonstrated. No cancellation, streaming, memory, relationships, or broader retry policy exists.

### Understand before proceeding

- The barrier freezes simulated time, not wall-clock time.
- Concurrent request completion order cannot change submission order.
- Request timeout is real time; retry cooldown is simulation time; engine validation is final.

### Safe exercise (10–20 minutes)

Add a scheduler test that gives one agent a delayed `Rest` decision, calls `resolve_required`, and asserts that `tick_count()` is unchanged until the awaited call returns.

Hints: follow [`barrier_waits_without_advancing_simulation_time`](../src/cognition/scheduler.rs); use `DeterministicTestBrain` with a short delay; do not call `Simulation::tick` in the test before the assertion.

### Questions

1. Why does the scheduler await all requests when it already uses concurrent Tokio tasks?
2. How can a fast response fail to gain priority over a slow response?
3. Which clock controls cooldowns, and which clock controls HTTP-style request timeouts?

#### Answers

1. Concurrency runs independent thought at once; awaiting the set is the barrier that prevents simulation time from advancing during that thought.
2. Results are collected and applied through `BTreeMap<AgentId, _>`, rather than in completion order.
3. Cooldowns use `eligible_at_tick` and simulation ticks; timeouts use elapsed wall-clock time.

## Deterministic randomized conflict resolution

### What was built

The simulation now resolves only genuine, mutually exclusive contention with a seeded pseudo-random draw. [`Simulation::new`](../src/simulation/engine.rs) uses one stable default seed; [`Simulation::with_seed`](../src/simulation/engine.rs) lets a caller supply a seed for a reproducible run. The resolver currently gives every contender weight `1`, while its private weighted-selection shape leaves a deliberately small future extension point for modifiers such as quickness.

This is not an attribute or skill system, and the random generator is not intended for cryptography. It is a deterministic game-rule tool: the same state, seed, and submitted decisions produce the same selections.

### When a lottery happens—and when it does not

Shared occupancy is still allowed. Two agents on the same tile do not automatically compete. Nor does the engine draw randomness for movement, rest, eating, ordinary action validation, sufficient resources, or a lone builder.

A draw happens only after normal validation identifies a scarce shared outcome:

1. When two or more otherwise-valid [`Action::BuildShelter`](../src/domain/action.rs) requests target the same unreserved tile in one tick, the engine selects one builder. It deducts only that winner's wood and reserves that site; other contenders receive `ConstructionSiteReserved`.
2. When gathering activities finish together at the same `(position, resource kind)` and fewer units remain than finishers, the engine selects as many winners as units. Each winner receives one unit; other finishers receive `ResourceUnavailable`, and every activity still completes.

If a resource has enough units for all ready gatherers, everyone succeeds and the RNG does not advance. A build already invalid because of insufficient wood, an existing shelter, or an earlier reservation is rejected normally rather than entering the lottery.

### Concrete walkthrough: two agents, one wood

At position `(1, 1)`, Aster (`AgentId(1)`) and Birch (`AgentId(2)`) both submit `Gather(Wood)`. The node contains one wood.

1. On the first tick, both gather activities start because the node is nonempty.
2. On their completion tick, the engine puts both ready activities under the same position/resource key. The `BTreeMap`-backed collection yields contenders in sorted `AgentId` order.
3. Because one unit is available for two contenders, [`select_without_replacement`](../src/simulation/engine.rs) runs one equal-weight draw from the seeded RNG.
4. The winner gets `Event::Gathered`; the other receives `ActionRejected { ResourceUnavailable }`; both receive `ActivityCompleted`.

The fixed-seed tests [`same_seed_reproduces_contested_gather_outcome`](../src/simulation/engine.rs) and [`equal_weight_contenders_can_each_win_across_fixed_seeds`](../src/simulation/engine.rs) demonstrate the two complementary goals: replayability for one seed, and no built-in `AgentId` advantage across a set of seeds.

### Readability convention

[`AGENTS.md`](../AGENTS.md) now formalizes the formatting discipline used for nontrivial Rust: let `rustfmt` keep its conventional layout, leave a blank line between adjacent functions/methods/tests, and use blank lines to separate validation, mutation, and event-emission phases. This is a reading aid, not behavior: the public simulation rules are unchanged.

### Rust concepts in context

Read [Ordered collections and deterministic iteration](RUST_CONCEPTS.md#ordered-collections-deterministic-collection-and-seeded-selection) and [private helpers and weighted selection](RUST_CONCEPTS.md#private-helpers-and-a-narrow-future-weight-hook). They explain why sorted contender collection is needed before a seeded choice.

### Safe exercise (10–20 minutes)

Add a focused test for two simultaneous shelter builds using `Simulation::with_seed`. Assert that exactly one `ActivityStarted` event and one `ConstructionSiteReserved` rejection occur, and that only one agent spends wood.

Hints: adapt [`contested_build_selects_one_builder_and_rejects_the_other`](../src/simulation/engine.rs); keep both agents on one tile; do not assert a particular winning ID unless the test is specifically about a chosen seed; run the Cargo checks afterward.

### Questions

1. Why are contenders collected in sorted order before selection if the winner is random?
2. Why does a two-agent shared tile not itself require a lottery?
3. Why is the RNG called only when availability is lower than demand?

#### Answers

1. A seed can replay choices only when the candidate sequence is also stable across runs.
2. Occupancy is not exclusive in this world; only the claimed build site or scarce resource unit is.
3. Avoiding needless draws preserves non-conflicting behavior and prevents unrelated RNG-state changes from affecting later real conflicts.

## Suggested next reading

Read [Architecture](ARCHITECTURE.md) for state ownership, then [Decisions](DECISIONS.md) for direct evidence versus inferred rationale.

## What You Just Built

A reproducible conflict resolver that replaces fixed ID priority only when agents genuinely contend for a scarce result.

## How It Works

The engine collects contenders in sorted order, then makes an equal-weight seeded draw only for contested builds or insufficient simultaneous gather completions.

## Three Things to Understand

1. Deterministic collection and seeded selection are both needed for replayability.
2. Equal weights are current policy; the private hook does not add agent attributes.
3. Shared occupancy and non-conflicting actions do not consume random numbers.

## Try This Yourself

Complete the shelter-build exercise above and compare two runs with the same seed.

## Check Your Understanding

Answer the three conflict questions before reading their answers, especially why a lottery is not a general ordering rule.

## Suggested Next Reading

Read [Architecture](ARCHITECTURE.md#deterministic-contention-resolution) for tick-level flow, then [Decisions](DECISIONS.md#deterministic-randomized-contention-resolution) for the current scope and deferrals.
