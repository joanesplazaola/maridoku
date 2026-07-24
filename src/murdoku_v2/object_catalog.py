from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ObjectSpec:
    type: str
    name: str
    footprints: tuple[str, ...]
    layer: str = "furniture"
    occupiable: bool = False
    blocks_character: bool = True


SPECS = (
    ObjectSpec("plant", "Planta", ("1x1",)),
    ObjectSpec("chair", "Silla", ("1x1",), occupiable=True, blocks_character=False),
    ObjectSpec("tv", "Televisión", ("1x1",)),
    ObjectSpec("table", "Mesa redonda", ("1x1", "1x2")),
    ObjectSpec("dining_table", "Mesa rectangular", ("1x2", "2x2")),
    ObjectSpec("sofa", "Sofá", ("1x1", "1x2"), occupiable=True, blocks_character=False),
    ObjectSpec("bed", "Cama individual", ("1x2",), occupiable=True, blocks_character=False),
    ObjectSpec("rug", "Alfombra", ("1x1", "1x2", "2x2", "L3"), "floor", True, False),
    ObjectSpec("bookshelf", "Estantería", ("1x2",)),
    ObjectSpec("wardrobe", "Armario", ("1x2",)),
    ObjectSpec("counter", "Mostrador", ("1x2", "L3")),
)

OBJECT_CATALOG = {spec.type: spec for spec in SPECS}


def footprint_kind(cells: Iterable[tuple[int, int]]) -> str:
    footprint = set(cells)
    height = max(row for row, _ in footprint) - min(row for row, _ in footprint) + 1
    width = max(column for _, column in footprint) - min(column for _, column in footprint) + 1
    if len(footprint) == 1:
        return "1x1"
    if len(footprint) == 2 and {height, width} == {1, 2}:
        return "1x2"
    if len(footprint) == 4 and height == width == 2:
        return "2x2"
    if len(footprint) == 3 and height == width == 2:
        return "L3"
    return "custom"


def catalog_json() -> list[dict[str, object]]:
    return [asdict(spec) for spec in SPECS]
