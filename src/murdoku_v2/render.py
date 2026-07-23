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
    type_ = str(obj.get("type") or "object").lower()
    art = {
        "plant": '<path d="M29 43h22l-3 15H32z"/><path class="soft" d="M40 43C17 34 22 13 39 28 35 7 55 8 47 29c17-14 23 7 2 14z"/>',
        "table": '<ellipse class="soft" cx="40" cy="31" rx="25" ry="16"/><path d="M18 31h44v8H18zM22 39h6l-3 20h-6zm30 0h6l3 20h-6z"/><ellipse cx="40" cy="31" rx="23" ry="13"/>',
        "rug": '<rect x="10" y="17" width="60" height="46" rx="7"/><path class="soft" d="M17 24h46v32H17zM24 40l16-11 16 11-16 11z"/>',
        "carpet": '<rect x="10" y="17" width="60" height="46" rx="7"/><path class="soft" d="M17 24h46v32H17zM24 40l16-11 16 11-16 11z"/>',
        "sofa": '<path class="soft" d="M14 31c0-9 8-15 17-10l9 5 9-5c9-5 17 1 17 10v24H14z"/><path d="M10 34c0-8 10-8 10 0v12h40V34c0-8 10-8 10 0v24H10zM19 58h7v6h-7zm35 0h7v6h-7z"/>',
        "chair": '<path class="soft" d="M22 12h36v27H22z"/><path d="M18 35h44v11H18zM22 46h6l-3 18h-6zm30 0h6l3 18h-6z"/>',
        "bed": '<path class="soft" d="M11 25h58v34H11z"/><path d="M8 20h8v44H8zm56 0h8v44h-8zM16 50h48v9H16z"/><path class="paper" d="M18 28h18v13H18z"/>',
        "tv": '<rect class="soft" x="10" y="12" width="60" height="39" rx="5"/><path d="M35 51h10v8h12v6H23v-6h12z"/><path class="paper" d="M17 19h46v25H17z"/>',
    }.get(type_, '<circle class="soft" cx="40" cy="40" r="25"/><path d="M36 22h8v24h-8zm0 30h8v8h-8z"/>')
    return (
        f'<svg class="object {_object_class(obj)}" viewBox="0 0 80 80" role="img" '
        f'aria-label="{name}" title="{name}">{art}</svg>'
    )


def _stylesheet() -> str:
    assets = files("murdoku_v2").joinpath("assets")
    css = assets.joinpath("murdoku.css").read_text(encoding="utf-8")
    texture = base64.b64encode(assets.joinpath("case-paper.webp").read_bytes()).decode("ascii")
    return css.replace("__CASE_PAPER__", f"data:image/webp;base64,{texture}")


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
    for card in puzzle["cards"]:
        statements = "".join(
            f"<li><small>{html.escape(_statement_tag(statement))}</small>"
            f"{html.escape(statement['text'])}</li>"
            for statement in card["statements"]
        )
        role = "Victima" if card["role"] == "victim" else "Sospechoso"
        cards.append(
            f"<article class=\"card {html.escape(card['role'])}\">"
            f"<header><div class=\"portrait\" aria-hidden=\"true\">{html.escape(card['character_name'][0])}</div>"
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
