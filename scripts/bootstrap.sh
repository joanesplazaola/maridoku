#!/usr/bin/env bash
set -euo pipefail
uv sync --extra dev
uv run murdoku-v2 solvers
uv run pytest -q
uv run murdoku-v2 generate --case examples/board_restaurant/case.json --seed 6201 --output generated_reference
uv run murdoku-v2 render --puzzle generated_reference/puzzle.json --output generated_reference/puzzle.html
