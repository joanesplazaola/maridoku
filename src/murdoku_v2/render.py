from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _room_lookup(board: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    return {
        tuple(cell): room
        for room in board["rooms"]
        for cell in room["cells"]
    }


def render_html(puzzle: dict[str, Any]) -> str:
    board = puzzle["board"]
    rooms = _room_lookup(board)
    positions = {(obj.get("row"), obj.get("column")): obj for obj in board.get("objects", [])}
    rows = []
    for row in range(board["rows"]):
        cells = []
        for column in range(board["columns"]):
            room = rooms[(row, column)]
            obj = positions.get((row, column))
            label = html.escape(room["name"]) if room.get("label_anchor") == [row, column] else ""
            marker = html.escape(obj["name"] if obj and obj.get("name") else obj["type"]) if obj else ""
            cells.append(f"<td><span>{label}</span><small>{marker}</small></td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    cards = []
    for card in puzzle["cards"]:
        statements = "".join(f"<li>{html.escape(statement['text'])}</li>" for statement in card["statements"])
        cards.append(
            f"<section><h2>{html.escape(card['character_name'])}</h2><ol>{statements}</ol></section>"
        )

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{html.escape(puzzle['id'])}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #202124; }}
    h1 {{ font-size: 24px; margin: 0 0 16px; }}
    table {{ border-collapse: collapse; margin-bottom: 24px; }}
    td {{ border: 2px solid #444; width: 88px; height: 64px; vertical-align: top; padding: 6px; }}
    td span {{ display: block; font-weight: 650; font-size: 12px; }}
    td small {{ display: block; margin-top: 8px; color: #5f6368; font-size: 11px; }}
    main {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    section {{ border: 1px solid #dadce0; padding: 12px; break-inside: avoid; }}
    h2 {{ font-size: 16px; margin: 0 0 8px; }}
    ol {{ margin: 0; padding-left: 20px; }}
    li {{ margin-bottom: 6px; }}
  </style>
</head>
<body>
  <h1>{html.escape(puzzle['id'])}</h1>
  <table>{''.join(rows)}</table>
  <main>{''.join(cards)}</main>
</body>
</html>
"""


def render_file(puzzle_path: Path, output: Path) -> None:
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(puzzle), encoding="utf-8")
