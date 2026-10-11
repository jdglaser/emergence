"""A* correctness and stable tie breaking over explicit knowledge."""

from emergence.domain.values import Position
from emergence.simulation.pathfinding import distance, find_path


def test_astar_shortest_deterministic_detour() -> None:
    origin = Position(x=0, y=1)
    destination = Position(x=2, y=1)
    wall = Position(x=1, y=1)
    known = frozenset(Position(x=x, y=y) for y in range(3) for x in range(3)) - {wall}
    expected = (Position(x=0, y=0), Position(x=1, y=0), Position(x=2, y=0), destination)
    assert find_path(origin, destination, known) == expected
    assert find_path(origin, destination, frozenset(reversed(tuple(known)))) == expected
    assert all(
        distance(a, b) == 1
        for a, b in zip((origin,) + expected, expected, strict=False)
    )


def test_astar_unknown_disconnected_and_occupied_targets() -> None:
    origin = Position(x=0, y=0)
    destination = Position(x=2, y=0)
    assert find_path(origin, destination, frozenset({origin})) is None
    assert find_path(origin, destination, frozenset({origin, destination})) is None
    known = frozenset({origin, Position(x=1, y=0), destination})
    assert find_path(origin, destination, known, frozenset({destination})) is None
    assert find_path(origin, origin, known) == ()
