"""One authoritative tick: submissions, movement, work, survival, publication."""

from collections import defaultdict
from collections.abc import Mapping
from random import Random

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
from emergence.domain.knowledge import ObservedTile
from emergence.domain.events import (
    ActionRejected,
    AgentAte,
    AgentDied,
    AgentMoved,
    AgentRested,
    DomainEvent,
    MovementWaiting,
    NeedsChanged,
    RejectionReason,
    ResourceDepleted,
    ResourceGathered,
    ShelterConstructed,
    TaskCompleted,
    TaskFailed,
    TaskStarted,
    TickAdvanced,
)
from emergence.domain.tasks import MovementProgress, Task, TaskPhase, TaskStatus
from emergence.domain.values import AgentId, Inventory, Needs, Position, Resource
from emergence.simulation.pathfinding import distance, find_path, neighbors
from emergence.simulation.rules import Rules
from emergence.world.models import ResourceSource, Terrain, Tile, World


def _replace_agent(agent: Agent, **changes: object) -> Agent:
    return Agent.model_validate({**agent.model_dump(), **changes})


def _replace_task(task: Task, **changes: object) -> Task:
    return Task.model_validate({**task.model_dump(), **changes})


def _need_change(needs: Needs, *, hunger: int = 0, energy: int = 0) -> Needs:
    return Needs(
        hunger=max(0, min(100, needs.hunger + hunger)),
        energy=max(0, min(100, needs.energy + energy)),
        health=needs.health,
    )


class Simulation:
    """Owns immutable snapshots and a private seeded contention RNG.

    Spatial tasks plan through persistent observations, never unseen world tiles.
    """

    def __init__(
        self, world: World, *, seed: int = 0, rules: Rules | None = None
    ) -> None:
        self._world = World.model_validate(world.model_dump())
        self._rules = Rules.model_validate((rules or Rules()).model_dump())
        self._random = Random(seed)
        self._world = self._refresh_world(self._world)

    @property
    def world(self) -> World:
        return self._world

    @property
    def rules(self) -> Rules:
        return self._rules

    def step(
        self, decisions: Mapping[AgentId, ActionRequest] | None = None
    ) -> tuple[DomainEvent, ...]:
        """Advance exactly one tick, including when no decisions are submitted."""
        initial = self._refresh_world(self._world)
        agents = {agent.id: agent for agent in initial.agents}
        tiles = list(initial.tiles)
        events: list[DomainEvent] = []
        submissions = dict(
            sorted((decisions or {}).items(), key=lambda item: item[0].value)
        )
        rejections = {
            agent_id: self._validate(initial, agents.get(agent_id), request)
            for agent_id, request in submissions.items()
        }

        # Evaluate occupied destinations together so following and cycles do not
        # depend on submission order. Stationary occupants still reject requests.
        moving = {agent.id for agent in initial.agents if self._eligible_mover(agent)}
        candidates = {
            agent_id
            for agent_id, request in submissions.items()
            if isinstance(request, Move) and rejections[agent_id] is None
        }
        occupants = {agent.position: agent.id for agent in initial.agents}
        while True:
            rejected = {
                agent_id
                for agent_id in candidates
                if isinstance(request := submissions[agent_id], Move)
                and (occupant := occupants.get(request.destination)) is not None
                and occupant not in moving | candidates
            }
            if not rejected:
                break
            for agent_id in rejected:
                rejections[agent_id] = RejectionReason.OCCUPIED
            candidates -= rejected

        for agent_id, request in submissions.items():
            reason = rejections[agent_id]
            if reason is not None:
                events.append(
                    ActionRejected(agent_id=agent_id, request=request, reason=reason)
                )
                continue

            agent = agents[agent_id]
            progress = None
            if isinstance(request, (Move, Gather, BuildShelter)):
                destination, route = self._plan(agent, request)
                # The validator established a terrain route. Occupants may delay it.
                assert destination is not None and route is not None
                progress = MovementProgress(destination=destination, route=route)
            phase = (
                TaskPhase.TRAVELING
                if progress and progress.route
                else TaskPhase.WORKING
            )
            task = Task(request=request, movement=progress, phase=phase)
            agents[agent_id] = _replace_agent(agent, active_task=task)
            events.append(TaskStarted(agent_id=agent_id, request=request))

        self._move(initial, agents, events)
        self._work(initial, agents, tiles, events)
        self._survival(initial, agents, events)

        self._world = self._refresh_world(
            World(
                width=initial.width,
                height=initial.height,
                tiles=tuple(tiles),
                agents=tuple(agents.values()),
                tick=initial.tick + 1,
            )
        )
        events.append(TickAdvanced(tick=self._world.tick))
        return tuple(events)

    def _energy_cost(self, request: ActionRequest) -> int:
        match request:
            case Move():
                return self.rules.movement_energy
            case Gather():
                return self.rules.gather_energy
            case BuildShelter():
                return self.rules.build_energy
            case _:
                return 0

    def _validate(
        self, world: World, agent: Agent | None, request: ActionRequest
    ) -> RejectionReason | None:
        if agent is None:
            return RejectionReason.UNKNOWN_AGENT
        if agent.needs.health == 0:
            return RejectionReason.DEAD
        if agent.active_task is not None and agent.active_task.status in (
            TaskStatus.ACTIVE,
            TaskStatus.SUSPENDED,
        ):
            return RejectionReason.AGENT_BUSY

        capability_id = CapabilityId(request.kind)
        if capability_id not in agent.known_capabilities:
            return RejectionReason.UNKNOWN_CAPABILITY
        cost = CAPABILITY_CATALOG[capability_id].resource_cost
        if agent.inventory.food < cost.food or agent.inventory.wood < cost.wood:
            return RejectionReason.INSUFFICIENT_RESOURCES
        if agent.needs.energy < self._energy_cost(request):
            return RejectionReason.INSUFFICIENT_ENERGY

        match request:
            case Move(destination=destination):
                observed = {tile.position: tile for tile in agent.knowledge}
                if destination not in observed:
                    return RejectionReason.OUT_OF_RANGE
                if destination == agent.position or not observed[destination].walkable:
                    return RejectionReason.INVALID_TARGET
                known = self._walkable(agent)
                if find_path(agent.position, destination, known) is None:
                    return RejectionReason.NO_ROUTE
            case Gather(position=position, resource=resource):
                observed = {tile.position: tile for tile in agent.knowledge}
                if position not in observed:
                    return RejectionReason.OUT_OF_RANGE
                if observed[position].resource != resource:
                    return RejectionReason.RESOURCE_UNAVAILABLE
            case BuildShelter(position=position):
                observed = {tile.position: tile for tile in agent.knowledge}
                if position not in observed:
                    return RejectionReason.OUT_OF_RANGE
                tile = observed[position]
                if (
                    tile.terrain != Terrain.GRASS
                    or tile.resource is not None
                    or tile.shelter
                ):
                    return RejectionReason.SITE_UNAVAILABLE
            case _:
                pass
        if isinstance(request, (Gather, BuildShelter)):
            destination, route = self._plan(agent, request)
            if destination is None or route is None:
                return RejectionReason.NO_ROUTE
            if route:
                if CapabilityId.MOVE not in agent.known_capabilities:
                    return RejectionReason.UNKNOWN_CAPABILITY
                if agent.needs.energy < self.rules.movement_energy:
                    return RejectionReason.INSUFFICIENT_ENERGY
        return None

    def _refresh_world(self, world: World) -> World:
        refreshed: list[Agent] = []
        for agent in world.agents:
            observed = {tile.position: tile for tile in agent.knowledge}
            for position in world.visible_positions(
                agent.position, self.rules.visible_radius
            ):
                tile = world.tile_at(position)
                observed[position] = ObservedTile(
                    position=position,
                    terrain=tile.terrain,
                    resource=tile.source.resource if tile.source else None,
                    shelter=tile.shelter,
                )
            refreshed.append(_replace_agent(agent, knowledge=tuple(observed.values())))
        return World.model_validate({**world.model_dump(), "agents": tuple(refreshed)})

    def _walkable(self, agent: Agent) -> frozenset[Position]:
        return frozenset(tile.position for tile in agent.knowledge if tile.walkable)

    def _plan(
        self,
        agent: Agent,
        request: ActionRequest,
        blocked: frozenset[Position] = frozenset(),
    ) -> tuple[Position | None, tuple[Position, ...] | None]:
        match request:
            case Move(destination=destination) | BuildShelter(position=destination):
                return destination, find_path(
                    agent.position, destination, self._walkable(agent), blocked
                )
            case Gather(position=position):
                choices = [
                    (destination, route)
                    for destination in neighbors(position)
                    if (
                        route := find_path(
                            agent.position, destination, self._walkable(agent), blocked
                        )
                    )
                    is not None
                ]
                if choices:
                    return min(
                        choices,
                        key=lambda choice: (len(choice[1]), choice[0].y, choice[0].x),
                    )
                return None, None
            case _:
                return None, None

    def _select(self, contenders: list[AgentId], capacity: int = 1) -> set[AgentId]:
        ordered = sorted(contenders, key=lambda agent_id: agent_id.value)
        if len(ordered) <= capacity:
            return set(ordered)
        return set(self._random.sample(ordered, capacity))

    def _finish(
        self, agent: Agent, events: list[DomainEvent], *, failure: str | None = None
    ) -> Agent:
        task = agent.active_task
        assert task is not None
        status = TaskStatus.COMPLETED if failure is None else TaskStatus.FAILED
        if failure is None:
            events.append(TaskCompleted(agent_id=agent.id, request=task.request))
        else:
            events.append(
                TaskFailed(agent_id=agent.id, request=task.request, reason=failure)
            )
        return _replace_agent(agent, active_task=_replace_task(task, status=status))

    def _eligible_mover(self, agent: Agent) -> bool:
        task = agent.active_task
        return (
            agent.needs.health > 0
            and agent.needs.energy >= self.rules.movement_energy
            and task is not None
            and task.status == TaskStatus.ACTIVE
            and task.phase == TaskPhase.TRAVELING
            and task.movement is not None
            and agent.position != task.movement.destination
        )

    def _move(
        self, world: World, agents: dict[AgentId, Agent], events: list[DomainEvent]
    ) -> None:
        occupants = {agent.position: agent.id for agent in world.agents}
        moving = {
            agent_id
            for agent_id, agent in agents.items()
            if self._eligible_mover(agent)
        }
        stationary = {
            position
            for position, agent_id in occupants.items()
            if agent_id not in moving
        }
        claims: dict[Position, list[AgentId]] = defaultdict(list)
        waiting: set[AgentId] = set()

        for agent_id, agent in agents.items():
            task = agent.active_task
            if (
                agent.needs.health == 0
                or task is None
                or task.status != TaskStatus.ACTIVE
                or task.phase != TaskPhase.TRAVELING
            ):
                continue
            if task.movement is None:
                agents[agent_id] = self._finish(
                    agent, events, failure="missing_movement_progress"
                )
                continue
            if isinstance(task.request, (Gather, BuildShelter)):
                observed = {tile.position: tile for tile in agent.knowledge}
                target = observed.get(task.request.position)
                failure = None
                if isinstance(task.request, Gather) and (target is None or target.resource != task.request.resource):
                    failure = "resource_depleted"
                if isinstance(task.request, BuildShelter) and (target is None or target.terrain != Terrain.GRASS or target.resource is not None or target.shelter):
                    failure = "site_unavailable"
                if failure:
                    agents[agent_id] = self._finish(agent, events, failure=failure)
                    continue
            if agent.position == task.movement.destination:
                agents[agent_id] = self._arrive(agent, events)
                continue
            if agent.needs.energy < self.rules.movement_energy:
                agents[agent_id] = self._finish(
                    agent, events, failure="insufficient_energy"
                )
                continue

            known = self._walkable(agent)
            visible = world.visible_positions(agent.position, self.rules.visible_radius)
            blocked = frozenset((stationary & visible) - {agent.position})
            route = task.movement.route
            if (
                not route
                or route[0] in blocked
                or route[0] not in known
                or distance(agent.position, route[0]) != 1
                or route[-1] != task.movement.destination
                or isinstance(task.request, Gather)
            ):
                destination, planned = self._plan(agent, task.request, blocked)
                route = planned or ()
            else:
                destination = task.movement.destination

            progress = MovementProgress(
                route=route, destination=destination or task.movement.destination
            )
            agents[agent_id] = _replace_agent(
                agent, active_task=_replace_task(task, movement=progress)
            )
            if not route:
                if destination == agent.position:
                    agents[agent_id] = self._arrive(agents[agent_id], events)
                else:
                    waiting.add(agent_id)
            else:
                claims[route[0]].append(agent_id)

        winners: set[AgentId] = set()
        for position in sorted(claims, key=lambda p: (p.y, p.x)):
            winners.update(self._select(claims[position]))

        # A move into an occupied tile depends on its occupant also moving.
        # Repeated pruning propagates a blocked tail through any following chain;
        # closed cycles survive. Lottery losers are never promoted or rerolled.
        destinations = {
            agent_id: position for position, ids in claims.items() for agent_id in ids
        }
        while True:
            blocked_winners = {
                agent_id
                for agent_id in winners
                if (occupant := occupants.get(destinations[agent_id])) is not None
                and occupant not in winners
            }
            if not blocked_winners:
                break
            winners -= blocked_winners

        moved_agents: dict[AgentId, Agent] = {}
        for agent_id in sorted(destinations.keys() | waiting, key=lambda a: a.value):
            agent = agents[agent_id]
            task = agent.active_task
            assert task is not None and task.movement is not None
            if agent_id not in winners:
                events.append(
                    MovementWaiting(
                        agent_id=agent_id, destination=task.movement.destination
                    )
                )
                continue

            destination = task.movement.route[0]
            # Replanning uses knowledge; final execution checks authoritative state.
            assert world.tile_at(destination).walkable
            assert (
                occupants.get(destination) is None or occupants[destination] in winners
            )
            progress = MovementProgress(
                route=task.movement.route[1:],
                destination=task.movement.destination,
            )
            moved = _replace_agent(
                agent,
                position=destination,
                needs=_need_change(agent.needs, energy=-self.rules.movement_energy),
                active_task=_replace_task(task, movement=progress),
            )
            events.append(
                AgentMoved(
                    agent_id=agent_id, origin=agent.position, destination=destination
                )
            )
            if destination == task.movement.destination:
                moved = self._arrive(moved, events)
            moved_agents[agent_id] = moved

        agents.update(moved_agents)

    def _arrive(self, agent: Agent, events: list[DomainEvent]) -> Agent:
        task = agent.active_task
        assert task is not None
        if isinstance(task.request, Move):
            return self._finish(agent, events)
        return _replace_agent(
            agent, active_task=_replace_task(task, phase=TaskPhase.WORKING)
        )

    def _work(
        self,
        world: World,
        agents: dict[AgentId, Agent],
        tiles: list[Tile],
        events: list[DomainEvent],
    ) -> None:
        accepted: dict[AgentId, ActionRequest] = {}
        for agent_id, agent in agents.items():
            task = agent.active_task
            if (
                task is None
                or task.status != TaskStatus.ACTIVE
                or task.phase != TaskPhase.WORKING
            ):
                continue
            request = task.request
            failure = self._work_failure(world, agent, request)
            if failure:
                agents[agent_id] = self._finish(agent, events, failure=failure)
            else:
                accepted[agent_id] = request
        gathers: dict[Position, list[AgentId]] = defaultdict(list)
        for agent_id, request in accepted.items():
            if isinstance(request, Gather):
                gathers[request.position].append(agent_id)

        gather_winners: set[AgentId] = set()
        for position in sorted(gathers, key=lambda p: (p.y, p.x)):
            source = world.tile_at(position).source
            assert source is not None
            gather_winners.update(self._select(gathers[position], source.quantity))

        for agent_id, request in accepted.items():
            if isinstance(request, Move):
                continue
            agent = agents[agent_id]
            if isinstance(request, Gather) and agent_id not in gather_winners:
                agents[agent_id] = self._finish(
                    agent, events, failure="resource_depleted"
                )
                continue

            cost = CAPABILITY_CATALOG[CapabilityId(request.kind)].resource_cost
            inventory = Inventory(
                food=agent.inventory.food - cost.food,
                wood=agent.inventory.wood - cost.wood,
            )
            needs = _need_change(agent.needs, energy=-self._energy_cost(request))

            match request:
                case Gather(position=position, resource=resource):
                    index = position.y * world.width + position.x
                    tile = tiles[index]
                    source = tile.source
                    assert source is not None and source.quantity > 0
                    remaining = source.quantity - 1
                    tiles[index] = Tile(
                        terrain=tile.terrain,
                        source=ResourceSource(resource=resource, quantity=remaining)
                        if remaining
                        else None,
                    )
                    inventory = Inventory(
                        food=inventory.food + (resource == Resource.FOOD),
                        wood=inventory.wood + (resource == Resource.WOOD),
                    )
                    events.append(
                        ResourceGathered(
                            agent_id=agent_id,
                            resource=resource,
                            position=position,
                            quantity=1,
                        )
                    )
                    if not remaining:
                        events.append(
                            ResourceDepleted(position=position, resource=resource)
                        )
                case Eat():
                    needs = _need_change(needs, hunger=self.rules.eat_hunger)
                    events.append(AgentAte(agent_id=agent_id))
                case Rest():
                    sheltered = world.tile_at(agent.position).shelter
                    bonus = self.rules.shelter_rest_bonus if sheltered else 0
                    needs = _need_change(needs, energy=self.rules.rest_energy + bonus)
                    events.append(AgentRested(agent_id=agent_id, sheltered=sheltered))
                case BuildShelter(position=position):
                    tiles[position.y * world.width + position.x] = Tile(
                        terrain=Terrain.GRASS, shelter=True
                    )
                    events.append(
                        ShelterConstructed(agent_id=agent_id, position=position)
                    )
                case _:
                    raise AssertionError("Unexpected non-movement request")

            updated = _replace_agent(agent, inventory=inventory, needs=needs)
            agents[agent_id] = self._finish(updated, events)

    def _work_failure(
        self, world: World, agent: Agent, request: ActionRequest
    ) -> str | None:
        if agent.needs.health == 0:
            return "agent_died"
        cost = CAPABILITY_CATALOG[CapabilityId(request.kind)].resource_cost
        if agent.inventory.food < cost.food or agent.inventory.wood < cost.wood:
            return "insufficient_resources"
        if agent.needs.energy < self._energy_cost(request):
            return "insufficient_energy"
        match request:
            case Gather(position=position, resource=resource):
                source = world.tile_at(position).source
                if source is None or source.resource != resource:
                    return "resource_depleted"
                if distance(agent.position, position) != 1:
                    return "invalid_target"
            case BuildShelter(position=position):
                tile = world.tile_at(position)
                if (
                    tile.terrain != Terrain.GRASS
                    or tile.source is not None
                    or tile.shelter
                ):
                    return "site_unavailable"
                if agent.position != position:
                    return "invalid_target"
            case _:
                pass
        return None

    def _survival(
        self, world: World, agents: dict[AgentId, Agent], events: list[DomainEvent]
    ) -> None:
        for original in world.agents:
            if original.needs.health == 0:
                continue
            agent = agents[original.id]
            decayed = _need_change(
                agent.needs,
                hunger=-self.rules.hunger_loss,
                energy=-self.rules.energy_loss,
            )
            damage = (self.rules.starvation_damage if decayed.hunger == 0 else 0) + (
                self.rules.exhaustion_damage if decayed.energy == 0 else 0
            )
            needs = Needs(
                hunger=decayed.hunger,
                energy=decayed.energy,
                health=max(0, decayed.health - damage),
            )
            updated = _replace_agent(agent, needs=needs)
            if needs != original.needs:
                events.append(
                    NeedsChanged(agent_id=agent.id, before=original.needs, after=needs)
                )
            if needs.health == 0:
                task = updated.active_task
                if task is not None and task.status in (
                    TaskStatus.ACTIVE,
                    TaskStatus.SUSPENDED,
                ):
                    updated = self._finish(updated, events, failure="agent_died")
                events.append(AgentDied(agent_id=agent.id))
            agents[agent.id] = updated
