$ErrorActionPreference = "Stop"
uv sync --extra cpsat --extra dev
uv run murdoku-v2 solvers
uv run pytest -q
