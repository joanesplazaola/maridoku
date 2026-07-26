from __future__ import annotations

import base64
import html
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

from .models import load_puzzle

def _room_lookup(board: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    return {
        tuple(cell): room
        for room in board["rooms"]
        for cell in room["cells"]
    }


def _display_statement(text: str, character_name: str, gender: str) -> str:
    if text.startswith(character_name):
        shortened = text[len(character_name):].lstrip(" ,:")
        return shortened[:1].upper() + shortened[1:]
    pronoun = "ella" if gender == "woman" else "él"
    return re.sub(rf"\b{re.escape(character_name)}\b", pronoun, text)


def _object_class(obj: dict[str, Any]) -> str:
    value = str(obj.get("type") or "object").lower().replace("_", "-")
    return f"object-{html.escape(value)}"


def _object_marker(obj: dict[str, Any]) -> str:
    name = html.escape(obj.get("name") or obj.get("type") or "Objeto")
    return f'<span class="object {_object_class(obj)}" role="img" aria-label="{name}" title="{name}"></span>'


def _object_placement(obj: dict[str, Any]) -> str:
    cells = {tuple(cell) for cell in (obj.get("cells") or [[obj["row"], obj["column"]]])}
    min_row = min(row for row, _ in cells)
    max_row = max(row for row, _ in cells)
    min_column = min(column for _, column in cells)
    max_column = max(column for _, column in cells)
    height = max_row - min_row + 1
    width = max_column - min_column + 1
    missing = {
        (row - min_row, column - min_column)
        for row in range(min_row, max_row + 1)
        for column in range(min_column, max_column + 1)
        if (row, column) not in cells
    }
    footprint = "1x1"
    if len(cells) == 2 and {height, width} == {1, 2}:
        footprint = "1x2"
    elif len(cells) == 4 and height == width == 2:
        footprint = "2x2"
    elif len(cells) == 3 and height == width == 2:
        footprint = "L3"
    shape = f" footprint-{footprint}"
    if height == width == 2 and len(cells) == 3:
        shape = f" shape-l-missing-{next(iter(missing))[0]}-{next(iter(missing))[1]}"
    if height > width:
        shape += " vertical"
    layer = " floor-object" if obj.get("layer") == "floor" else ""
    style = (
        f"--object-row:{min_row + 1};--object-column:{min_column + 1};"
        f"--object-height:{height};--object-width:{width};"
        f"--object-rotation:{int(obj.get('rotation', 0))}deg"
    )
    return (
        f'<div class="object-placement{layer}{shape}" '
        f'data-object-type="{html.escape(obj["type"])}" style="{style}">'
        f"{_object_marker(obj)}</div>"
    )


def _stylesheet() -> str:
    assets = files("murdoku_v2").joinpath("assets")
    css = assets.joinpath("murdoku.css").read_text(encoding="utf-8")
    replacements = {
        "__CASE_PAPER__": assets.joinpath("case-paper.webp"),
        "__PORTRAITS__": assets.joinpath("portraits.webp"),
        "__PORTRAIT_IRENE__": assets.joinpath("portrait-irene.webp"),
        "__PLANT__": assets.joinpath("furniture/plant.webp"),
        "__TABLE__": assets.joinpath("furniture/table.webp"),
        "__RUG__": assets.joinpath("furniture/rug.webp"),
        "__RUG_L__": assets.joinpath("furniture/rug-l.webp"),
        "__SOFA__": assets.joinpath("furniture/sofa.webp"),
        "__BED__": assets.joinpath("furniture/bed.webp"),
        "__BED_HORIZONTAL__": assets.joinpath("furniture/bed-horizontal.webp"),
        "__CHAIR__": assets.joinpath("furniture/chair.webp"),
        "__TV__": assets.joinpath("furniture/tv.webp"),
        "__DINING_TABLE__": assets.joinpath("furniture/dining-table.webp"),
        "__DINING_TABLE_HORIZONTAL__": assets.joinpath("furniture/dining-table-horizontal.webp"),
        "__BOOKSHELF__": assets.joinpath("furniture/bookshelf.webp"),
        "__BOOKSHELF_HORIZONTAL__": assets.joinpath("furniture/bookshelf-horizontal.webp"),
        "__WARDROBE__": assets.joinpath("furniture/wardrobe.webp"),
        "__WARDROBE_HORIZONTAL__": assets.joinpath("furniture/wardrobe-horizontal.webp"),
        "__COUNTER_L__": assets.joinpath("furniture/counter-l.webp"),
        "__COUNTER_STRAIGHT__": assets.joinpath("furniture/counter-straight.webp"),
        "__FLAG__": assets.joinpath("furniture/flag.webp"),
    }
    for marker, asset in replacements.items():
        data = base64.b64encode(asset.read_bytes()).decode("ascii")
        css = css.replace(marker, f"data:image/webp;base64,{data}")
    return css


def _player_script() -> str:
    return files("murdoku_v2").joinpath("assets/player.js").read_text(encoding="utf-8")


def render_html(puzzle: dict[str, Any], *, navigation: dict[str, Any] | None = None) -> str:
    board = puzzle["board"]
    rooms = _room_lookup(board)
    room_classes = {room["id"]: f"room-{index % 6}" for index, room in enumerate(board["rooms"])}
    room_labels = {
        room["id"]: tuple(room.get("label_anchor", room["cells"][0]))
        for room in board["rooms"]
    }
    zones_at: dict[tuple[int, int], list[int]] = {}
    zone_labels = {}
    for index, zone in enumerate(board.get("zones", [])):
        for cell in zone["cells"]:
            zones_at.setdefault(tuple(cell), []).append(index)
        zone_labels[tuple(zone["cells"][0])] = zone["name"]
    sequence_at = {
        tuple(cell): (sequence["item_label"], index + 1)
        for sequence in board.get("sequences", [])
        for index, cell in enumerate(sequence["cells"])
    }
    rows = []
    for row in range(board["rows"]):
        cells = []
        for column in range(board["columns"]):
            room = rooms[(row, column)]
            zone_classes = " ".join(
                f"zone-cell zone-{index % 3}"
                for index in zones_at.get((row, column), [])
            )
            wall_classes = [
                name
                for name, neighbor in {
                    "wall-n": (row - 1, column),
                    "wall-s": (row + 1, column),
                    "wall-w": (row, column - 1),
                    "wall-e": (row, column + 1),
                }.items()
                if neighbor not in rooms or rooms[neighbor]["id"] != room["id"]
            ]
            label = html.escape(room["name"]) if room_labels[room["id"]] == (row, column) else ""
            label_html = f'<span class="room-name">{label}</span>' if label else ""
            sequence = sequence_at.get((row, column))
            sequence_html = (
                f'<span class="sequence-label" title="{html.escape(sequence[0])} {sequence[1]}">'
                f'{html.escape(sequence[0][:1].upper())}{sequence[1]}</span>'
                if sequence else ""
            )
            zone_label = zone_labels.get((row, column))
            zone_label_html = (
                f'<span class="zone-label">{html.escape(zone_label).upper()}</span>'
                if zone_label else ""
            )
            cells.append(
                f"<td class=\"{room_classes[room['id']]} {' '.join(wall_classes)} {zone_classes}\" "
                f"data-row=\"{row}\" data-column=\"{column}\" tabindex=\"0\" "
                f"aria-label=\"Fila {row + 1}, columna {column + 1}\">"
                f"{label_html}{zone_label_html}{sequence_html}</td>"
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    furniture = "".join(
        _object_placement(obj)
        for obj in sorted(board.get("objects", []), key=lambda item: item.get("layer") != "floor")
    )

    cards = []
    gender_slots = {"woman": 0, "man": 0}
    gender_by_character = {character["id"]: character.get("gender", "woman") for character in puzzle["characters"]}
    name_by_character = {character["id"]: character["name"] for character in puzzle["characters"]}
    for card in puzzle["cards"]:
        gender = gender_by_character.get(card["character"], "woman")
        character_name = card.get("character_name") or name_by_character[card["character"]]
        statement_items = []
        for statement in card["statements"]:
            object_type = statement["args"].get("object_type")
            object_attribute = (
                f' data-object-type="{html.escape(object_type)}" tabindex="0"'
                if object_type else ""
            )
            statement_items.append(
                f'<li data-statement="{html.escape(statement["id"])}"{object_attribute}>'
                f"{html.escape(_display_statement(statement.get('text', ''), character_name, gender))}</li>"
            )
        statements = "".join(statement_items)
        portrait_column = min(gender_slots.get(gender, 0), 3)
        gender_slots[gender] = portrait_column + 1
        portrait_x = (0, 33.333, 66.667, 100)[portrait_column]
        portrait_y = 100 if gender == "man" else 0
        victim_badge = '<small class="victim-badge">V · VÍCTIMA</small>' if card["role"] == "victim" else ""
        cards.append(
            f"<article class=\"card {html.escape(card['role'])}\" data-card=\"{html.escape(card['character'])}\">"
            f"<button class=\"person-select\" type=\"button\" data-character=\"{html.escape(card['character'])}\" "
            f"data-portrait-x=\"{portrait_x}%\" data-portrait-y=\"{portrait_y}%\" draggable=\"true\" "
            f"aria-label=\"Seleccionar a {html.escape(character_name)}\">"
            f"<span class=\"portrait\" style=\"--portrait-x:{portrait_x}%;--portrait-y:{portrait_y}%\" "
            f"role=\"img\" aria-label=\"Retrato de {html.escape(character_name)}\"></span>"
            f"<span><h2>{html.escape(character_name)}</h2>"
            f"{victim_badge}"
            f"</span></button>"
            f"<ol>{statements}</ol></article>"
        )
    puzzle_data = base64.b64encode(
        json.dumps(puzzle, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    general_clues = ""
    if puzzle.get("general_clues"):
        items = "".join(
            f"<li>{html.escape(statement.get('text', ''))}</li>"
            for statement in puzzle["general_clues"]
        )
        general_clues = f'<section class="general-clues" aria-label="Pistas generales"><ul>{items}</ul></section>'
    level_navigation = ""
    if navigation:
        previous = (
            f'<a href="{html.escape(navigation["previous"])}" aria-label="Nivel anterior">←</a>'
            if navigation.get("previous") else "<span></span>"
        )
        following = (
            f'<a href="{html.escape(navigation["next"])}" aria-label="Nivel siguiente">→</a>'
            if navigation.get("next") else "<span></span>"
        )
        level_navigation = (
            f'<nav class="level-navigation">{previous}<a href="../index.html">'
            f'Nivel {int(navigation["number"]):02d}</a>{following}</nav>'
        )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(puzzle['id'])}</title>
  <style>{_stylesheet()}</style>
</head>
<body>
  <div class="sheet">
    {level_navigation}
    <header class="titlebar">
      <div class="masthead">
        <span class="eyebrow">Archivo de investigación</span>
        <h1>{html.escape(puzzle.get('title') or board.get('name') or puzzle['id'])}</h1>
        <p class="subtitle">{html.escape(puzzle.get('story') or 'Una víctima. Una habitación. Un asesino entre los presentes.')}</p>
      </div>
      <div class="case-id"><span>Caso</span>{html.escape(puzzle['id'])}</div>
    </header>
    <div class="layout">
      <aside class="board-wrap">
        <div class="board-heading"><span>Plano de la escena</span><i>N</i></div>
        <div class="game-toolbar" aria-label="Controles del puzle">
          <button type="button" data-action="undo" title="Deshacer" aria-label="Deshacer">↶</button>
          <button type="button" data-action="reset" title="Reiniciar" aria-label="Reiniciar">↺</button>
          <button type="button" data-tool="cross" title="Marcar como imposible" aria-label="Marcar como imposible">×</button>
          <button type="button" data-tool="candidate" title="Marcar posición posible" aria-label="Marcar posición posible">✎</button>
          <button type="button" data-tool="erase" title="Borrar casilla" aria-label="Borrar casilla">⌫</button>
          <button type="button" class="check-button" data-action="check">Comprobar</button>
          <button type="button" data-action="export" title="Exportar sesión" aria-label="Exportar sesión">⇩</button>
          <output class="game-status" aria-live="polite">Coloca a los personajes</output>
        </div>
        <div class="board-frame">
          <div class="board-stage" style="--cols:{int(board['columns'])};--rows:{int(board['rows'])}">
            <table aria-label="Tablero" style="--cols:{int(board['columns'])};--rows:{int(board['rows'])}">{''.join(rows)}</table>
            <div class="furniture-layer" aria-label="Mobiliario">{furniture}</div>
          </div>
        </div>
      </aside>
      <main><div class="section-heading"><span>Declaraciones</span><small>{len(cards)} expedientes</small></div>{general_clues}{''.join(cards)}</main>
    </div>
  </div>
  <script type="application/json" id="puzzle-data">{puzzle_data}</script>
  <script>{_player_script()}</script>
</body>
</html>
"""


def render_file(puzzle_path: Path, output: Path) -> None:
    puzzle = load_puzzle(puzzle_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(puzzle), encoding="utf-8")
