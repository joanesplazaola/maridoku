# Roadmap

## Estado actual

- CP-SAT (`ortools`) es el motor exacto principal.
- `exhaustive` queda solo como oráculo 6x6.
- El antiguo solver artesanal se retiró en Git.
- El generador sintético CP-SAT escribe casos 10x10+ con `generate-scale`.

## Gaps principales

1. Generación editorial limitada a 6 personajes.
   `engine.py` usa `CHARACTERS` fijo y exige `rows == len(CHARACTERS)`.

2. Selector basado en universo enumerado.
   `enumerate_base_solutions()` crea `(n!)^2` asignaciones y las máscaras NumPy dependen de ese universo. Esto bloquea 8x8+ aunque CP-SAT ya resuelva esos tamaños.

3. Solver humano enumerativo.
   `human_solver.py` reutiliza `enumerate_base_solutions()`, así que la explicación/dificultad tampoco escala.

4. Tests de paridad lentos.
   Al borrar backtracking, la comparación masiva usa `exhaustive`; sirve como oráculo, pero la suite tarda unos 2 minutos.

5. Datos históricos con nombres legacy.
   Los JSON generados antiguos aún contienen campos `backtracking_*`. No rompen ejecución, pero confunden reportes.

## Próximos pasos

1. Parametrizar personajes.
   Cargar personajes desde tablero/perfil o generar N personajes por tamaño. Quitar la regla `rows == len(CHARACTERS)`.

2. Reemplazar máscaras globales por consultas CP-SAT.
   Para cada pista candidata: añadir la pista al modelo base y preguntar si conserva la solución objetivo y cuántas alternativas deja, con límite 2.

3. Rehacer el selector sobre conteos CP-SAT.
   Mantener el beam search existente, pero cambiar su señal de `mask bitset` a `solution_count <= 2` y `target still valid`.

4. Separar explicación humana de generación grande.
   Mantener explicación completa para 6x6; para 8x8+ devolver diagnóstico estructural hasta que haya propagador no enumerativo.

5. Acelerar tests.
   Mantener una prueba exhaustiva 6x6 completa y convertir exclusiones masivas en un fixture pequeño o marcado como benchmark.

6. Regenerar fixtures.
   Crear ejemplos frescos con `exact_validation` y borrar campos históricos `backtracking_*` de salidas versionadas.
