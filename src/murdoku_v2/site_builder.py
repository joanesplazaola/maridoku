from __future__ import annotations

import html
import json
from pathlib import Path

from .render import _stylesheet, render_html


REFERENCE_CASES = (
    {
        "number": 1,
        "difficulty": "easy",
        "difficulty_label": "Fácil",
        "path": Path("examples/board_restaurant/puzzle.json"),
    },
)


def _catalog_html(levels: list[dict[str, object]]) -> str:
    data = json.dumps(levels, ensure_ascii=False).replace("</", "<\\/")
    buttons = "".join(
        f'<a class="level" data-difficulty="{level["difficulty"]}" '
        f'data-puzzle="{html.escape(str(level["puzzle_id"]))}" '
        f'href="levels/{int(level["number"]):03d}.html">'
        f'<strong>{int(level["number"]):02d}</strong>'
        f'<b>{html.escape(str(level["title"]))}</b>'
        f'<span>{html.escape(str(level["difficulty_label"]))} · {level["size"]}×{level["size"]}</span></a>'
        for level in levels
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Murdoku</title>
  <style>{_stylesheet()}
  .catalog {{ display:block; max-width:1040px; margin:0 auto; padding:28px; }}
  .catalog-head {{ display:flex; justify-content:space-between; gap:20px; align-items:end; border-bottom:2px solid var(--line); padding-bottom:20px; }}
  .catalog-head h1 {{ font-size:48px; }}
  .progress {{ font:800 13px Inter,sans-serif; color:var(--green); }}
  .difficulty-tabs {{ display:flex; gap:8px; margin:24px 0 18px; }}
  .difficulty-tabs button {{ min-height:40px; padding:0 18px; border:1px solid var(--line); border-radius:4px; background:#fffef9; font-weight:800; cursor:pointer; }}
  .difficulty-tabs button.active {{ background:var(--green); color:white; }}
  .levels {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; }}
  .level {{ min-height:92px; padding:14px; border:1px solid rgb(41 44 39 / 24%); background:rgb(255 254 249 / 90%); color:var(--ink); text-decoration:none; box-shadow:0 3px 8px rgb(35 37 32 / 7%); }}
  .level:hover,.level:focus-visible {{ outline:3px solid var(--green); outline-offset:1px; }}
  .level strong {{ display:block; font:700 30px Georgia,serif; }}
  .level b {{ display:block; margin-top:5px; font:700 15px Georgia,serif; }}
  .level span {{ display:block; margin-top:7px; color:var(--muted); font-size:11px; font-weight:800; }}
  .level.completed {{ border-color:var(--green); background:#e4eee8; }}
  .level.completed strong::after {{ content:" ✓"; color:var(--green); font-size:16px; }}
  @media(max-width:700px) {{ .catalog {{ padding:20px 14px; }} .catalog-head {{ align-items:start; flex-direction:column; }} .catalog-head h1 {{ font-size:40px; }} .levels {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
  </style>
</head>
<body>
  <main class="catalog">
    <header class="catalog-head"><div><span class="eyebrow">Casos disponibles</span><h1>Murdoku</h1></div><output class="progress"></output></header>
    <nav class="difficulty-tabs" aria-label="Dificultad">
      <button class="active" data-filter="all">Todos</button>
      <button data-filter="easy">Fácil</button>
      <button data-filter="medium">Medio</button>
      <button data-filter="hard">Difícil</button>
    </nav>
    <section class="levels" aria-label="Tableros">{buttons}</section>
  </main>
  <script type="application/json" id="catalog-data">{data}</script>
  <script>
  (() => {{
    const levels = JSON.parse(document.querySelector("#catalog-data").textContent);
    const completed = new Set();
    for (let index = 0; index < localStorage.length; index += 1) {{
      const key = localStorage.key(index);
      if (!key.endsWith(":metrics")) continue;
      try {{
        const metrics = JSON.parse(localStorage.getItem(key));
        if (metrics.completedAt) completed.add(key.split(":")[1]);
      }} catch {{}}
    }}
    document.querySelectorAll(".level").forEach((level) => level.classList.toggle("completed", completed.has(level.dataset.puzzle)));
    document.querySelector(".progress").value = `${{completed.size}} / ${{levels.length}} resueltos`;
    document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {{
      document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".level").forEach((level) => {{
        level.hidden = button.dataset.filter !== "all" && level.dataset.difficulty !== button.dataset.filter;
      }});
    }}));
  }})();
  </script>
</body>
</html>"""


def build_site(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    levels_dir = output / "levels"
    levels_dir.mkdir(exist_ok=True)
    catalog = []
    project = Path(__file__).resolve().parents[2]
    for index, spec in enumerate(REFERENCE_CASES):
        puzzle = json.loads((project / spec["path"]).read_text(encoding="utf-8"))
        level = {
            **{key: value for key, value in spec.items() if key != "path"},
            "puzzle_id": puzzle["id"],
            "title": puzzle.get("title", puzzle["board"]["name"]),
            "size": puzzle["board"]["rows"],
        }
        catalog.append(level)
        navigation = {
            "number": spec["number"],
            "previous": f"{int(spec['number']) - 1:03d}.html" if index else None,
            "next": f"{int(spec['number']) + 1:03d}.html" if index + 1 < len(REFERENCE_CASES) else None,
        }
        (levels_dir / f"{int(spec['number']):03d}.html").write_text(
            render_html(puzzle, navigation=navigation), encoding="utf-8"
        )
    (output / "index.html").write_text(_catalog_html(catalog), encoding="utf-8")
    (output / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / ".nojekyll").touch()
    return {"levels": len(catalog), "output": str(output)}
