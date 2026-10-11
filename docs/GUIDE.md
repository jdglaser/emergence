# Learning guide

Start with the executable example in [README](../README.md), then use [architecture](ARCHITECTURE.md) for the rules and [roadmap](ROADMAP.md) for future scope. M2 provides a running Python simulation; no model or browser participates yet.

## Follow one journey

The README creates Ada at `(0, 0)` and submits `Move(destination=(3, 0))`. Trace `Simulation.step` in [engine.py](../src/emergence/simulation/engine.py): it validates the target against the starting world, creates a task, advances one step, applies survival, and publishes a new snapshot. The first accepted tick already moves Ada to `(1, 0)`.

The next two calls to `step()` contain no decisions. `_move` reads the active task's remaining route and continues until arrival. `AgentMoved` describes each step; `TaskCompleted` marks arrival. The task record remains attached with completed status. `NeedsChanged` compares the agent's starting needs with the entire tick's result, including action effects and survival.

Read `test_destination_move_continues_without_decisions_and_completes` in [engine tests](../tests/simulation/test_engine.py). This is the foundation for future cognition: choose a destination once, let deterministic execution handle the journey.

## Values, state, and validation

[Domain values](../src/emergence/domain/values.py) use strict, frozen Pydantic models. Type hints let Pyright check code statically; Pydantic validates actual runtime values. `Annotated` adds constraints such as 0–100 needs. Strict Python input rejects `"50"` and `True` as integer scores. JSON validation interprets JSON forms of enums and collections through `model_validate_json`.

An agent composes identity, position, personality, needs, inventory, capability knowledge, intention text, and an optional task. Knowledge differs from affordability: Ada can know the shelter capability without possessing its five wood. The catalog defines inventory costs; rules define effects; engine validation combines those with actual world state.

The engine reconstructs updates using `Agent.model_validate({**agent.model_dump(), ...})`. Reconstruction validates changed data and preserves unrelated fields, including intention. Avoid `model_copy(update=...)`, which skips validation. Frozen nested records and tuples allow retaining an old world snapshot while later ticks publish new ones. See `test_empty_ticks_are_persistent_and_previous_snapshot_is_immutable`.

## Learn only what the agent can see

[World visibility](../src/emergence/world/models.py) is a clipped square: radius 3 means at most 7×7 tiles, including diagonals. It does not model sight blocked by trees or walls. Movement remains cardinal.

[A*](../src/emergence/simulation/pathfinding.py) accepts known passable positions and blocked positions; it cannot access the world. Manhattan distance estimates remaining travel. A priority queue explores promising positions, with coordinate tie-breaking producing a stable route. The task retains passability observed during this journey, updating its visible area each tick. It does not retain exploration knowledge for the next journey.

If another agent occupies the next step, the engine replans around visible occupants. If it cannot find a route, `MovementWaiting` leaves the destination intact. There is no three-tick collision failure or new brain request. Survival still drains needs, so waiting is not free indefinitely. Read the dynamic-obstacle and temporary-blockage tests in [engine tests](../tests/simulation/test_engine.py).

## Contention and ordering

Two agents may independently propose entry into the same tile. Claims are collected before execution, sorted deterministically, then a seeded lottery picks one winner. The other agent keeps its task. Movement applies atomically: Ada can follow Ben into his former tile if Ben successfully leaves, and swaps or closed cycles can also succeed. If Ben loses his claim or cannot leave, Ada waits too. Dependency pruning propagates these blocks without rerolling the lottery or promoting losers; waiting costs no movement energy. Read the atomic-swap and contention-loser/follower tests in [engine tests](../tests/simulation/test_engine.py).

Gathering works similarly when adjacent agents request more units than a source holds. Winners gather one unit each; losers fail without action costs. The final unit removes the source and emits `ResourceDepleted`. There is no regeneration. The opening becomes available for movement next tick because movement uses the tick's starting world.

Seeded randomness alone is insufficient for reproducibility: caller decisions, initial state, rules, and ordering also matter. Uncontested actions consume no random draws. Compare the replay/input-order, equal-weight fairness, and noncontention tests in [engine tests](../tests/simulation/test_engine.py).

## Exercises

1. Run the README journey and print each event's `kind`. Why does `TaskStarted` appear once while `AgentMoved` appears three times?
2. Place a one-unit food source adjacent to Ada, gather it, then move onto its former tile on the next tick. Why would the move be invalid before depletion?
3. Change the source terrain to water. Does gathering make the tile walkable?
4. Read the waiting/resumption test and explain why calling `step()` with no new request can eventually resume movement.
5. Calculate Ada's needs after one ordinary move from hunger/energy 100. Movement costs 1 energy; survival costs another 1 energy and 1 hunger.
6. Compare two simulations with the same seed and reversed decision insertion order. Which ordering rules keep both events and outcomes equal?

Run focused checks with `uv run pytest tests/simulation` or `uv run pytest tests/world`. Full validation commands are in README. M3 will extend travel into gather/build work and richer knowledge; cognition barriers and interruption policies arrive later.
