# Murdoku V2-gamma — CP-SAT

Repositorio local del motor de generación y validación de puzles Murdoku.
Esta rama usa **Google OR-Tools CP-SAT** como motor exacto principal y conserva
el exhaustivo solo como oráculo de referencia 6×6.

## Contenido

- `ORToolsSolver`: modelo exacto CP-SAT para las 22 familias de pistas actuales.
- `ExhaustiveSolver`: oráculo independiente para 6×6.
- `Z3Solver`: punto de integración experimental.
- Cinco tableros manuales y casos ya generados.
- Pruebas cruzadas entre CP-SAT y el oráculo exhaustivo.
- Benchmark de construcción del modelo, primera solución y unicidad.

## Requisitos

- Python 3.11 o superior.
- Recomendado: [`uv`](https://docs.astral.sh/uv/).

## Instalación rápida con uv

```bash
uv sync --extra dev
```

Para instalar también Z3:

```bash
uv sync --extra solvers --extra dev
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

Con OR-Tools instalado deben ejecutarse **16 pruebas**: 10 generales y 6 de
CP-SAT. Sin OR-Tools, las 6 pruebas del backend se omiten.

## Benchmark de escalado CP-SAT

```bash
uv run murdoku-v2 scale-benchmark --sizes 6 8 10 12 --solver ortools --repetitions 3
```

## Validar un caso con CP-SAT

```bash
uv run murdoku-v2 validate \
  --puzzle examples/board_restaurant/puzzle.json \
  --solution examples/board_restaurant/solution.json \
  --solver ortools
```

Comparar motores desde la CLI:

```bash
uv run murdoku-v2 benchmark-solvers \
  --puzzles examples \
  --solvers ortools exhaustive \
  --output solver_comparison_local.json
```

## Generar un caso

El generador completo continúa usando temporalmente el selector exhaustivo de
6×6. La validación final sí puede ejecutarse con CP-SAT.

```bash
uv run murdoku-v2 generate \
  --board boards/board_restaurant.json \
  --seed 6201 \
  --output generated_local
```

Para generar un caso escalable sintético validado con CP-SAT:

```bash
uv run murdoku-v2 generate-scale --size 10 --seed 6201 --output generated_scale
```

## Objetivo inmediato

La siguiente fase es sustituir el universo exhaustivo y las máscaras NumPy por
consultas CP-SAT incrementales:

```text
solución objetivo
→ pistas verdaderas
→ combinación de tarjetas
→ CP-SAT busca 0, 1 o 2 soluciones
→ aceptar, modificar o rechazar
```

Así el generador completo podrá pasar de 6×6 a 8×8, 10×10 y 13×13 sin enumerar
previamente `(n!)²` distribuciones.

Consulta `LOCAL_SETUP.md` para una secuencia detallada de ejecución y resolución
de problemas.
