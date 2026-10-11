"""Persistent observations, deliberately excluding transient agent occupancy."""

from enum import StrEnum

from emergence.domain.values import DomainModel, Position, Resource


class Terrain(StrEnum):
    GRASS = "grass"
    FOREST = "forest"
    WATER = "water"


class ObservedTile(DomainModel, frozen=True):
    position: Position
    terrain: Terrain
    resource: Resource | None = None
    shelter: bool = False

    @property
    def walkable(self) -> bool:
        return self.terrain != Terrain.WATER and self.resource is None
