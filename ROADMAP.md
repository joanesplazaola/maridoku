# Roadmap

## Estado actual

- CP-SAT (`ortools`) es el motor exacto principal.
- El antiguo solver artesanal se retiró en Git.
- El generador CP-SAT escalable escribe casos 8x8+ seed-dependientes con `generate-scale`, varias habitaciones, objetos visibles y pistas de objetos/habitación aceptadas solo si conservan la unicidad.
- CP-SAT acepta `base_statements`, `extra_statements`, `probe_candidate_with_cpsat()` y `probe_candidates_with_cpsat()` para evaluar pistas candidatas sin crear tarjetas definitivas.
- El generador editorial registra una muestra CP-SAT vs NumPy de candidatos supervivientes en diagnostics.
- El set de tarjetas elegido se valida con CP-SAT antes de aceptar un caso.
- La CLI renderiza puzzles a una hoja HTML imprimible para pruebas humanas.
- El selector editorial estable está separado en `selector.py` y usa máscaras bitset con `int.bit_count()` para elegir sets completos de tarjetas.
- Existe una ruta experimental `--cpsat-selector` basada en conteos CP-SAT capados a 2; reporta `solve_calls`/`cache_hits` y cae al selector estable cuando no encuentra set.

## Gaps principales

1. Generación editorial limitada a 6 personajes.
   `engine.py` usa `CHARACTERS` fijo y exige `rows == len(CHARACTERS)`.

2. Selector basado en universo enumerado.
   La selección por máscaras ya es rápida para 6x6, pero `enumerate_base_solutions()` aún crea `(n!)^2` asignaciones y las máscaras dependen de ese universo. Esto bloquea 8x8+ aunque CP-SAT ya resuelva esos tamaños.

3. Solver humano enumerativo.
   `human_solver.py` reutiliza `enumerate_base_solutions()`, así que la explicación/dificultad tampoco escala.

4. Tests deben cubrir propiedades, no enumeración.
   La suite normal debe seguir barata: unicidad, solución esperada, exclusiones y escalado sintético.

5. Fixtures actuales regenerados.
   `examples/` y `generated/` usan `exact_validation` y diagnostics CP-SAT; los informes V2-alpha/beta quedan como historia.

6. Variedad editorial grande aún limitada.
   El 8x8+ ya mezcla pistas espaciales, de habitación y de objetos, pero conserva parte de la cadena de distancias como garantía. Falta seleccionar el conjunto completo con CP-SAT y medir dificultad humana.

## Próximos pasos

1. Parametrizar personajes.
   Cargar personajes desde tablero/perfil o generar N personajes por tamaño. Quitar la regla `rows == len(CHARACTERS)`.

2. Reemplazar máscaras globales por consultas CP-SAT.
   Para cada pista candidata o conjunto de pistas: añadirlas al modelo base y preguntar si conserva la solución objetivo y cuántas alternativas deja, con límite 2. Los probes ya existen y el generador ya registra una muestra comparativa; falta reemplazar el filtro completo.

3. Rehacer el selector sobre conteos CP-SAT.
   Optimizar/cachear `--cpsat-selector` hasta hacerlo default. La aceptación del set completo ya está en CP-SAT; la búsqueda parcial ya existe experimentalmente y evita shortlists de una sola familia, pero todavía puede quedarse en sets no únicos y caer al selector de máscara estable.

4. Separar explicación humana de generación grande.
   Mantener explicación completa para 6x6; para 8x8+ devolver diagnóstico estructural hasta que haya propagador no enumerativo.

5. Medir casos reales grandes.
   Añadir benchmarks de generación 8x8, 10x10 y 13x13 con tableros editoriales ricos cuando el selector CP-SAT sustituya las máscaras.

6. Preparar paquete de prueba.
   Mantener `scripts/bootstrap.*` como smoke reproducible: sync, tests, generación editorial, HTML imprimible y generación 13x13.
