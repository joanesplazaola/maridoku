$ErrorActionPreference = "Stop"
uv sync --extra dev
uv run murdoku-v2 solvers
uv run pytest -q
uv run murdoku-v2 generate --board boards/board_restaurant.json --seed 6201 --output generated
uv run murdoku-v2 render --puzzle generated/puzzle.json --output generated/puzzle.html
uv run murdoku-v2 generate-scale --size 13 --seed 6201 --output generated_scale_reference
