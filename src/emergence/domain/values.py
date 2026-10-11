"""Immutable values and shared validation conventions."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type Percentage = Annotated[int, Field(ge=0, le=100)]
type Quantity = Annotated[int, Field(ge=0)]
type NonblankText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class DomainModel(BaseModel, frozen=True):
    """Strict, frozen records; rebuild through model_validate for validated updates.

    Pydantic's model_copy(update=...) bypasses validation and is not an update API
    for untrusted data.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", validate_default=True
    )


class AgentId(DomainModel, frozen=True):
    """Caller-supplied ID; the world validates uniqueness across its agents."""

    value: Annotated[int, Field(gt=0)]


class Position(DomainModel, frozen=True):
    """Grid coordinate; bounds and reachability belong to the world."""

    x: int
    y: int


class Resource(StrEnum):
    FOOD = "food"
    WOOD = "wood"


class Personality(DomainModel, frozen=True):
    sociability: Percentage
    cooperativeness: Percentage
    cautiousness: Percentage
    curiosity: Percentage
    assertiveness: Percentage


class Needs(DomainModel, frozen=True):
    """All scales improve upward: hunger 0 starving/100 full,
    energy 0 exhausted/100 rested, health 0 depleted/100 healthy.
    """

    hunger: Percentage
    energy: Percentage
    health: Percentage


class Inventory(DomainModel, frozen=True):
    food: Quantity = 0
    wood: Quantity = 0
