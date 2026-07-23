# Murdoku V2-gamma — backend Google OR-Tools CP-SAT

## Estado de la entrega

Se ha implementado el backend CP-SAT y el banco de comparación, pero **el binario de OR-Tools no pudo instalarse en este entorno de ejecución**. El índice de paquetes disponible devolvió que no había ninguna distribución accesible para `ortools==9.15.6755`, y las descargas binarias externas están bloqueadas.

Por tanto:

- La implementación CP-SAT está escrita y compila.
- El contrato y los diez tests no dependientes de OR-Tools pasan.
- Los seis tests que ejecutan CP-SAT se omiten automáticamente cuando la dependencia no está disponible.
- El benchmark se ejecutó, pero devolvió un resultado `blocked`; **no se han inventado tiempos de CP-SAT**.

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

`benchmarks_cpsat_compare.py` compara CP-SAT con el backtracking sobre los cinco escenarios reales y registra por separado:

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
10 passed, 6 skipped
```

Los seis tests omitidos son exclusivamente los que necesitan importar el binario de OR-Tools.

También se verificó que todos los módulos compilan mediante `compileall`.

## Cómo ejecutar la prueba real

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[solvers,dev]'
PYTHONPATH=src pytest -q
PYTHONPATH=src python benchmarks_cpsat_compare.py --repeats 20 --output cpsat_benchmark
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
