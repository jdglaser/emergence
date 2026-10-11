"""Executable rules, persistent travel, contention, and deterministic replay."""

from collections import Counter

import pytest
from pydantic import TypeAdapter, ValidationError

from emergence.domain.actions import (
    ActionRequest,
    BuildShelter,
    Eat,
    Gather,
    Move,
    Rest,
)
from emergence.domain.agent import Agent
from emergence.domain.capabilities import CAPABILITY_CATALOG, CapabilityId
from emergence.domain.events import (
    ActionRejected,
    AgentDied,
    AgentMoved,
    DomainEvent,
    MovementWaiting,
    NeedsChanged,
    RejectionReason,
    ResourceDepleted,
    ResourceGathered,
    TaskCompleted,
    TaskFailed,
    TaskStarted,
    TickAdvanced,
)
from emergence.domain.tasks import MovementProgress, Task, TaskStatus
from emergence.domain.values import (
    AgentId,
    Inventory,
    Needs,
    Personality,
    Position,
    Resource,
)
from emergence.simulation import Rules, Simulation
from emergence.world import ResourceSource, Terrain, Tile, World


def pos(x: int, y: int = 0) -> Position:
    return Position(x=x, y=y)


def aid(value: int = 1) -> AgentId:
    return AgentId(value=value)


def agent(
    identifier: int = 1,
    position: Position | None = None,
    *,
    hunger: int = 100,
    energy: int = 100,
    health: int = 100,
    food: int = 0,
    wood: int = 0,
    task: Task | None = None,
) -> Agent:
    return Agent(
        id=aid(identifier),
        name=f"Agent {identifier}",
        position=position or pos(0),
        personality=Personality(
            sociability=50,
            cooperativeness=50,
            cautiousness=50,
            curiosity=50,
            assertiveness=50,
        ),
        needs=Needs(hunger=hunger, energy=energy, health=health),
        inventory=Inventory(food=food, wood=wood),
        active_task=task,
    )


def world(
    *agents: Agent,
    width: int = 5,
    height: int = 3,
    special: dict[Position, Tile] | None = None,
) -> World:
    overrides = special or {}
    return World(
        width=width,
        height=height,
        tiles=tuple(
            overrides.get(pos(x, y), Tile())
            for y in range(height)
            for x in range(width)
        ),
        agents=agents,
    )


def source(resource: Resource = Resource.WOOD, quantity: int = 1) -> Tile:
    return Tile(
        terrain=Terrain.FOREST,
        source=ResourceSource(resource=resource, quantity=quantity),
    )


def test_empty_ticks_are_persistent_and_previous_snapshot_is_immutable() -> None:
    initial = world(agent())
    simulation = Simulation(initial)
    events = simulation.step()
    assert initial.tick == 0 and initial.agent(aid()).needs == Needs(
        hunger=100, energy=100, health=100
    )
    assert simulation.world.tick == 1
    assert simulation.world.agent(aid()).needs == Needs(
        hunger=99, energy=99, health=100
    )
    assert events == (
        NeedsChanged(
            agent_id=aid(),
            before=initial.agent(aid()).needs,
            after=simulation.world.agent(aid()).needs,
        ),
        TickAdvanced(tick=1),
    )
    simulation.step({})
    assert simulation.world.tick == 2
    with pytest.raises(ValidationError):
        simulation.world.__setattr__("tick", 99)


def test_destination_move_continues_without_decisions_and_completes() -> None:
    simulation = Simulation(world(agent(), width=4, height=1))
    first = simulation.step({aid(): Move(destination=pos(3))})
    assert simulation.world.agent(aid()).position == pos(1)
    assert sum(isinstance(e, TaskStarted) for e in first) == 1
    task = simulation.world.agent(aid()).active_task
    assert task is not None and task.status == TaskStatus.ACTIVE
    assert task.movement is not None and task.movement.route == (pos(2), pos(3))

    second = simulation.step()
    third = simulation.step()
    arrived = simulation.world.agent(aid())
    assert arrived.position == pos(3)
    assert arrived.needs.energy == 94  # Three steps and three survival losses.
    assert (
        arrived.active_task is not None
        and arrived.active_task.status == TaskStatus.COMPLETED
    )
    assert not any(isinstance(e, TaskStarted) for e in second + third)
    assert any(isinstance(e, TaskCompleted) for e in third)
    simulation.step({aid(): Rest()})
    assert simulation.world.agent(aid()).needs.energy == 99


@pytest.mark.parametrize(
    "target,reason",
    [
        (pos(4), RejectionReason.OUT_OF_RANGE),
        (pos(-1), RejectionReason.OUT_OF_RANGE),
        (pos(0), RejectionReason.INVALID_TARGET),
    ],
)
def test_move_target_validation(target: Position, reason: RejectionReason) -> None:
    simulation = Simulation(world(agent(), width=5, height=1))
    events = simulation.step({aid(): Move(destination=target)})
    assert events[0] == ActionRejected(
        agent_id=aid(), request=Move(destination=target), reason=reason
    )
    assert simulation.world.agent(aid()).position == pos(0)
    assert simulation.world.agent(aid()).needs.energy == 99


@pytest.mark.parametrize("tile", [Tile(terrain=Terrain.WATER), source()])
def test_move_cannot_enter_resource_or_water(tile: Tile) -> None:
    simulation = Simulation(world(agent(), special={pos(1): tile}))
    events = simulation.step({aid(): Move(destination=pos(1))})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.INVALID_TARGET
    )


def test_move_rejects_occupied_destination() -> None:
    simulation = Simulation(world(agent(), agent(2, pos(1))))
    events = simulation.step({aid(): Move(destination=pos(1))})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.OCCUPIED
    )


def test_move_route_never_uses_unobserved_detour() -> None:
    wall = {pos(1, y): Tile(terrain=Terrain.WATER) for y in range(4)}
    simulation = Simulation(world(agent(), width=3, height=5, special=wall))
    # A world-wide route exists through row 4, outside the initial radius 3.
    events = simulation.step({aid(): Move(destination=pos(2))})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.NO_ROUTE
    )
    assert simulation.world.agent(aid()).position == pos(0)


def test_busy_agent_rejects_new_request_but_existing_movement_continues() -> None:
    simulation = Simulation(world(agent(), height=1))
    simulation.step({aid(): Move(destination=pos(3))})
    events = simulation.step({aid(): Rest()})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.AGENT_BUSY
    )
    assert simulation.world.agent(aid()).position == pos(2)


def test_suspended_task_is_busy_and_does_not_move() -> None:
    task = Task(
        request=Move(destination=pos(2)),
        status=TaskStatus.SUSPENDED,
        movement=MovementProgress(
            route=(pos(1), pos(2)), destination=pos(2)
        ),
    )
    simulation = Simulation(world(agent(task=task), height=1))
    events = simulation.step({aid(): Rest()})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.AGENT_BUSY
    )
    assert simulation.world.agent(aid()).position == pos(0)
    assert simulation.world.agent(aid()).active_task == task


def test_dynamic_obstacle_replans_and_keeps_destination() -> None:
    simulation = Simulation(
        world(agent(position=pos(0, 1)), agent(2, pos(2, 0)), width=4)
    )
    simulation.step(
        {aid(): Move(destination=pos(3, 1)), aid(2): Move(destination=pos(2, 1))}
    )
    assert simulation.world.agent(aid()).position == pos(1, 1)
    assert simulation.world.agent(aid(2)).position == pos(2, 1)

    events = simulation.step()
    assert simulation.world.agent(aid()).position == pos(1, 0)
    assert any(isinstance(e, AgentMoved) and e.agent_id == aid() for e in events)
    for _ in range(3):
        simulation.step()
    moved = simulation.world.agent(aid())
    assert moved.position == pos(3, 1)
    assert (
        moved.active_task is not None
        and moved.active_task.status == TaskStatus.COMPLETED
    )
    assert moved.active_task.request == Move(destination=pos(3, 1))


def test_temporary_blockage_waits_beyond_three_ticks_and_resumes() -> None:
    simulation = Simulation(world(agent(), agent(2, pos(2)), width=5, height=1))
    simulation.step({aid(): Move(destination=pos(3))})
    assert simulation.world.agent(aid()).position == pos(1)
    for _ in range(5):
        events = simulation.step()
        assert any(
            isinstance(e, MovementWaiting) and e.agent_id == aid() for e in events
        )
        assert not any(isinstance(e, TaskFailed) for e in events)
    waiting = simulation.world.agent(aid())
    assert (
        waiting.active_task is not None
        and waiting.active_task.status == TaskStatus.ACTIVE
    )
    assert waiting.needs.energy == 93  # One movement cost, six survival costs.

    simulation.step({aid(2): Move(destination=pos(4))})
    events = simulation.step()
    assert simulation.world.agent(aid()).position == pos(3)
    assert any(isinstance(e, TaskCompleted) and e.agent_id == aid() for e in events)


def test_following_enters_vacated_tiles_in_the_same_movement_phase() -> None:
    simulation = Simulation(world(agent(), agent(2, pos(1)), width=4, height=1))
    events = simulation.step(
        {aid(): Move(destination=pos(2)), aid(2): Move(destination=pos(3))}
    )
    assert simulation.world.agent(aid()).position == pos(1)
    assert simulation.world.agent(aid(2)).position == pos(2)
    assert not any(isinstance(e, MovementWaiting) for e in events)
    simulation.step()
    assert simulation.world.agent(aid()).position == pos(2)
    assert simulation.world.agent(aid(2)).position == pos(3)
    assert simulation.world.agent(aid()).needs.energy == 96


def test_swaps_execute_atomically_and_preserve_exclusive_occupancy() -> None:
    simulation = Simulation(world(agent(), agent(2, pos(1)), width=2, height=1))
    events = simulation.step(
        {aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(0))}
    )
    assert not any(isinstance(e, ActionRejected) for e in events)
    assert [a.position for a in simulation.world.agents] == [pos(1), pos(0)]
    assert [a.needs.energy for a in simulation.world.agents] == [98, 98]
    assert [e.agent_id for e in events if isinstance(e, AgentMoved)] == [aid(), aid(2)]


def contested_movement(seed: int) -> tuple[World, tuple[DomainEvent, ...]]:
    simulation = Simulation(
        world(agent(), agent(2, pos(2)), width=3, height=1), seed=seed
    )
    events = simulation.step(
        {aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(1))}
    )
    return simulation.world, events


def test_contested_movement_uses_one_winner_and_loser_keeps_task() -> None:
    final, events = contested_movement(9)
    assert sum(a.position == pos(1) for a in final.agents) == 1
    assert len({a.position for a in final.agents}) == 2
    assert sum(isinstance(e, AgentMoved) for e in events) == 1
    assert sum(isinstance(e, MovementWaiting) for e in events) == 1
    loser = next(a for a in final.agents if a.position != pos(1))
    assert (
        loser.active_task is not None and loser.active_task.status == TaskStatus.ACTIVE
    )
    assert loser.needs.energy == 99


def test_seeded_equal_weight_movement_fairness_and_reproducibility() -> None:
    counts: Counter[int] = Counter()
    for seed in range(400):
        final, events = contested_movement(seed)
        assert (final, events) == contested_movement(seed)
        counts[next(a.id.value for a in final.agents if a.position == pos(1))] += 1
    assert 160 <= counts[1] <= 240 and 160 <= counts[2] <= 240


@pytest.mark.parametrize("resource", list(Resource))
def test_adjacent_gather_removes_depleted_source_and_does_not_regenerate(
    resource: Resource,
) -> None:
    simulation = Simulation(world(agent(), special={pos(1): source(resource)}))
    events = simulation.step({aid(): Gather(resource=resource, position=pos(1))})
    assert simulation.world.tile_at(pos(1)).source is None
    assert simulation.world.tile_at(pos(1)).walkable
    gathered = simulation.world.agent(aid())
    assert gathered.inventory.food == (1 if resource == Resource.FOOD else 0)
    assert gathered.inventory.wood == (1 if resource == Resource.WOOD else 0)
    assert gathered.needs.energy == 97
    assert any(isinstance(e, ResourceDepleted) for e in events)
    simulation.step({aid(): Move(destination=pos(1))})
    assert simulation.world.agent(aid()).position == pos(1)
    for _ in range(25):
        simulation.step()
    assert simulation.world.tile_at(pos(1)).source is None


def test_depleted_water_source_leaves_water_impassable() -> None:
    tile = Tile(
        terrain=Terrain.WATER, source=ResourceSource(resource=Resource.FOOD, quantity=1)
    )
    simulation = Simulation(world(agent(), special={pos(1): tile}))
    simulation.step({aid(): Gather(resource=Resource.FOOD, position=pos(1))})
    assert simulation.world.tile_at(pos(1)).source is None
    assert not simulation.world.tile_at(pos(1)).walkable


@pytest.mark.parametrize(
    "target,resource,reason",
    [
        (pos(1, 1), Resource.WOOD, RejectionReason.RESOURCE_UNAVAILABLE),
        (pos(2), Resource.WOOD, RejectionReason.RESOURCE_UNAVAILABLE),
        (pos(-1), Resource.WOOD, RejectionReason.OUT_OF_RANGE),
        (pos(1), Resource.FOOD, RejectionReason.RESOURCE_UNAVAILABLE),
    ],
)
def test_gather_validation_requires_observed_matching_resource(
    target: Position, resource: Resource, reason: RejectionReason
) -> None:
    simulation = Simulation(world(agent(), special={pos(1): source()}))
    events = simulation.step({aid(): Gather(position=target, resource=resource)})
    assert isinstance(events[0], ActionRejected) and events[0].reason == reason
    assert simulation.world.tile_at(pos(1)).source is not None
    assert simulation.world.agent(aid()).inventory == Inventory()


def gather_contest(
    seed: int, quantity: int = 1
) -> tuple[World, tuple[DomainEvent, ...]]:
    simulation = Simulation(
        world(
            agent(),
            agent(2, pos(2)),
            width=3,
            height=1,
            special={pos(1): source(quantity=quantity)},
        ),
        seed=seed,
    )
    return_events = simulation.step(
        {
            aid(): Gather(resource=Resource.WOOD, position=pos(1)),
            aid(2): Gather(resource=Resource.WOOD, position=pos(1)),
        }
    )
    return simulation.world, return_events


def test_scarce_gather_lottery_depletion_and_loser_spends_nothing() -> None:
    final, events = gather_contest(5)
    assert sum(a.inventory.wood for a in final.agents) == 1
    assert final.tile_at(pos(1)).source is None
    loser = next(a for a in final.agents if a.inventory.wood == 0)
    assert loser.needs.energy == 99
    assert (
        loser.active_task is not None and loser.active_task.status == TaskStatus.FAILED
    )
    assert sum(isinstance(e, ResourceDepleted) for e in events) == 1
    assert sum(isinstance(e, ResourceGathered) for e in events) == 1
    assert sum(isinstance(e, TaskFailed) for e in events) == 1


def test_noncontested_gather_all_succeed_and_fairness_is_equal_weight() -> None:
    final, _ = gather_contest(1, quantity=2)
    assert [a.inventory.wood for a in final.agents] == [1, 1]
    counts: Counter[int] = Counter()
    for seed in range(400):
        result, events = gather_contest(seed)
        assert (result, events) == gather_contest(seed)
        counts[next(a.id.value for a in result.agents if a.inventory.wood)] += 1
    assert 160 <= counts[1] <= 240 and 160 <= counts[2] <= 240


@pytest.mark.parametrize("hunger,expected", [(50, 74), (90, 99), (0, 24)])
def test_eat_cost_from_catalog_restore_then_decay(hunger: int, expected: int) -> None:
    food_cost = CAPABILITY_CATALOG[CapabilityId.EAT].resource_cost.food
    simulation = Simulation(world(agent(hunger=hunger, food=food_cost)))
    simulation.step({aid(): Eat()})
    ate = simulation.world.agent(aid())
    assert ate.inventory.food == 0 and ate.needs.hunger == expected
    assert ate.needs.health == 100


@pytest.mark.parametrize(
    "sheltered,energy,expected",
    [(False, 50, 59), (True, 50, 64), (True, 98, 99), (False, 0, 9)],
)
def test_rest_energy_and_shelter_bonus(
    sheltered: bool, energy: int, expected: int
) -> None:
    simulation = Simulation(
        world(agent(energy=energy), special={pos(0): Tile(shelter=sheltered)})
    )
    simulation.step({aid(): Rest()})
    assert simulation.world.agent(aid()).needs.energy == expected


def test_build_shelter_spends_catalog_cost_and_is_walkable() -> None:
    cost = CAPABILITY_CATALOG[CapabilityId.BUILD_SHELTER].resource_cost.wood
    simulation = Simulation(world(agent(wood=cost)))
    simulation.step({aid(): BuildShelter(position=pos(0))})
    assert (
        simulation.world.tile_at(pos(0)).shelter
        and simulation.world.tile_at(pos(0)).walkable
    )
    built = simulation.world.agent(aid())
    assert built.inventory.wood == 0 and built.needs.energy == 94


@pytest.mark.parametrize(
    "tile,target,reason",
    [
        (Tile(terrain=Terrain.FOREST), pos(0), RejectionReason.SITE_UNAVAILABLE),
        (Tile(shelter=True), pos(0), RejectionReason.SITE_UNAVAILABLE),
        (Tile(), pos(-1), RejectionReason.OUT_OF_RANGE),
    ],
)
def test_build_rejections_spend_nothing(
    tile: Tile, target: Position, reason: RejectionReason
) -> None:
    simulation = Simulation(world(agent(wood=5), special={pos(0): tile}))
    events = simulation.step({aid(): BuildShelter(position=target)})
    assert isinstance(events[0], ActionRejected) and events[0].reason == reason
    assert simulation.world.agent(aid()).inventory.wood == 5
    assert simulation.world.agent(aid()).needs.energy == 99


@pytest.mark.parametrize(
    "action,energy,food,wood,reason",
    [
        (Eat(), 100, 0, 0, RejectionReason.INSUFFICIENT_RESOURCES),
        (
            BuildShelter(position=pos(0)),
            100,
            0,
            4,
            RejectionReason.INSUFFICIENT_RESOURCES,
        ),
        (BuildShelter(position=pos(0)), 4, 0, 5, RejectionReason.INSUFFICIENT_ENERGY),
        (
            Gather(resource=Resource.WOOD, position=pos(1)),
            1,
            0,
            0,
            RejectionReason.INSUFFICIENT_ENERGY,
        ),
        (Move(destination=pos(2)), 0, 0, 0, RejectionReason.INSUFFICIENT_ENERGY),
    ],
)
def test_affordability_rejects_without_action_cost(
    action: ActionRequest, energy: int, food: int, wood: int, reason: RejectionReason
) -> None:
    simulation = Simulation(
        world(agent(energy=energy, food=food, wood=wood), special={pos(1): source()})
    )
    events = simulation.step({aid(): action})
    assert isinstance(events[0], ActionRejected) and events[0].reason == reason
    assert simulation.world.agent(aid()).inventory == Inventory(food=food, wood=wood)


def test_unknown_capability_and_unknown_agent_rejected() -> None:
    limited = Agent.model_validate(
        {**agent().model_dump(), "known_capabilities": frozenset({CapabilityId.REST})}
    )
    simulation = Simulation(world(limited))
    events = simulation.step({aid(): Eat(), aid(99): Rest()})
    rejected = [e for e in events if isinstance(e, ActionRejected)]
    assert [e.reason for e in rejected] == [
        RejectionReason.UNKNOWN_CAPABILITY,
        RejectionReason.UNKNOWN_AGENT,
    ]


@pytest.mark.parametrize(
    "hunger,energy,health,expected",
    [(1, 100, 100, 98), (100, 1, 100, 99), (1, 1, 100, 97), (0, 0, 1, 0)],
)
def test_survival_damage_thresholds_and_clamping(
    hunger: int, energy: int, health: int, expected: int
) -> None:
    simulation = Simulation(world(agent(hunger=hunger, energy=energy, health=health)))
    simulation.step()
    assert simulation.world.agent(aid()).needs.health == expected


def test_active_move_fails_when_energy_exhausted_without_another_step() -> None:
    simulation = Simulation(world(agent(energy=2), width=4, height=1))
    simulation.step({aid(): Move(destination=pos(3))})
    events = simulation.step()
    assert simulation.world.agent(aid()).position == pos(1)
    assert any(
        isinstance(e, TaskFailed) and e.reason == "insufficient_energy" for e in events
    )


def test_death_fails_task_once_is_terminal_and_still_blocks_tile() -> None:
    simulation = Simulation(
        world(agent(hunger=0, health=1), agent(2, pos(3)), width=4, height=1)
    )
    first = simulation.step({aid(): Move(destination=pos(2))})
    dead = simulation.world.agent(aid())
    assert dead.position == pos(1) and dead.needs.health == 0
    assert dead.active_task is not None and dead.active_task.status == TaskStatus.FAILED
    assert sum(isinstance(e, AgentDied) for e in first) == 1
    assert sum(isinstance(e, TaskFailed) for e in first) == 1
    events = simulation.step({aid(): Rest(), aid(2): Move(destination=pos(1))})
    assert simulation.world.agent(aid()) == dead
    assert not any(isinstance(e, AgentDied) for e in events)
    assert [e.reason for e in events if isinstance(e, ActionRejected)] == [
        RejectionReason.DEAD,
        RejectionReason.OCCUPIED,
    ]


def test_replay_and_input_order_produce_identical_states_and_events() -> None:
    first = agent()
    second = agent(2, pos(2))
    tile = {pos(1): source(quantity=2)}
    left = Simulation(world(first, second, special=tile), seed=123)
    right = Simulation(world(second, first, special=tile), seed=123)
    decision_sequence: list[dict[AgentId, ActionRequest]] = [
        {
            aid(): Gather(resource=Resource.WOOD, position=pos(1)),
            aid(2): Gather(resource=Resource.WOOD, position=pos(1)),
        },
        {aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(1))},
        {},
        {aid(): Rest(), aid(2): Rest()},
    ]
    for decisions in decision_sequence:
        assert left.step(decisions) == right.step(
            dict(reversed(tuple(decisions.items())))
        )
        assert left.world == right.world


def test_uncontested_actions_do_not_consume_conflict_randomness() -> None:
    initial = world(agent(), agent(2, pos(2)), width=3, height=1)
    left = Simulation(initial, seed=92)
    right = Simulation(initial, seed=92)
    left.step({aid(): Rest(), aid(2): Rest()})
    right.step()
    decisions = {aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(1))}
    left.step(decisions)
    right.step(decisions)
    assert [a.position for a in left.world.agents] == [
        a.position for a in right.world.agents
    ]


def test_events_roundtrip_and_needs_describe_full_tick_change() -> None:
    simulation = Simulation(world(agent(hunger=20, food=1)))
    events = simulation.step({aid(): Eat()})
    adapter = TypeAdapter[tuple[DomainEvent, ...]](tuple[DomainEvent, ...])
    assert adapter.validate_json(adapter.dump_json(events)) == events
    change = next(e for e in events if isinstance(e, NeedsChanged))
    assert change.before.hunger == 20 and change.after.hunger == 44
    assert events[-1] == TickAdvanced(tick=1)


def test_configurable_rules_use_visibility_and_effects_without_wall_time() -> None:
    rules = Rules(visible_radius=1, movement_energy=3, energy_loss=2, hunger_loss=2)
    simulation = Simulation(world(agent(), height=1), rules=rules)
    events = simulation.step({aid(): Move(destination=pos(2))})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.OUT_OF_RANGE
    )
    simulation.step({aid(): Move(destination=pos(1))})
    moved = simulation.world.agent(aid())
    assert moved.position == pos(1) and moved.needs.energy == 93
    assert moved.needs.hunger == 96


def test_live_movement_snapshot_roundtrips_and_revalidates_updates() -> None:
    simulation = Simulation(world(agent(), height=1))
    simulation.step({aid(): Move(destination=pos(3))})
    snapshot = simulation.world
    assert World.model_validate(snapshot.model_dump()) == snapshot
    assert World.model_validate_json(snapshot.model_dump_json()) == snapshot
    restored = Simulation(snapshot, seed=3)
    assert restored.step() == simulation.step()
    assert restored.world == simulation.world
    with pytest.raises(ValidationError):
        Agent.model_validate(
            {
                **snapshot.agent(aid()).model_dump(),
                "needs": {"hunger": 101, "energy": 90, "health": 100},
            }
        )


def test_movement_progress_is_restricted_to_move_tasks() -> None:
    with pytest.raises(ValidationError):
        Task(request=Rest(), movement=MovementProgress(destination=pos(0)))


def test_atomic_following_chain_with_a_free_tail() -> None:
    initial = world(agent(), agent(2, pos(1)), agent(3, pos(2)), width=4, height=1)
    simulation = Simulation(initial)
    decisions = {aid(i): Move(destination=pos(i)) for i in range(1, 4)}
    events = simulation.step(decisions)
    assert [a.position for a in simulation.world.agents] == [pos(1), pos(2), pos(3)]
    assert len({a.position for a in simulation.world.agents}) == 3
    assert [a.needs.energy for a in simulation.world.agents] == [98, 98, 98]
    assert sum(isinstance(e, TaskCompleted) for e in events) == 3
    assert not any(isinstance(e, MovementWaiting) for e in events)


def test_closed_movement_cycle_executes_without_any_free_tile() -> None:
    positions = (pos(0, 0), pos(1, 0), pos(1, 1), pos(0, 1))
    initial = world(
        *(agent(i + 1, p) for i, p in enumerate(positions)), width=2, height=2
    )
    destinations = positions[1:] + positions[:1]
    decisions = {aid(i + 1): Move(destination=p) for i, p in enumerate(destinations)}
    simulation = Simulation(initial)
    events = simulation.step(decisions)
    assert tuple(a.position for a in simulation.world.agents) == destinations
    assert len({a.position for a in simulation.world.agents}) == 4
    assert sum(isinstance(e, AgentMoved) for e in events) == 4
    assert sum(isinstance(e, TaskCompleted) for e in events) == 4


def travel_task(destination: Position, route: tuple[Position, ...]) -> Task:
    return Task(
        request=Move(destination=destination), movement=MovementProgress(route=route, destination=destination)
    )


def test_blocked_tail_propagates_waiting_through_existing_tasks() -> None:
    initial = world(
        agent(task=travel_task(pos(2), (pos(1), pos(2)))),
        agent(2, pos(1), task=travel_task(pos(3), (pos(2), pos(3)))),
        agent(3, pos(2)),
        width=4,
        height=1,
    )
    simulation = Simulation(initial)
    events = simulation.step()
    assert [a.position for a in simulation.world.agents] == [pos(0), pos(1), pos(2)]
    assert [a.needs.energy for a in simulation.world.agents] == [99, 99, 99]
    assert [e.agent_id for e in events if isinstance(e, MovementWaiting)] == [
        aid(),
        aid(2),
    ]
    assert not any(isinstance(e, AgentMoved) for e in events)
    assert all(
        a.active_task is not None and a.active_task.status == TaskStatus.ACTIVE
        for a in simulation.world.agents[:2]
    )


def test_stationary_destination_rejection_propagates_across_new_requests() -> None:
    simulation = Simulation(
        world(agent(), agent(2, pos(1)), agent(3, pos(2)), width=3, height=1)
    )
    events = simulation.step(
        {aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(2))}
    )
    rejected = [e for e in events if isinstance(e, ActionRejected)]
    assert [e.agent_id for e in rejected] == [aid(), aid(2)]
    assert all(e.reason == RejectionReason.OCCUPIED for e in rejected)
    assert not any(isinstance(e, TaskStarted) for e in events)


@pytest.mark.parametrize(
    "occupant_task,health,energy",
    [
        (None, 0, 100),
        (travel_task(pos(2), (pos(2),)), 100, 0),
        (
            Task(
                request=Move(destination=pos(2)),
                status=TaskStatus.SUSPENDED,
                movement=MovementProgress(route=(pos(2),), destination=pos(2)),
            ),
            100,
            100,
        ),
        (Task(request=Move(destination=pos(2))), 100, 100),
    ],
)
def test_ineligible_occupants_block_new_moves(
    occupant_task: Task | None, health: int, energy: int
) -> None:
    occupant = agent(2, pos(1), task=occupant_task, health=health, energy=energy)
    simulation = Simulation(world(agent(), occupant, width=3, height=1))
    events = simulation.step({aid(): Move(destination=pos(1))})
    assert (
        isinstance(events[0], ActionRejected)
        and events[0].reason == RejectionReason.OCCUPIED
    )
    assert simulation.world.agent(aid()).position == pos(0)


def test_contention_loser_keeps_followers_waiting_without_extra_energy() -> None:
    initial = world(
        agent(),
        agent(2, pos(1)),
        agent(3, pos(2, 1)),
        agent(4, pos(3, 1)),
        width=4,
        height=2,
    )
    decisions = {
        aid(): Move(destination=pos(1)),
        aid(2): Move(destination=pos(2)),
        aid(3): Move(destination=pos(2)),
        aid(4): Move(destination=pos(2, 1)),
    }
    for seed in range(12):
        simulation = Simulation(initial, seed=seed)
        events = simulation.step(decisions)
        moved_ids = {e.agent_id for e in events if isinstance(e, AgentMoved)}
        assert moved_ids in ({aid(), aid(2)}, {aid(3), aid(4)})
        assert len({a.position for a in simulation.world.agents}) == 4
        for a in simulation.world.agents:
            assert a.needs.energy == (98 if a.id in moved_ids else 99)
            if a.id not in moved_ids:
                assert a.active_task is not None
                assert a.active_task.status == TaskStatus.ACTIVE


def test_pruned_lottery_winner_does_not_promote_runner_up() -> None:
    # A and C compete for B's tile while B wants A's tile. If C wins,
    # B depends on losing A, then C depends on pruned B: nobody can move.
    initial = world(agent(), agent(2, pos(1)), agent(3, pos(1, 1)), width=2, height=2)
    decisions = {
        aid(): Move(destination=pos(1)),
        aid(2): Move(destination=pos(0)),
        aid(3): Move(destination=pos(1)),
    }
    observed: set[int] = set()
    for seed in range(30):
        simulation = Simulation(initial, seed=seed)
        events = simulation.step(decisions)
        moved_ids = {e.agent_id for e in events if isinstance(e, AgentMoved)}
        assert moved_ids in (set(), {aid(), aid(2)})
        observed.add(len(moved_ids))
        assert len({a.position for a in simulation.world.agents}) == 3
    assert observed == {0, 2}


def test_atomic_cycle_and_contention_are_independent_of_input_order() -> None:
    initial_agents = (agent(), agent(2, pos(1)), agent(3, pos(1, 1)))
    decisions = {
        aid(): Move(destination=pos(1)),
        aid(2): Move(destination=pos(0)),
        aid(3): Move(destination=pos(1)),
    }
    for seed in range(8):
        left = Simulation(world(*initial_agents, width=2, height=2), seed=seed)
        right = Simulation(
            world(*reversed(initial_agents), width=2, height=2), seed=seed
        )
        assert left.step(decisions) == right.step(
            dict(reversed(tuple(decisions.items())))
        )
        assert left.world == right.world


def test_uncontested_swap_does_not_consume_conflict_randomness() -> None:
    initial = world(
        agent(),
        agent(2, pos(1)),
        agent(3, pos(0, 1)),
        agent(4, pos(2, 1)),
        width=3,
        height=2,
    )
    left = Simulation(initial, seed=12)
    right = Simulation(initial, seed=12)
    left.step({aid(): Move(destination=pos(1)), aid(2): Move(destination=pos(0))})
    right.step()
    contest = {aid(3): Move(destination=pos(1, 1)), aid(4): Move(destination=pos(1, 1))}
    left.step(contest)
    right.step(contest)
    assert [a.position for a in left.world.agents[2:]] == [
        a.position for a in right.world.agents[2:]
    ]
