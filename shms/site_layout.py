"""Synthetic map coordinates and pedestrian network shared by the site plan and report form."""

from dataclasses import dataclass
from heapq import heappop, heappush

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Area, Hazard


@dataclass(frozen=True)
class Unit:
    code: str
    name: str
    x: int
    y: int
    w: int
    h: int
    equipment: str
    caption: str
    reporting: bool = False


UNITS = (
    Unit("BXH", "Bauxite handling", 92, 110, 159, 128, "stock", "Jetty & stockpile", True),
    Unit("GRD", "Grinding", 276, 124, 145, 114, "mill", "Pre-desilication", True),
    Unit("DIG", "Digestion", 446, 99, 165, 139, "dig", "HP digesters · flash tanks", True),
    Unit("CLR", "Clarification", 638, 111, 143, 127, "clar", "Settling vessels", True),
    Unit("CCD", "Residue washing", 814, 121, 150, 117, "clar", "Counter-current decantation"),
    Unit("RS", "Residue storage", 1010, 95, 158, 259, "pond", "Wash train discharge"),
    Unit("SILO", "Product silos", 99, 310, 149, 128, "silo", "Conveyor to ship loader"),
    Unit("CAL", "Calcination", 270, 329, 156, 109, "kiln", "Calciner & cooler", True),
    Unit("HYD", "Hydrate classification", 453, 318, 157, 120, "disc", "Product / coarse / fine seed"),
    Unit("PRC", "Precipitation", 634, 299, 152, 139, "seed", "Seeded tank train", True),
    Unit("FLT", "Security filtration", 822, 327, 142, 111, "disc", "Liquor filters", True),
    Unit("TNK", "Caustic tank farm", 98, 511, 154, 127, "silo", "Unloading & storage", True),
    Unit("PWR", "Powerhouse", 275, 523, 155, 115, "boiler", "Steam & utilities", True),
    Unit("WAT", "Water treatment", 460, 529, 144, 109, "clar", "Treatment basins"),
    Unit("EVP", "Evaporation", 642, 514, 142, 124, "dig", "Spent liquor recovery"),
    Unit("CCR", "Control room", 826, 542, 138, 96, "shed", "CCR"),
    Unit("MNT", "Maintenance", 1005, 506, 155, 66, "shed", "Workshop"),
    Unit("WH", "Warehouse", 1005, 583, 155, 66, "shed", "Stores"),
    Unit("ADM", "Administration", 820, 709, 145, 62, "shed", "Site offices"),
    Unit("GT", "Gatehouse", 91, 708, 135, 62, "shed", "Main entrance"),
)

Point = tuple[int, int]
GATE: Point = (70, 739)
FRONTS = (255, 455, 655)
SIDES = (70, 986)


def walkway_edges() -> list[tuple[Point, Point]]:
    """Only the marked frontage walks, entrance spurs and two perimeter connections."""
    edges = [(GATE, (SIDES[0], FRONTS[-1]))]
    for x in SIDES:
        edges.extend(((x, a), (x, b)) for a, b in zip(FRONTS, FRONTS[1:], strict=False))
    for y in FRONTS:
        xs = [*SIDES]
        for unit in UNITS:
            if unit.y + unit.h + 17 == y:
                x = unit.x + unit.w // 2
                xs.append(x)
                edges.append(((x, y), (x, y - 17)))
        xs.sort()
        edges.extend(((a, y), (b, y)) for a, b in zip(xs, xs[1:], strict=False))
    return edges


def flagged_areas(db: Session) -> set[str]:
    from .services import ACTIVE

    return set(
        db.scalars(
            select(Area.code)
            .join(Hazard)
            .where(Hazard.status.in_(ACTIVE), Hazard.risk_level.in_(("High", "Extreme")))
            .distinct()
        )
    )


def walk_route(code: str, flagged: set[str]) -> list[Point]:
    """Shortest marked walk excluding the entrance and frontage of every flagged area."""
    dest = next((u for u in UNITS if u.code == code and u.reporting), None)
    if dest is None or code in flagged:
        return []
    target = (dest.x + dest.w // 2, dest.y + dest.h)
    blocked = {(u.x + u.w // 2, u.y + u.h + 17) for u in UNITS if u.code in flagged}
    graph: dict[Point, list[Point]] = {}
    for a, b in walkway_edges():
        if a not in blocked and b not in blocked:
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
    queue = [(0, GATE)]
    distance = {GATE: 0}
    parent: dict[Point, Point] = {}
    while queue:
        cost, node = heappop(queue)
        if node == target:
            result = [node]
            while result[-1] != GATE:
                result.append(parent[result[-1]])
            return result[::-1]
        if cost != distance[node]:
            continue
        for other in graph.get(node, []):
            new = cost + abs(node[0] - other[0]) + abs(node[1] - other[1])
            if other not in distance or new < distance[other]:
                distance[other] = new
                parent[other] = node
                heappush(queue, (new, other))
    return []
