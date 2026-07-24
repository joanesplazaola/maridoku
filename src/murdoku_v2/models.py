from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .object_catalog import OBJECT_CATALOG, footprint_kind


class CharacterModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    gender: Literal["woman", "man"] | str


class RoomModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    cells: list[tuple[int, int]]
    label_anchor: tuple[int, int] | None = None


class RoomGroupModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    clue_label: str | None = None
    rooms: list[str]


class ObjectModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    name: str | None = None
    cells: list[tuple[int, int]] = Field(default_factory=list)
    row: int | None = None
    column: int | None = None
    occupiable: bool = False
    blocks_character: bool = False

    @model_validator(mode="after")
    def normalise_cells(self) -> "ObjectModel":
        if not self.cells and self.row is not None and self.column is not None:
            self.cells = [(self.row, self.column)]
        if not self.cells:
            raise ValueError(f"El objeto {self.id} no tiene huella.")
        return self


class BoardModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    rows: int = Field(gt=0)
    columns: int = Field(gt=0)
    rooms: list[RoomModel]
    room_groups: list[RoomGroupModel] = Field(default_factory=list)
    objects: list[ObjectModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_geometry(self) -> "BoardModel":
        expected = {(row, column) for row in range(self.rows) for column in range(self.columns)}
        actual: list[tuple[int, int]] = [cell for room in self.rooms for cell in room.cells]
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError("Las habitaciones deben cubrir cada casilla exactamente una vez.")
        room_ids = {room.id for room in self.rooms}
        if len(room_ids) != len(self.rooms):
            raise ValueError("Hay identificadores de habitación repetidos.")
        for group in self.room_groups:
            unknown = set(group.rooms) - room_ids
            if unknown:
                raise ValueError(f"El grupo {group.id} referencia habitaciones inexistentes: {sorted(unknown)}")
        room_at = {cell: room.id for room in self.rooms for cell in room.cells}
        for obj in self.objects:
            if any(cell not in expected for cell in obj.cells):
                raise ValueError(f"El objeto {obj.id} sale del tablero.")
            cells = set(obj.cells)
            if len(cells) != len(obj.cells):
                raise ValueError(f"El objeto {obj.id} repite casillas.")
            if len({room_at[cell] for cell in cells}) != 1:
                raise ValueError(f"El objeto {obj.id} atraviesa paredes.")
            connected = {next(iter(cells))}
            while frontier := {
                neighbor
                for row, column in connected
                for neighbor in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
                if neighbor in cells - connected
            }:
                connected |= frontier
            if connected != cells:
                raise ValueError(f"El objeto {obj.id} tiene una huella desconectada.")
            spec = OBJECT_CATALOG.get(obj.type)
            if spec is None:
                raise ValueError(f"El objeto {obj.id} usa un tipo fuera del catálogo: {obj.type}.")
            footprint = footprint_kind(obj.cells)
            if footprint not in spec.footprints:
                raise ValueError(
                    f"El objeto {obj.id} usa huella {footprint}; {obj.type} admite {spec.footprints}."
                )
        return self


class StatementModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    args: dict[str, Any]
    text: str = ""
    family: str | None = None


class CardModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    character: str
    role: Literal["victim", "suspect"] | str
    statements: list[StatementModel]


class PuzzleModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int
    id: str
    seed: int
    board: BoardModel
    characters: list[CharacterModel]
    victim: str
    cards: list[CardModel]

    @model_validator(mode="after")
    def validate_contract(self) -> "PuzzleModel":
        if self.board.rows != self.board.columns:
            raise ValueError("El tablero debe ser cuadrado para la regla de filas y columnas.")
        if len(self.characters) != self.board.rows:
            raise ValueError("Debe haber tantos personajes como filas y columnas.")
        character_ids = [character.id for character in self.characters]
        if len(set(character_ids)) != len(character_ids):
            raise ValueError("Hay identificadores de personaje repetidos.")
        if self.victim not in character_ids:
            raise ValueError("La víctima no figura entre los personajes.")
        card_characters = [card.character for card in self.cards]
        if set(card_characters) != set(character_ids) or len(card_characters) != len(character_ids):
            raise ValueError("Debe existir exactamente una tarjeta por personaje.")
        for card in self.cards:
            if not 1 <= len(card.statements) <= 2:
                raise ValueError(f"La tarjeta {card.id} debe contener una o dos afirmaciones.")
            for statement in card.statements:
                subject = statement.args.get("character")
                if subject != card.character:
                    raise ValueError(
                        f"La afirmación {statement.id} no está centrada en el personaje de su tarjeta."
                    )
        return self


def validate_puzzle(data: dict[str, Any]) -> PuzzleModel:
    """Validate and normalise the public puzzle JSON contract."""
    return PuzzleModel.model_validate(data)
