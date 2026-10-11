# Rust concepts used in Emergence

This is a progressive, source-grounded companion to [the milestone guide](GUIDE.md). It covers only constructs used in the repository. Follow the guide first; return here when a construct is in your way.

## Structs, enums, and `Option`

Rust uses a `struct` for a named record and an `enum` for a closed set of alternatives. In Emergence an activity is one of four states:

```rust
pub enum Activity {
    Gathering,
    Moving,
    BuildingShelter,
    Resting,
}
```

([source](../src/domain/agent.rs)). `Action` has both unit variants (`Eat`) and data variants (`Move(Direction)` and `Speak { ... }`) ([source](../src/domain/action.rs)). This resembles a TypeScript discriminated union or Java sealed hierarchy. Rust's `match` must address every variant, so adding an action makes missing engine handling a compiler error.

`Option<T>` replaces nullable values:

```rust
pub current_activity: Option<Activity>,
```

`None` means idle and `Some(Activity::Resting)` means active. Rust needs this explicit wrapper because every value must have a known valid type; there is no universal `null` hidden in arbitrary references. Common mistake: use an enum/`Option` for a finite state, not a sentinel string or integer. See the Milestone 1 walkthrough in [the guide](GUIDE.md#milestone-1--core-domain-model).

## Newtypes and derives

`AgentId` wraps a number in a new type:

```rust
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct AgentId(pub u64);
```

([source](../src/domain/agent.rs)). `AgentId(1)` is not interchangeable with `u64`, which is useful when an ID crosses many APIs. In Python and TypeScript this distinction is usually convention-only; Java would often require a small value class.

`derive` asks the compiler to generate trait implementations. `PartialEq`/`Eq` enable `assert_eq!`; `Clone` enables explicit duplication; `Ord` enables use as the key in `BTreeMap`; `Debug` enables `{:?}` output. Common mistake: `PartialEq` alone does not satisfy an ordered-map key; `Ord` is why `AgentId` works in [`World`](../src/domain/world.rs).

## Ownership, borrowing, and mutation

Rust tracks who owns data and whether it is temporarily lent. The engine exposes read-only borrows:

```rust
pub fn world(&self) -> &World { &self.world }
pub fn agent(&self, id: &AgentId) -> Option<&Agent> { self.agents.get(id) }
```

([source](../src/simulation/engine.rs)). `&self` borrows immutably; `&mut self`, as on `tick`, requires exclusive mutable access. Step by step: callers can inspect a returned `&Agent`, but cannot mutate it; to mutate internal state, only an engine method with `&mut self` can do so. This is the language mechanism supporting the ownership boundary described in [Architecture](ARCHITECTURE.md#current-architecture-at-a-glance).

Compared with Python objects or Java references, aliases are not assumed freely mutable. Rust rejects conflicting mutable/immutable access at compile time. Common mistake: trying to keep a `&Agent` while mutating the map that owns it. Instead, shorten the read borrow, copy/clone needed values, or use a scoped lookup.

`clone()` is deliberate, not implicit copying. The engine clones IDs when it needs an owned event field while map-derived data may still be borrowed ([source](../src/simulation/engine.rs)).

## Ordered collections and deterministic iteration

The world state uses standard-library B-tree collections:

```rust
pub agent_positions: BTreeMap<AgentId, Position>,
pub resources: BTreeMap<Position, ResourceNode>,
pub shelters: BTreeSet<Position>,
```

([source](../src/domain/world.rs)). A `BTreeMap` iterates keys in sorted order, unlike a hash map with no ordering guarantee. The engine takes pending actions and running IDs from ordered maps, so equal inputs have a defined processing order.

Rust needs key ordering because this collection implements sorted lookup/iteration, hence `Position` and `AgentId` derive `Ord`. This is similar to Java's `TreeMap`; Python's `dict` preserves insertion order but not sorted-key order. Common mistake: change these maps to `HashMap` and still assume deterministic agent ordering. See [Milestone 2](GUIDE.md#milestone-2--world-and-simulation-engine) for why the order matters.

## Pattern matching, `Result`, and safe arithmetic

The engine branches exhaustively over action variants with `match` ([source](../src/simulation/engine.rs)). It uses `let Some(target) = step(...) else { ... }` to stop early when a move cannot exist, and `matches!` in tests/validation to inspect enum shape. These are type-aware alternatives to nullable checks and `instanceof` chains.

Survival math uses explicit overflow policy:

```rust
a.needs.hunger = a.needs.hunger.saturating_add(self.rules.hunger_per_tick);
```

([source](../src/simulation/engine.rs)). `saturating_add` clamps at `u8::MAX`; `saturating_sub` clamps at zero; `checked_sub` produces `None` when north/west would cross zero. Step by step, `step` turns that `None` into a rejected invalid move rather than wrapping an unsigned coordinate.

Rust needs this because integer overflow is never silently chosen as a domain policy. Python integers grow, while Java/TypeScript number behavior differs and can hide mistakes. Common mistake: use `saturating_*` everywhere without considering whether clamping is correct; here it is explicitly used for bounded needs/coordinates.

`Result<T, E>` represents success or an error. The cognition boundary aliases it as `BrainResult<T>` ([source](../src/cognition/brain.rs)); the scheduler handles errors as cooldown cases rather than panicking. Common mistake: call `unwrap()` for normal external failure; the production paths map errors to `BrainError`.

## Traits, trait objects, and async futures

`Brain` is an interface-like trait:

```rust
pub trait Brain: Send + Sync {
    fn decide(&self, observation: Observation)
        -> Pin<Box<dyn Future<Output = BrainResult<AgentDecision>> + Send>>;
}
```

([source](../src/cognition/brain.rs)). A concrete brain receives an owned observation and eventually yields a decision or `BrainError`. `dyn Brain` is dynamic dispatch, like a Java interface reference; `Arc<dyn Brain>` shares it between scheduler tasks. `Send + Sync` say it is safe to transfer/share under Tokio's concurrency requirements.

The boxed, pinned `Future` is an explicit type-erased async result. In TypeScript this resembles returning `Promise<AgentDecision>`; in Java, `CompletionStage<AgentDecision>`. Rust needs `Pin<Box<dyn Future...>>` here because trait methods need one stable return type even when implementors' async state machines differ. Common mistake: hold a borrow into `Simulation` across an `await`; observation is owned specifically to avoid that. See [Milestone 3](GUIDE.md#milestone-3--cognition-and-orchestration).

## Tokio barriers and deterministic async collection

The scheduler's async method is an explicit synchronization boundary:

```rust
pub async fn resolve_required(&mut self, simulation: &mut Simulation) -> Vec<Event>
```

([source](../src/cognition/scheduler.rs)). It first constructs owned observations, then starts a Tokio task for every required decision. `Arc<Semaphore>` bounds how many tasks may actively call `Brain::decide`; `tokio::time::timeout` gives each call a wall-clock deadline. These are concurrent operations: a slow task does not prevent another permitted task from running.

Concurrency is not the same as advancing the simulation. The scheduler awaits each spawned task before it returns to the caller, and [`main.rs`](../src/main.rs) calls `Simulation::tick` only after that return. `Simulation` is passed as `&mut Simulation`, but the spawned tasks receive only owned `Observation` values and `Arc` clones of the brain/semaphore. This keeps a mutable simulation reference out of every task and across every task's `await`.

Arrival order is intentionally not a rule of the game. The implementation stores task handles and then responses in `BTreeMap<AgentId, _>` ([source](../src/cognition/scheduler.rs)), so it awaits and submits in key order. A network response can be physically first without becoming logically first. This is a useful pattern when async I/O must coexist with deterministic state transitions.

`SlotState` is a compact state machine: `NeedsDecision`, `Outstanding { request_id }`, `Resolved`, or `Cooldown { eligible_at_tick }`. The request ID is one monotonic number per agent; it identifies the outstanding result without a second generation counter. In contrast to a detached/background lifecycle, no cognition task is deliberately retained after the barrier returns. Common mistake: assume an awaited barrier makes requests serial. The tasks are spawned before awaiting their handles; the semaphore test in [`scheduler.rs`](../src/cognition/scheduler.rs) demonstrates bounded parallelism.

## Serialization, schema, and boundary DTOs

The decision types derive three external traits:

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
pub struct AgentDecision { pub action: DecisionAction }
```

([source](../src/cognition/decision.rs)). `Serialize` writes structured data, `Deserialize` reads it, and `JsonSchema` lets Schemars generate a schema. `AgentDecision::into_action` maps the provider-facing DTO into the domain's `Action`.

Step by step, `OpenAiBrain` generates/strictifies this schema, submits it as Responses API output format, then parses returned JSON ([source](../src/cognition/openai.rs)). Tests establish strict object settings and one successful response parse; they do not establish live network behavior. Common mistake: expose domain mutation or provider JSON directly to the engine. The DTO conversion is the intentional boundary.
