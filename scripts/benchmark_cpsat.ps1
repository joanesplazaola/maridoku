param(
    [int]$Repeats = 20,
    [string]$Output = "cpsat_benchmark_local"
)
$ErrorActionPreference = "Stop"
uv run python benchmarks_cpsat_compare.py --repeats $Repeats --output $Output
