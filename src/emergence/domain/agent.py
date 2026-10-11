"""An individual agent's descriptive state."""

from emergence.domain.capabilities import INITIAL_CAPABILITIES, CapabilityId
from typing import Self

from pydantic import model_validator

from emergence.domain.knowledge import ObservedTile
from emergence.domain.tasks import Task
from emergence.domain.values import (
    AgentId,
    DomainModel,
    Inventory,
    Needs,
    NonblankText,
    Personality,
    Position,
)


class Agent(DomainModel, frozen=True):
    id: AgentId
    name: NonblankText
    position: Position
    personality: Personality
    needs: Needs
    inventory: Inventory = Inventory()
    known_capabilities: frozenset[CapabilityId] = INITIAL_CAPABILITIES
    intention: NonblankText | None = None
    active_task: Task | None = None
    knowledge: tuple[ObservedTile, ...] = ()

    @model_validator(mode="after")
    def normalize_knowledge(self) -> Self:
        positions = [tile.position for tile in self.knowledge]
        if len(set(positions)) != len(positions):
            raise ValueError("Observed positions must be unique")
        object.__setattr__(
            self,
            "knowledge",
            tuple(
                sorted(
                    self.knowledge, key=lambda tile: (tile.position.y, tile.position.x)
                )
            ),
        )
        return self
