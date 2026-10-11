"""Structurally valid proposed requests; world executability is deferred."""

from typing import Annotated, Literal

from pydantic import Field

from emergence.domain.values import DomainModel, Position, Resource


class Move(DomainModel, frozen=True):
    kind: Literal["move"] = "move"
    destination: Position


class Gather(DomainModel, frozen=True):
    kind: Literal["gather"] = "gather"
    resource: Resource
    position: Position


class Eat(DomainModel, frozen=True):
    kind: Literal["eat"] = "eat"


class Rest(DomainModel, frozen=True):
    kind: Literal["rest"] = "rest"


class BuildShelter(DomainModel, frozen=True):
    kind: Literal["build_shelter"] = "build_shelter"
    position: Position


type ActionRequest = Annotated[
    Move | Gather | Eat | Rest | BuildShelter, Field(discriminator="kind")
]
