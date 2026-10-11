"""Validated rectangular grids with exclusive tile occupancy."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from emergence.domain.agent import Agent
from emergence.domain.capabilities import validate_known_capabilities
from emergence.domain.knowledge import Terrain
from emergence.domain.values import AgentId, DomainModel, Position, Resource


class ResourceSource(DomainModel, frozen=True):
    resource: Resource
    quantity: Annotated[int, Field(gt=0)]


class Tile(DomainModel, frozen=True):
    terrain: Terrain = Terrain.GRASS
    source: ResourceSource | None = None
    shelter: bool = False

    @property
    def walkable(self) -> bool:
        return self.terrain != Terrain.WATER and self.source is None

    @model_validator(mode="after")
    def validate_shelter(self) -> Self:
        if self.shelter and (self.terrain != Terrain.GRASS or self.source is not None):
            raise ValueError("Shelters require grass without a resource source")
        return self


class World(DomainModel, frozen=True):
    """Tiles are row-major; agents are normalized to ID order."""

    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    tiles: tuple[Tile, ...]
    agents: tuple[Agent, ...] = ()
    tick: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_world(self) -> Self:
        if len(self.tiles) != self.width * self.height:
            raise ValueError("Tile count must match the rectangular grid dimensions")

        ids: set[AgentId] = set()
        occupied: set[Position] = set()
        for agent in self.agents:
            if agent.id in ids:
                raise ValueError("Agent IDs must be unique")
            if agent.position in occupied:
                raise ValueError("Only one agent may occupy a tile")
            if (
                not self.contains(agent.position)
                or not self.tile_at(agent.position).walkable
            ):
                raise ValueError("Agents must occupy in-bounds, walkable tiles")
            validate_known_capabilities(agent.known_capabilities)
            ids.add(agent.id)
            occupied.add(agent.position)

        # Normalization is confined to initial model validation, before publication.
        object.__setattr__(
            self, "agents", tuple(sorted(self.agents, key=lambda a: a.id.value))
        )
        return self

    def contains(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def tile_at(self, position: Position) -> Tile:
        if not self.contains(position):
            raise ValueError("Position is outside the world")
        return self.tiles[position.y * self.width + position.x]

    def agent(self, agent_id: AgentId) -> Agent:
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(agent_id)

    def visible_positions(self, origin: Position, radius: int) -> frozenset[Position]:
        if radius < 0:
            raise ValueError("Visible radius must be nonnegative")
        return frozenset(
            Position(x=x, y=y)
            for y in range(
                max(0, origin.y - radius), min(self.height, origin.y + radius + 1)
            )
            for x in range(
                max(0, origin.x - radius), min(self.width, origin.x + radius + 1)
            )
        )
