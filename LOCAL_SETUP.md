# Ejecución local de CP-SAT

## 1. Preparar el entorno

### Opción recomendada: uv

```bash
uv sync --extra cpsat --extra dev
```

### Opción alternativa: pip

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[cpsat,dev]'
```

En Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[cpsat,dev]"
```

## 2. Confirmar que OR-Tools está disponible

```bash
uv run python -c "import ortools; print(ortools.__version__)"
uv run murdoku-v2 solvers
```

La fila `ortools` debe indicar `sí`.

## 3. Ejecutar pruebas

```bash
uv run pytest -q
```

Resultado esperado con OR-Tools instalado:

```text
16 passed
```

Las pruebas CP-SAT validan:

- Coincidencia exacta con backtracking en cinco escenarios.
- Exclusión de cada tarjeta.
- Exclusión de cada afirmación individual.
- Unicidad mediante una segunda búsqueda que prohíbe la primera solución.

## 4. Ejecutar el benchmark principal

```bash
uv run python benchmarks_cpsat_compare.py \
  --repeats 50 \
  --output cpsat_benchmark_local
```

Para una prueba rápida:

```bash
uv run python benchmarks_cpsat_compare.py \
  --repeats 5 \
  --output cpsat_benchmark_smoke
```

## 5. Datos que conviene compartir

Los dos archivos generados:

```text
cpsat_benchmark_local/cpsat_vs_backtracking.json
cpsat_benchmark_local/cpsat_vs_backtracking.csv
```

El JSON separa:

- tiempo total;
- construcción del modelo;
- primera solución;
- segunda consulta de unicidad;
- variables y restricciones;
- ramas y conflictos;
- versión exacta de OR-Tools.

## 6. Reproducibilidad

El backend usa:

```text
num_search_workers = 1
randomize_search = false
random_seed = puzzle.seed
```

Esto prioriza comparaciones deterministas. Más adelante se podrá añadir un
benchmark separado con varios trabajadores para medir rendimiento máximo.

## 7. Errores frecuentes

### `OR-Tools no está instalado`

```bash
uv sync --extra cpsat --extra dev
```

O:

```bash
python -m pip install 'ortools==9.15.6755'
```

### La versión fijada no está disponible para tu Python

Prueba Python 3.11 o 3.12 y vuelve a crear el entorno virtual.

### CP-SAT y backtracking discrepan

Guarda el `puzzle.json`, la versión de OR-Tools y la salida completa de:

```bash
uv run pytest -q tests/test_ortools_solver.py -vv
```

No uses ese backend como motor principal hasta resolver la discrepancia.
