"""Domain invariants and the distinction between knowledge, requests and tasks."""

from collections.abc import Mapping

import pytest
from pydantic import TypeAdapter, ValidationError

from emergence.domain.actions import (
    ActionRequest,
    BuildShelter,
    Eat,
    Gather,
    Move,
    Rest,
)
from emergence.domain.agent import Agent
from emergence.domain.capabilities import (
    CAPABILITY_CATALOG,
    INITIAL_CAPABILITIES,
    Capability,
    CapabilityId,
    validate_known_capabilities,
)
from emergence.domain.events import (
    AgentMoved,
    DomainEvent,
    ResourceGathered,
    ShelterConstructed,
    TaskCompleted,
    TaskFailed,
)
from emergence.domain.tasks import Task, TaskStatus
from emergence.domain.values import (
    AgentId,
    Inventory,
    Needs,
    Personality,
    Position,
    Resource,
)


def make_agent() -> Agent:
    return Agent(
        id=AgentId(value=1),
        name="Ada",
        position=Position(x=0, y=0),
        personality=Personality(
            sociability=50,
            cooperativeness=60,
            cautiousness=70,
            curiosity=80,
            assertiveness=40,
        ),
        needs=Needs(hunger=100, energy=100, health=100),
    )


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, "1"])
def test_ids_require_positive_integers(invalid: object) -> None:
    with pytest.raises(ValidationError):
        AgentId.model_validate({"value": invalid})


@pytest.mark.parametrize("invalid", [True, 1.5, "1"])
def test_coordinates_reject_coercion(invalid: object) -> None:
    with pytest.raises(ValidationError):
        Position.model_validate({"x": invalid, "y": 0})


def test_value_equality_hashing_and_negative_coordinates() -> None:
    assert Position(x=-2, y=3) == Position(x=-2, y=3)
    assert len({AgentId(value=1), AgentId(value=1), AgentId(value=2)}) == 2


@pytest.mark.parametrize("field", ["hunger", "energy", "health"])
@pytest.mark.parametrize("invalid", [-1, 101, True, 1.5, "50"])
def test_needs_validate_every_field(field: str, invalid: object) -> None:
    data: dict[str, object] = {"hunger": 50, "energy": 50, "health": 50}
    data[field] = invalid
    with pytest.raises(ValidationError):
        Needs.model_validate(data)


def test_needs_positive_scale_endpoints() -> None:
    depleted = Needs(hunger=0, energy=0, health=0)
    healthy = Needs(hunger=100, energy=100, health=100)
    assert depleted.hunger == depleted.energy == depleted.health == 0
    assert healthy.hunger == healthy.energy == healthy.health == 100


@pytest.mark.parametrize(
    "field",
    ["sociability", "cooperativeness", "cautiousness", "curiosity", "assertiveness"],
)
@pytest.mark.parametrize("invalid", [-1, 101, True, 1.5, "50"])
def test_personality_bounds(field: str, invalid: object) -> None:
    data = make_agent().personality.model_dump()
    data[field] = invalid
    with pytest.raises(ValidationError):
        Personality.model_validate(data)


@pytest.mark.parametrize("field", ["food", "wood"])
@pytest.mark.parametrize("invalid", [-1, True, 1.5, "1"])
def test_inventory_nonnegative_integers(field: str, invalid: object) -> None:
    with pytest.raises(ValidationError):
        Inventory.model_validate({field: invalid})


def test_agent_constructs_with_all_known_capabilities_when_unaffordable() -> None:
    agent = make_agent()
    assert agent.intention is None and agent.active_task is None
    assert agent.inventory == Inventory()
    assert agent.known_capabilities == INITIAL_CAPABILITIES
    validate_known_capabilities(agent.known_capabilities)
    assert CapabilityId.BUILD_SHELTER in agent.known_capabilities


@pytest.mark.parametrize("field", ["name", "intention"])
def test_agent_rejects_blank_text(field: str) -> None:
    data = make_agent().model_dump()
    data[field] = "  \n "
    with pytest.raises(ValidationError):
        Agent.model_validate(data)


def test_validated_reconstruction_preserves_and_revises_intention() -> None:
    original = make_agent()
    planning = Agent.model_validate(
        {**original.model_dump(), "intention": " Build a shelter. "}
    )
    working = Agent.model_validate(
        {**planning.model_dump(), "active_task": Task(request=Rest())}
    )
    revised = Agent.model_validate(
        {**working.model_dump(), "intention": "Find food first."}
    )
    assert original.intention is None
    assert working.intention == "Build a shelter."
    assert revised.intention == "Find food first."
    assert revised.active_task == working.active_task

    with pytest.raises(ValidationError):
        Agent.model_validate({**revised.model_dump(), "intention": ""})
    with pytest.raises(ValidationError):
        revised.__setattr__("intention", "Other")


def test_catalog_is_shared_typed_and_read_only() -> None:
    assert set(CAPABILITY_CATALOG) == set(CapabilityId)
    assert all(key == value.id for key, value in CAPABILITY_CATALOG.items())
    assert CAPABILITY_CATALOG[CapabilityId.EAT].resource_cost == Inventory(food=1)
    build = CAPABILITY_CATALOG[CapabilityId.BUILD_SHELTER]
    assert build.resource_cost == Inventory(wood=5)
    assert build.requires_suitable_site
    assert not CAPABILITY_CATALOG[CapabilityId.MOVE].requires_suitable_site
    with pytest.raises(ValidationError):
        build.__setattr__("description", "Changed")


def test_knowledge_catalog_validation_and_individual_subset() -> None:
    known = frozenset({CapabilityId.MOVE})
    catalog: Mapping[CapabilityId, Capability] = {}
    with pytest.raises(ValueError, match="move"):
        validate_known_capabilities(known, catalog)
    agent = Agent.model_validate(
        {**make_agent().model_dump(), "known_capabilities": known}
    )
    assert agent.known_capabilities == known
    with pytest.raises(ValidationError):
        Agent.model_validate_json(
            make_agent().model_dump_json().replace('"move"', '"invented"')
        )


@pytest.mark.parametrize(
    "action",
    [
        Move(destination=Position(x=8, y=4)),
        Gather(resource=Resource.WOOD, position=Position(x=8, y=4)),
        Eat(),
        Rest(),
        BuildShelter(position=Position(x=2, y=1)),
    ],
)
def test_typed_requests_roundtrip_without_world_validation(
    action: ActionRequest,
) -> None:
    adapter = TypeAdapter[ActionRequest](ActionRequest)
    assert adapter.validate_json(adapter.dump_json(action)) == action
    task = Task(request=action)
    assert task.request == action and task.status == TaskStatus.ACTIVE


@pytest.mark.parametrize(
    "payload",
    [
        '{"kind":"move"}',
        '{"kind":"gather","position":{"x":0,"y":0}}',
        '{"kind":"gather","resource":"stone","position":{"x":0,"y":0}}',
        '{"kind":"build_shelter"}',
        '{"kind":"rest","destination":{"x":0,"y":0}}',
        '{"kind":"speak"}',
    ],
)
def test_requests_require_targets_and_valid_tags(payload: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter[ActionRequest](ActionRequest).validate_json(payload)


@pytest.mark.parametrize("status", list(TaskStatus))
def test_task_lifecycle_is_representation_only(status: TaskStatus) -> None:
    task = Task(request=Rest(), status=status)
    assert Task.model_validate_json(task.model_dump_json()) == task


def test_invalid_status_and_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Task.model_validate_json('{"request":{"kind":"rest"},"status":"queued"}')
    with pytest.raises(ValidationError):
        Needs.model_validate({"hunger": 1, "energy": 2, "health": 3, "mana": 4})


def test_events_are_typed_facts_and_roundtrip() -> None:
    agent_id = AgentId(value=1)
    position = Position(x=2, y=3)
    events: list[DomainEvent] = [
        AgentMoved(agent_id=agent_id, origin=Position(x=0, y=0), destination=position),
        ResourceGathered(
            agent_id=agent_id, resource=Resource.FOOD, position=position, quantity=2
        ),
        TaskCompleted(agent_id=agent_id, request=Eat()),
        TaskFailed(agent_id=agent_id, request=Rest(), reason="Target unavailable"),
        ShelterConstructed(agent_id=agent_id, position=position),
    ]
    adapter = TypeAdapter[DomainEvent](DomainEvent)
    assert len({event.kind for event in events}) == 5
    for event in events:
        assert adapter.validate_json(adapter.dump_json(event)) == event
    with pytest.raises(ValidationError):
        ResourceGathered(
            agent_id=agent_id, resource=Resource.FOOD, position=position, quantity=0
        )
    with pytest.raises(ValidationError):
        TaskFailed(agent_id=agent_id, request=Rest(), reason=" ")


def test_domain_generates_schema_and_nested_json_roundtrip() -> None:
    schema = TypeAdapter[ActionRequest](ActionRequest).json_schema()
    assert schema["discriminator"]["propertyName"] == "kind"
    assert len(schema["oneOf"]) == 5
    agent = make_agent()
    assert Agent.model_validate_json(agent.model_dump_json()) == agent
    assert Agent.model_json_schema()["additionalProperties"] is False
