"""Explicit default effects; inventory requirements come from the catalog."""

from typing import Annotated

from pydantic import Field

from emergence.domain.values import DomainModel, Quantity


class Rules(DomainModel, frozen=True):
    visible_radius: Annotated[int, Field(ge=1)] = 3
    movement_energy: Quantity = 1
    gather_energy: Quantity = 2
    build_energy: Quantity = 5
    eat_hunger: Quantity = 25
    rest_energy: Quantity = 10
    shelter_rest_bonus: Quantity = 5
    hunger_loss: Quantity = 1
    energy_loss: Quantity = 1
    starvation_damage: Quantity = 2
    exhaustion_damage: Quantity = 1
