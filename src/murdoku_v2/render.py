from __future__ import annotations

import base64
import html
import json
from importlib.resources import files
from pathlib import Path
from typing import Any


def _room_lookup(board: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    return {
        tuple(cell): room
        for room in board["rooms"]
        for cell in room["cells"]
    }


def _object_lookup(board: dict[str, Any]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    result: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for obj in board.get("objects", []):
        cells = obj.get("cells") or [[obj.get("row"), obj.get("column")]]
        for cell in cells:
            result.setdefault(tuple(cell), []).append(obj)
    return result


def _statement_tag(statement: dict[str, Any]) -> str:
    family = statement.get("family", "")
    return {
        "murder_rule": "Crimen",
        "relative_distance": "Distancia",
        "relative_order": "Orden",
        "coordinate": "Posición",
        "object_occupancy": "Objeto",
        "object_line": "Objeto",
        "object_adjacency": "Objeto",
        "room_population": "Sala",
        "room_exact": "Sala",
        "room_choice": "Sala",
        "room_relation": "Habitación",
    }.get(family, "Pista")


def _object_class(obj: dict[str, Any]) -> str:
    value = str(obj.get("type") or "object").lower().replace("_", "-")
    return f"object-{html.escape(value)}"


def _object_marker(obj: dict[str, Any]) -> str:
    name = html.escape(obj.get("name") or obj.get("type") or "Objeto")
    return f'<span class="object {_object_class(obj)}" role="img" aria-label="{name}" title="{name}"></span>'


def _stylesheet() -> str:
    assets = files("murdoku_v2").joinpath("assets")
    css = assets.joinpath("murdoku.css").read_text(encoding="utf-8")
    replacements = {
        "__CASE_PAPER__": assets.joinpath("case-paper.webp"),
        "__PORTRAITS__": assets.joinpath("portraits.webp"),
        "__PLANT__": assets.joinpath("furniture/plant.webp"),
        "__TABLE__": assets.joinpath("furniture/table.webp"),
        "__RUG__": assets.joinpath("furniture/rug.webp"),
        "__SOFA__": assets.joinpath("furniture/sofa.webp"),
    }
    for marker, asset in replacements.items():
        data = base64.b64encode(asset.read_bytes()).decode("ascii")
        css = css.replace(marker, f"data:image/webp;base64,{data}")
    return css


def render_html(puzzle: dict[str, Any]) -> str:
    board = puzzle["board"]
    rooms = _room_lookup(board)
    objects = _object_lookup(board)
    room_classes = {room["id"]: f"room-{index % 6}" for index, room in enumerate(board["rooms"])}
    room_labels = {
        room["id"]: tuple(room.get("label_anchor", room["cells"][0]))
        for room in board["rooms"]
    }
    rows = []
    for row in range(board["rows"]):
        cells = []
        for column in range(board["columns"]):
            room = rooms[(row, column)]
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
            cell_objects = objects.get((row, column), [])
            label = html.escape(room["name"]) if room_labels[room["id"]] == (row, column) else ""
            label_html = f'<span class="room-name">{label}</span>' if label else ""
            markers = "".join(_object_marker(obj) for obj in cell_objects)
            cells.append(
                f"<td class=\"{room_classes[room['id']]} {' '.join(wall_classes)}\">"
                f"<b>{row + 1}.{column + 1}</b>{label_html}<div class=\"objects\">{markers}</div></td>"
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")

    cards = []
    gender_slots = {"woman": 0, "man": 0}
    gender_by_character = {character["id"]: character.get("gender", "woman") for character in puzzle["characters"]}
    for card in puzzle["cards"]:
        statements = "".join(
            f"<li><small>{html.escape(_statement_tag(statement))}</small>"
            f"{html.escape(statement['text'])}</li>"
            for statement in card["statements"]
        )
        role = "Victima" if card["role"] == "victim" else "Sospechoso"
        gender = gender_by_character.get(card["character"], "woman")
        portrait_column = min(gender_slots.get(gender, 0), 3)
        gender_slots[gender] = portrait_column + 1
        portrait_x = (0, 33.333, 66.667, 100)[portrait_column]
        portrait_y = 100 if gender == "man" else 0
        cards.append(
            f"<article class=\"card {html.escape(card['role'])}\">"
            f"<header><div class=\"portrait\" style=\"--portrait-x:{portrait_x}%;--portrait-y:{portrait_y}%\" "
            f"role=\"img\" aria-label=\"Retrato de {html.escape(card['character_name'])}\"></div>"
            f"<div><h2>{html.escape(card['character_name'])}</h2><p>{role}</p></div></header>"
            f"<ol>{statements}</ol></article>"
        )
    legend = "".join(
        f"<li>{_object_marker(obj)}{html.escape(obj.get('name') or obj.get('type') or 'Objeto')}</li>"
        for obj in board.get("objects", [])
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
    <header class="titlebar">
      <div class="masthead">
        <span class="eyebrow">Archivo de investigación</span>
        <h1>{html.escape(board.get('name') or puzzle['id'])}</h1>
        <p class="subtitle">Una víctima. Una habitación. Un asesino entre los presentes.</p>
      </div>
      <div class="case-id"><span>Caso</span>{html.escape(puzzle['id'])}</div>
    </header>
    <div class="layout">
      <aside class="board-wrap">
        <div class="board-heading"><span>Plano de la escena</span><i>N</i></div>
        <div class="board-frame">
          <table aria-label="Tablero" style="--cols: {int(board['columns'])}">{''.join(rows)}</table>
        </div>
        <ul class="legend" aria-label="Objetos">{legend}</ul>
      </aside>
      <main><div class="section-heading"><span>Declaraciones</span><small>{len(cards)} expedientes</small></div>{''.join(cards)}</main>
    </div>
  </div>
</body>
</html>
"""


def render_file(puzzle_path: Path, output: Path) -> None:
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(puzzle), encoding="utf-8")
