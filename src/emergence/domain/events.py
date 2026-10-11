"""Facts about completed changes, distinct from proposed action requests."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from emergence.domain.actions import ActionRequest
from emergence.domain.values import (
    AgentId,
    DomainModel,
    Needs,
    NonblankText,
    Position,
    Resource,
)


class AgentMoved(DomainModel, frozen=True):
    kind: Literal["agent_moved"] = "agent_moved"
    agent_id: AgentId
    origin: Position
    destination: Position


class ResourceGathered(DomainModel, frozen=True):
    kind: Literal["resource_gathered"] = "resource_gathered"
    agent_id: AgentId
    resource: Resource
    position: Position
    quantity: Annotated[int, Field(gt=0)]


class TaskCompleted(DomainModel, frozen=True):
    kind: Literal["task_completed"] = "task_completed"
    agent_id: AgentId
    request: ActionRequest


class TaskFailed(DomainModel, frozen=True):
    kind: Literal["task_failed"] = "task_failed"
    agent_id: AgentId
    request: ActionRequest
    reason: NonblankText


class ShelterConstructed(DomainModel, frozen=True):
    kind: Literal["shelter_constructed"] = "shelter_constructed"
    agent_id: AgentId
    position: Position


class RejectionReason(StrEnum):
    UNKNOWN_AGENT = "unknown_agent"
    DEAD = "dead"
    AGENT_BUSY = "agent_busy"
    UNKNOWN_CAPABILITY = "unknown_capability"
    INSUFFICIENT_RESOURCES = "insufficient_resources"
    INSUFFICIENT_ENERGY = "insufficient_energy"
    INVALID_TARGET = "invalid_target"
    OUT_OF_RANGE = "out_of_range"
    OCCUPIED = "occupied"
    NO_ROUTE = "no_route"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    SITE_UNAVAILABLE = "site_unavailable"


class ActionRejected(DomainModel, frozen=True):
    kind: Literal["action_rejected"] = "action_rejected"
    agent_id: AgentId
    request: ActionRequest
    reason: RejectionReason


class TaskStarted(DomainModel, frozen=True):
    kind: Literal["task_started"] = "task_started"
    agent_id: AgentId
    request: ActionRequest


class MovementWaiting(DomainModel, frozen=True):
    kind: Literal["movement_waiting"] = "movement_waiting"
    agent_id: AgentId
    destination: Position


class AgentAte(DomainModel, frozen=True):
    kind: Literal["agent_ate"] = "agent_ate"
    agent_id: AgentId


class AgentRested(DomainModel, frozen=True):
    kind: Literal["agent_rested"] = "agent_rested"
    agent_id: AgentId
    sheltered: bool


class NeedsChanged(DomainModel, frozen=True):
    kind: Literal["needs_changed"] = "needs_changed"
    agent_id: AgentId
    before: Needs
    after: Needs


class ResourceDepleted(DomainModel, frozen=True):
    kind: Literal["resource_depleted"] = "resource_depleted"
    position: Position
    resource: Resource


class AgentDied(DomainModel, frozen=True):
    kind: Literal["agent_died"] = "agent_died"
    agent_id: AgentId


class TickAdvanced(DomainModel, frozen=True):
    kind: Literal["tick_advanced"] = "tick_advanced"
    tick: Annotated[int, Field(ge=1)]


type DomainEvent = Annotated[
    AgentMoved
    | ResourceGathered
    | TaskCompleted
    | TaskFailed
    | ShelterConstructed
    | ActionRejected
    | TaskStarted
    | MovementWaiting
    | AgentAte
    | AgentRested
    | NeedsChanged
    | ResourceDepleted
    | AgentDied
    | TickAdvanced,
    Field(discriminator="kind"),
]
