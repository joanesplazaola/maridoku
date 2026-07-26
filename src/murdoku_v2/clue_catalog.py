from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ClueSpec:
    type: str
    family: str
    summary: str
    subject_centred: bool = True
    supports_partial_propagation: bool = True


SPECS: tuple[ClueSpec, ...] = (
    ClueSpec("room", "room_exact", "El personaje está en una habitación concreta."),
    ClueSpec("exact_row", "coordinate", "El personaje está en una fila concreta."),
    ClueSpec("exact_column", "coordinate", "El personaje está en una columna concreta."),
    ClueSpec("room_population", "room_population", "Cantidad total de personas en su habitación."),
    ClueSpec("alone_in_room", "room_population", "Está solo en una habitación concreta."),
    ClueSpec("room_gender_count", "room_composition", "Cantidad de un género en su habitación, incluyéndole."),
    ClueSpec("companion_gender_count", "room_companion", "Cantidad de acompañantes de un género, excluyéndole."),
    ClueSpec("alone_with_gender", "room_companion", "Está únicamente con una persona de un género."),
    ClueSpec("not_adjacent_to_wall", "room_geometry", "No toca ninguna pared de su habitación."),
    ClueSpec("in_room_corner", "room_geometry", "Está en una esquina de su habitación."),
    ClueSpec("in_room_group", "room_group", "Está en una habitación de un grupo jerárquico."),
    ClueSpec("room_disjunction", "room_choice", "Está en una de dos habitaciones."),
    ClueSpec("unique_on_object", "object_occupancy", "Es la única persona situada sobre un tipo de objeto."),
    ClueSpec("object_same_row_in_room", "object_line", "Comparte fila y habitación con un tipo de objeto."),
    ClueSpec("object_same_column_in_room", "object_line", "Comparte columna y habitación con un tipo de objeto."),
    ClueSpec("adjacent_object", "object_adjacency", "Está ortogonalmente junto a un tipo de objeto."),
    ClueSpec("unique_adjacent_object", "object_adjacency", "Es la única persona ortogonalmente junto a un tipo de objeto."),
    ClueSpec("relative_row_order", "relative_order", "Está al norte o al sur de otra persona."),
    ClueSpec("relative_column_order", "relative_order", "Está al este o al oeste de otra persona."),
    ClueSpec("relative_row_distance", "relative_distance", "Distancia vertical exacta respecto a otra persona."),
    ClueSpec("relative_column_distance", "relative_distance", "Distancia horizontal exacta respecto a otra persona."),
    ClueSpec("same_diagonal", "relative_diagonal", "Está en la misma diagonal que otra persona."),
    ClueSpec("same_room", "room_relation", "Está en la misma habitación que otra persona."),
    ClueSpec("different_room", "room_relation", "Está en una habitación distinta de otra persona."),
)

CLUE_SPECS = {spec.type: spec for spec in SPECS}
if len(CLUE_SPECS) != len(SPECS):
    raise RuntimeError("El catálogo contiene tipos de pista duplicados.")


def catalog_json() -> list[dict[str, object]]:
    return [asdict(spec) for spec in SPECS]
