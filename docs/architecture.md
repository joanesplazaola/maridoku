# Arquitectura V2-alpha

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

## Grafo de dependencias

Se añade una arista `A → B` cuando la ganancia de información de B aumenta al haber aplicado previamente A. Se registra:

- orden determinista de aplicación;
- fuerza de la dependencia en bits;
- profundidad máxima;
- número de tarjetas dependientes.

Es una métrica estructural estable, no una afirmación de que modele perfectamente a una persona.
