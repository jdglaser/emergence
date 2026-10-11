"""Objective action requirements, separate from individual knowledge."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from emergence.domain.values import DomainModel, Inventory, NonblankText


class CapabilityId(StrEnum):
    MOVE = "move"
    GATHER = "gather"
    EAT = "eat"
    REST = "rest"
    BUILD_SHELTER = "build_shelter"


class Capability(DomainModel, frozen=True):
    id: CapabilityId
    description: NonblankText
    resource_cost: Inventory = Inventory()
    requires_suitable_site: bool = False


CAPABILITY_CATALOG: Mapping[CapabilityId, Capability] = MappingProxyType(
    {
        CapabilityId.MOVE: Capability(
            id=CapabilityId.MOVE, description="Travel to a destination."
        ),
        CapabilityId.GATHER: Capability(
            id=CapabilityId.GATHER, description="Gather a resource at a target."
        ),
        CapabilityId.EAT: Capability(
            id=CapabilityId.EAT,
            description="Eat food from inventory.",
            resource_cost=Inventory(food=1),
        ),
        CapabilityId.REST: Capability(id=CapabilityId.REST, description="Rest."),
        CapabilityId.BUILD_SHELTER: Capability(
            id=CapabilityId.BUILD_SHELTER,
            description="Construct a basic shelter at a target.",
            resource_cost=Inventory(wood=5),
            requires_suitable_site=True,
        ),
    }
)

INITIAL_CAPABILITIES = frozenset(CAPABILITY_CATALOG)


def validate_known_capabilities(
    known: frozenset[CapabilityId],
    catalog: Mapping[CapabilityId, Capability] = CAPABILITY_CATALOG,
) -> None:
    """Check references without conflating knowledge with affordability."""
    missing = known.difference(catalog)
    if missing:
        names = ", ".join(sorted(capability.value for capability in missing))
        raise ValueError(f"Unknown capabilities in catalog: {names}")
