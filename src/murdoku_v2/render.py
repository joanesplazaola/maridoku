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
        "murder_rule": "Coartada",
        "relative_distance": "Distancia",
        "relative_order": "Orden",
        "coordinate": "Coord.",
        "object_occupancy": "Objeto",
        "object_line": "Objeto",
        "object_adjacency": "Objeto",
        "room_population": "Sala",
        "room_exact": "Sala",
        "room_choice": "Sala",
    }.get(family, "Pista")


def _object_initial(obj: dict[str, Any]) -> str:
    return html.escape(str(obj.get("name") or obj.get("type") or "?")[:1].upper())


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
            cell_objects = objects.get((row, column), [])
            label = html.escape(room["name"]) if room_labels[room["id"]] == (row, column) else ""
            label_html = f"<span>{label}</span>" if label else ""
            markers = "".join(
                "<span class=\"object\" title=\"{name}\">{initial}</span>".format(
                    name=html.escape(obj.get("name") or obj.get("type") or "Objeto"),
                    initial=_object_initial(obj),
                )
                for obj in cell_objects
            )
            cells.append(
                f"<td class=\"{room_classes[room['id']]}\">"
                f"<b>{row + 1}.{column + 1}</b>{label_html}<div>{markers}</div></td>"
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
            f"<section class=\"card {html.escape(card['role'])}\">"
            f"<header><h2>{html.escape(card['character_name'])}</h2><p>{role}</p></header>"
            f"<ol>{statements}</ol></section>"
        )
    legend = "".join(
        f"<li><span>{_object_initial(obj)}</span>{html.escape(obj.get('name') or obj.get('type') or 'Objeto')}</li>"
        for obj in board.get("objects", [])
    )

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(puzzle['id'])}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #182026;
      --muted: #66737f;
      --paper: #fbfaf7;
      --line: #26313a;
      --accent: #b94135;
      --gold: #d99b2b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #ebe7df;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .sheet {{
      max-width: 1180px;
      margin: 24px auto;
      padding: 28px;
      background: var(--paper);
      border: 1px solid #d8d0c3;
      box-shadow: 0 18px 50px rgb(43 36 25 / 14%);
    }}
    .titlebar {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: end;
      border-bottom: 3px solid var(--line);
      padding-bottom: 16px;
      margin-bottom: 22px;
    }}
    h1 {{ font-size: clamp(26px, 4vw, 44px); line-height: 1; margin: 0; letter-spacing: 0; }}
    .subtitle {{ margin: 8px 0 0; color: var(--muted); font-size: 14px; }}
    .case-id {{ border: 1px solid var(--line); padding: 10px 12px; font-weight: 800; font-size: 13px; text-transform: uppercase; }}
    .layout {{ display: grid; grid-template-columns: minmax(360px, 1fr) 1.05fr; gap: 24px; align-items: start; }}
    .board-wrap {{ position: sticky; top: 18px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; border: 3px solid var(--line); background: white; }}
    td {{
      position: relative;
      width: calc(100% / var(--cols));
      aspect-ratio: 1;
      border: 1px solid rgb(24 32 38 / 24%);
      vertical-align: top;
      padding: 6px;
      overflow: hidden;
    }}
    td b {{ font-size: 10px; color: rgb(24 32 38 / 48%); font-weight: 750; }}
    td > span {{ display: block; margin-top: 4px; font-size: 10px; font-weight: 800; line-height: 1.1; text-transform: uppercase; }}
    td div {{ position: absolute; left: 6px; right: 6px; bottom: 6px; display: flex; gap: 4px; flex-wrap: wrap; }}
    .room-0 {{ background: #f4d7cf; }}
    .room-1 {{ background: #e7edd7; }}
    .room-2 {{ background: #d7e6ed; }}
    .room-3 {{ background: #efe3c8; }}
    .room-4 {{ background: #e7dced; }}
    .room-5 {{ background: #dce9df; }}
    .object {{
      display: inline-grid;
      place-items: center;
      width: 22px;
      height: 22px;
      border-radius: 999px;
      background: var(--ink);
      color: white;
      font-size: 11px;
      font-weight: 850;
      box-shadow: 0 1px 0 rgb(255 255 255 / 45%) inset;
    }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 8px 12px; list-style: none; padding: 0; margin: 12px 0 0; color: var(--muted); font-size: 12px; }}
    .legend li {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend span {{ display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 999px; background: var(--ink); color: white; font-size: 10px; font-weight: 800; }}
    main {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .card {{
      min-height: 150px;
      padding: 14px;
      background: white;
      border: 1px solid #d8d0c3;
      border-top: 5px solid var(--gold);
      break-inside: avoid;
    }}
    .card.victim {{ border-top-color: var(--accent); }}
    .card header {{ display: flex; justify-content: space-between; gap: 10px; align-items: baseline; margin-bottom: 10px; }}
    h2 {{ font-size: 18px; margin: 0; letter-spacing: 0; }}
    .card p {{ margin: 0; color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }}
    ol {{ display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }}
    li {{ font-size: 14px; line-height: 1.35; }}
    li small {{ display: inline-block; margin: 0 7px 3px 0; padding: 2px 6px; border: 1px solid #d8d0c3; color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; }}
    @media (max-width: 860px) {{
      .sheet {{ margin: 0; padding: 16px; }}
      .titlebar, .layout {{ grid-template-columns: 1fr; }}
      .board-wrap {{ position: static; }}
      main {{ grid-template-columns: 1fr; }}
      td {{ padding: 4px; }}
      td > span {{ font-size: 8px; }}
    }}
    @media print {{
      body {{ background: white; }}
      .sheet {{ margin: 0; padding: 12mm; border: 0; box-shadow: none; max-width: none; }}
      .layout {{ grid-template-columns: 0.95fr 1.05fr; gap: 14px; }}
      .board-wrap {{ position: static; }}
      .card {{ min-height: auto; }}
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <header class="titlebar">
      <div>
        <h1>{html.escape(board.get('name') or puzzle['id'])}</h1>
        <p class="subtitle">Caso imprimible para resolver: tablero, objetos y tarjetas de testimonio.</p>
      </div>
      <div class="case-id">{html.escape(puzzle['id'])}</div>
    </header>
    <div class="layout">
      <aside class="board-wrap">
        <table aria-label="Tablero" style="--cols: {int(board['columns'])}">{''.join(rows)}</table>
        <ul class="legend">{legend}</ul>
      </aside>
      <main>{''.join(cards)}</main>
    </div>
  </div>
</body>
</html>
"""


def render_file(puzzle_path: Path, output: Path) -> None:
    puzzle = json.loads(puzzle_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(puzzle), encoding="utf-8")
