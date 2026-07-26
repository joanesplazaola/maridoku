# Murdoku

Repositorio local del motor de generación y validación de puzles Murdoku.
Esta rama usa **Google OR-Tools CP-SAT** como motor exacto principal.

La web publica únicamente casos de referencia revisados. El primero,
**Último servicio**, separa la escena de la solución, identifica a la víctima
y usa objetos y habitaciones como evidencia.

## Contenido

- `ORToolsSolver`: modelo exacto CP-SAT para las 22 familias de pistas actuales.
- Cinco tableros manuales y fixtures de regresión.
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
uv run murdoku-v2 scale-benchmark --sizes 10 13 --solver ortools --repetitions 2
```

Smoke para desarrollo:

```bash
uv run murdoku-v2 scale-regression \
  --sizes 6 8 10 \
  --count-per-size 3 \
  --budget-seconds 30
```

Gate de release:

```bash
uv run murdoku-v2 scale-regression \
  --sizes 6 8 10 \
  --count-per-size 100 \
  --budget-seconds 30
```

El último gate aceptado se conserva en
`docs/regressions/scaling-100-seeds.json`.
El workflow manual `Release generation gate` ejecuta el mismo gate en GitHub y
conserva el informe durante 90 días, sin bloquear el desarrollo local.

## Validar un caso con CP-SAT

```bash
uv run murdoku-v2 validate \
  --puzzle examples/board_restaurant/puzzle.json \
  --solution examples/board_restaurant/solution.json \
  --solver ortools
```

## Generar un caso sintético

Esta ruta mide escalabilidad de CP-SAT. Su salida no se publica como contenido
editorial.

```bash
uv run murdoku-v2 generate \
  --size 8 \
  --seed 6201 \
  --output generated_local
```

`generate-scale` se mantiene como alias compatible:

```bash
uv run murdoku-v2 generate-scale --size 10 --seed 6201 --output generated_scale
```

Para generar una hoja HTML imprimible:

```bash
uv run murdoku-v2 render --puzzle generated/puzzle.json --output generated/puzzle.html
```

## Construir la web

```bash
uv run murdoku-v2 build-site --output _site
```

## Objetivo inmediato

Crear tres casos de referencia sobre escenas fijas y añadir las técnicas
humanas que permitan medir dificultad antes de ampliar el catálogo.

Consulta `LOCAL_SETUP.md` para una secuencia detallada de ejecución y resolución
de problemas.
