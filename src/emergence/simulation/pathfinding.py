"""Deterministic cardinal A* over caller-supplied knowledge, never the world."""

import heapq

from emergence.domain.values import Position


def distance(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def neighbors(position: Position) -> tuple[Position, ...]:
    return (
        Position(x=position.x, y=position.y - 1),
        Position(x=position.x + 1, y=position.y),
        Position(x=position.x, y=position.y + 1),
        Position(x=position.x - 1, y=position.y),
    )


def find_path(
    origin: Position,
    destination: Position,
    walkable: frozenset[Position],
    blocked: frozenset[Position] = frozenset(),
) -> tuple[Position, ...] | None:
    """Return steps excluding origin. Heap ties use coordinates, then path cost."""
    if destination not in walkable or destination in blocked:
        return None

    frontier: list[tuple[int, int, int, int]] = [
        (distance(origin, destination), origin.y, origin.x, 0)
    ]
    costs = {origin: 0}
    previous: dict[Position, Position] = {}
    while frontier:
        _, y, x, cost = heapq.heappop(frontier)
        current = Position(x=x, y=y)
        if cost != costs[current]:
            continue
        if current == destination:
            path: list[Position] = []
            while current != origin:
                path.append(current)
                current = previous[current]
            return tuple(reversed(path))

        for adjacent in neighbors(current):
            if adjacent not in walkable or adjacent in blocked:
                continue
            next_cost = cost + 1
            if next_cost >= costs.get(adjacent, next_cost + 1):
                continue
            costs[adjacent] = next_cost
            previous[adjacent] = current
            heapq.heappush(
                frontier,
                (
                    next_cost + distance(adjacent, destination),
                    adjacent.y,
                    adjacent.x,
                    next_cost,
                ),
            )

    return None
