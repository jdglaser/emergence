"""World shape, occupancy, and immutable snapshot invariants."""

import pytest
from pydantic import ValidationError

from emergence.domain.agent import Agent
from emergence.domain.values import AgentId, Needs, Personality, Position, Resource
from emergence.world import ResourceSource, Terrain, Tile, World


def agent(identifier: int, x: int = 0, y: int = 0) -> Agent:
    return Agent(
        id=AgentId(value=identifier),
        name="Agent",
        position=Position(x=x, y=y),
        personality=Personality(
            sociability=50,
            cooperativeness=50,
            cautiousness=50,
            curiosity=50,
            assertiveness=50,
        ),
        needs=Needs(hunger=100, energy=100, health=100),
    )


@pytest.mark.parametrize(
    "width,height,tiles", [(0, 1, ()), (1, -1, ()), (2, 2, (Tile(),))]
)
def test_grid_dimensions_and_tile_count(
    width: int, height: int, tiles: tuple[Tile, ...]
) -> None:
    with pytest.raises(ValidationError):
        World(width=width, height=height, tiles=tiles)


@pytest.mark.parametrize(
    "agents",
    [(agent(1), agent(1, 1)), (agent(1), agent(2)), (agent(1, -1),), (agent(1, 2),)],
)
def test_unique_ids_exclusive_occupancy_and_bounds(agents: tuple[Agent, ...]) -> None:
    with pytest.raises(ValidationError):
        World(width=2, height=1, tiles=(Tile(), Tile()), agents=agents)


@pytest.mark.parametrize(
    "tile",
    [
        Tile(terrain=Terrain.WATER),
        Tile(source=ResourceSource(resource=Resource.WOOD, quantity=1)),
    ],
)
def test_agents_cannot_occupy_blocked_tiles(tile: Tile) -> None:
    with pytest.raises(ValidationError):
        World(width=1, height=1, tiles=(tile,), agents=(agent(1),))


@pytest.mark.parametrize("quantity", [0, -1, True, "1"])
def test_sources_are_nonempty_strict_quantities(quantity: object) -> None:
    with pytest.raises(ValidationError):
        ResourceSource.model_validate({"resource": Resource.FOOD, "quantity": quantity})


@pytest.mark.parametrize(
    "terrain,resource",
    [
        (Terrain.FOREST, None),
        (Terrain.WATER, None),
        (Terrain.GRASS, ResourceSource(resource=Resource.WOOD, quantity=1)),
    ],
)
def test_shelters_require_resource_free_grass(
    terrain: Terrain, resource: ResourceSource | None
) -> None:
    with pytest.raises(ValidationError):
        Tile(terrain=terrain, source=resource, shelter=True)


def test_sorted_agent_snapshots_tile_access_and_serialization() -> None:
    snapshot = World(
        width=2,
        height=1,
        tiles=(Tile(), Tile(shelter=True)),
        agents=(agent(2, 1), agent(1)),
    )
    assert [a.id.value for a in snapshot.agents] == [1, 2]
    assert snapshot.agent(AgentId(value=2)).position == Position(x=1, y=0)
    assert snapshot.tile_at(Position(x=1, y=0)).walkable
    assert World.model_validate_json(snapshot.model_dump_json()) == snapshot
    with pytest.raises(ValueError):
        snapshot.tile_at(Position(x=2, y=0))
    with pytest.raises(KeyError):
        snapshot.agent(AgentId(value=3))
    with pytest.raises(ValidationError):
        snapshot.tiles[0].__setattr__("shelter", True)


def test_visibility_is_a_clipped_square_including_diagonals() -> None:
    snapshot = World(width=8, height=8, tiles=(Tile(),) * 64)
    visible = snapshot.visible_positions(Position(x=0, y=0), 3)
    assert len(visible) == 16
    assert Position(x=3, y=3) in visible
    assert Position(x=4, y=0) not in visible
    assert len(snapshot.visible_positions(Position(x=4, y=4), 3)) == 49
    with pytest.raises(ValueError):
        snapshot.visible_positions(Position(x=0, y=0), -1)
