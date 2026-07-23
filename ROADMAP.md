# Roadmap

## Estado actual

- CP-SAT (`ortools`) es el motor exacto principal.
- El antiguo solver artesanal se retiró en Git.
- El generador sintético CP-SAT escribe casos 10x10+ con `generate-scale`.
- CP-SAT acepta `base_statements`, `extra_statements` y `probe_candidate_with_cpsat()` para evaluar pistas candidatas sin crear tarjetas definitivas.

## Gaps principales

1. Generación editorial limitada a 6 personajes.
   `engine.py` usa `CHARACTERS` fijo y exige `rows == len(CHARACTERS)`.

2. Selector basado en universo enumerado.
   `enumerate_base_solutions()` crea `(n!)^2` asignaciones y las máscaras NumPy dependen de ese universo. Esto bloquea 8x8+ aunque CP-SAT ya resuelva esos tamaños.

3. Solver humano enumerativo.
   `human_solver.py` reutiliza `enumerate_base_solutions()`, así que la explicación/dificultad tampoco escala.

4. Tests deben cubrir propiedades, no enumeración.
   La suite normal debe seguir barata: unicidad, solución esperada, exclusiones y escalado sintético.

5. Datos históricos con nombres legacy.
   Los JSON generados antiguos aún contienen campos `backtracking_*`. No rompen ejecución, pero confunden reportes.

## Próximos pasos

1. Parametrizar personajes.
   Cargar personajes desde tablero/perfil o generar N personajes por tamaño. Quitar la regla `rows == len(CHARACTERS)`.

2. Reemplazar máscaras globales por consultas CP-SAT.
   Para cada pista candidata: añadir la pista al modelo base y preguntar si conserva la solución objetivo y cuántas alternativas deja, con límite 2. El probe ya existe y funciona con conjuntos explícitos de statements; falta conectarlo al selector.

3. Rehacer el selector sobre conteos CP-SAT.
   Mantener el beam search existente, pero cambiar su señal de `mask bitset` a `solution_count <= 2` y `target still valid`.

4. Separar explicación humana de generación grande.
   Mantener explicación completa para 6x6; para 8x8+ devolver diagnóstico estructural hasta que haya propagador no enumerativo.

5. Medir casos reales grandes.
   Añadir benchmarks de generación 8x8, 10x10 y 13x13 cuando el selector CP-SAT sustituya las máscaras.

6. Regenerar fixtures.
   Crear ejemplos frescos con `exact_validation` y borrar campos históricos `backtracking_*` de salidas versionadas.
