# Murdoku

Repositorio local del motor de generación y validación de puzles Murdoku.
Esta rama usa **Google OR-Tools CP-SAT** como motor exacto principal.

La web publica 15 casos revisados generados sobre escenas fijas. Cada caso
separa la escena de la solución y usa objetos, habitaciones y relaciones
espaciales como evidencia.

## Contenido

- `ORToolsSolver`: modelo exacto CP-SAT para el catálogo formal de pistas.
- Tres escenas fijas y un catálogo versionado de variantes revisadas.
- Benchmark de construcción del modelo, primera solución y unicidad.

## Requisitos

- Python 3.11 o superior.
- Recomendado: [`uv`](https://docs.astral.sh/uv/).

## Instalación rápida con uv

```bash
uv sync --extra dev
```

Con `venv` y `pip`:

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\\Scripts\\activate       # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Primera comprobación

```bash
uv run murdoku-v2 solvers
uv run pytest -q
```

Con OR-Tools instalado debe pasar la suite completa.

Smoke completo:

```bash
./scripts/bootstrap.sh
```

## Benchmark de escalado CP-SAT

```bash
uv run murdoku-v2 scale-benchmark --sizes 5 8 12 16 --solver ortools --repetitions 2
```

El benchmark es sintético y solo mide el motor. El workflow manual
`Release generation gate` valida el catálogo y ejecuta QA visual cruzada.

## Validar un caso con CP-SAT

```bash
uv run murdoku-v2 validate \
  --puzzle examples/board_restaurant/case.json \
  --solution examples/board_restaurant/solution.json \
  --solver ortools
```

## Generar una variante sobre una escena fija

```bash
uv run murdoku-v2 generate \
  --case examples/board_restaurant/case.json \
  --seed 6201 \
  --output generated_local
```

La geometría y el mobiliario proceden siempre del caso de entrada; el generador
elige la solución y las pistas.

Para generar una hoja HTML imprimible:

```bash
uv run murdoku-v2 render --puzzle generated/puzzle.json --output generated/puzzle.html
```

## Construir la web

```bash
uv run murdoku-v2 build-site --output _site
```

## Estado de producto

El catálogo publica 15 casos revisados sobre tres escenas fijas. Las etiquetas
actuales son estimaciones técnicas; `docs/playtest.md` define la calibración
ciega pendiente con personas.

Consulta `LOCAL_SETUP.md` para una secuencia detallada de ejecución y resolución
de problemas.
