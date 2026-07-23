#!/usr/bin/env bash
set -euo pipefail
REPEATS="${1:-20}"
OUTPUT="${2:-cpsat_benchmark_local}"
uv run python benchmarks_cpsat_compare.py --repeats "$REPEATS" --output "$OUTPUT"
