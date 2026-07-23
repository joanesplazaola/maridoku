$ErrorActionPreference = "Stop"
uv sync --extra dev
uv run murdoku-v2 solvers
uv run pytest -q
