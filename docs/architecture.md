# Arquitectura

## Flujo

```text
board.json
   ↓ validación estructural
asignaciones base fila/columna
   ↓ regla de la víctima
objetivos candidatos
   ↓ catálogo formal de pistas verdaderas
máscaras lógicas cacheadas
   ↓ selector global de tarjetas
contrato de aceptación
   ↓
puzzle.json + solution.json + diagnostics.json
   ↓
validador independiente + solucionador deductivo
```

## Separación de responsabilidades

- `clue_catalog.py`: contrato lógico de los tipos de pista.
- `selector.py`: búsqueda de conjuntos completos de tarjetas.
- `engine.py`: orquestación, generación y diagnósticos.
- `validator.py`: segundo solucionador, deliberadamente separado.
- `human_solver.py`: propagación deductiva y dificultad provisional.
- `benchmark.py`: ejecución masiva y estadísticas.

## Selector global

Primero busca una combinación completa con una afirmación por sospechoso mediante DFS global. No confirma una pista antes de comprobar que el resto de tarjetas puede completar el conjunto.

Cuando las tarjetas simples no bastan, construye opciones de tarjeta doble y realiza una búsqueda por haz sobre tarjetas completas. Las dos afirmaciones compiten como una sola opción editorial y se comprueba después que ambas sean necesarias.
