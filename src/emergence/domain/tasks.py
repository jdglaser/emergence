"""Accepted requests, lifecycle status, and persistent movement progress."""

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from emergence.domain.actions import ActionRequest, BuildShelter, Gather, Move
from emergence.domain.values import DomainModel, Position


class TaskStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPhase(StrEnum):
    TRAVELING = "traveling"
    WORKING = "working"


class MovementProgress(DomainModel, frozen=True):
    """Current destination and route; knowledge belongs to the agent."""

    destination: Position
    route: tuple[Position, ...] = ()


class Task(DomainModel, frozen=True):
    request: ActionRequest
    status: TaskStatus = TaskStatus.ACTIVE
    phase: TaskPhase = TaskPhase.WORKING
    movement: MovementProgress | None = None

    @model_validator(mode="after")
    def validate_movement(self) -> Self:
        if isinstance(self.request, Move):
            object.__setattr__(self, "phase", TaskPhase.TRAVELING)
        if self.movement is not None and not isinstance(
            self.request, (Move, Gather, BuildShelter)
        ):
            raise ValueError("Only spatial tasks may hold movement progress")
        return self
