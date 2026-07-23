# Murdoku V2-gamma — backend Google OR-Tools CP-SAT

## Estado de la entrega

Se ha implementado el backend CP-SAT y OR-Tools queda como motor exacto
principal del proyecto.

Por tanto:

- La implementación CP-SAT está escrita y compila.
- OR-Tools se instala por defecto desde `pyproject.toml`.
- El oráculo exhaustivo se conserva para contrastes 6×6.
- El solver artesanal anterior se retiró.

## Implementación

Archivo principal:

`src/murdoku_v2/solvers/ortools_solver.py`

El modelo utiliza para cada personaje:

- variable de casilla;
- variable de fila;
- variable de columna;
- variable de habitación.

Restricciones base:

- dominio formado únicamente por casillas transitables;
- relación casilla–fila mediante división entera;
- relación casilla–columna mediante módulo;
- relación casilla–habitación mediante `Element`;
- `AllDifferent` para todas las filas;
- `AllDifferent` para todas las columnas.

Se han compilado los 22 tipos de pista actuales, incluida la regla de la víctima, conteos de habitación y género, objetos multicasilla, esquinas, paredes, alternativas de habitación y relaciones espaciales.

## Comprobación de unicidad

El backend:

1. Resuelve el modelo para obtener una primera distribución.
2. Añade una restricción *no-good* que prohíbe exactamente esa distribución.
3. Vuelve a resolver.
4. Si no encuentra una segunda distribución, considera la solución única.

La búsqueda se configura de forma reproducible con:

- un solo trabajador;
- semilla tomada del puzle;
- búsqueda aleatoria desactivada.

## Banco de comparación

`murdoku-v2 benchmark-solvers` compara CP-SAT con el oráculo exhaustivo sobre
los cinco escenarios 6×6 y registra por separado:

- construcción del modelo;
- primera solución;
- comprobación de unicidad;
- tiempo total;
- número de variables y restricciones;
- ramas y conflictos;
- igualdad exacta del conjunto de soluciones.

## Pruebas ejecutadas

Resultado en este entorno:

```text
16 passed
```

## Cómo ejecutar la prueba real

```bash
uv sync --extra dev
uv run pytest -q
uv run murdoku-v2 benchmark-solvers --puzzles examples --solvers ortools exhaustive
uv run murdoku-v2 scale-benchmark --sizes 6 8 10 12 --solver ortools
```

Resultados esperados:

```text
cpsat_benchmark/solver_comparison.json
cpsat_benchmark/solver_comparison.csv
```

## Dependencia fijada

```toml
ortools==9.15.6755
```

La versión se fija para que los benchmarks y los resultados de búsqueda sean comparables entre ejecuciones.
