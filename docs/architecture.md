# Arquitectura

## Flujo

```text
board.json + case.json + seed
        ↓ permutación válida
 solución candidata
        ↓ candidate_pools(puzle, solución candidata)
 candidatos verdaderos
        ↓ select_clues()
 selección única, necesaria y editorial
        ↓ solve_human()
 ruta deductiva completa
        ↓ generate_variant()
 solución privada + puzle público
        ↓
validación Pydantic + CP-SAT
        ↓
HTML sin solution.json
```

## Separación de responsabilidades

- `boards/*.json`: geometría, habitaciones y objetos de una escena fija.
- `examples/*/case.json`: personajes, víctima y pistas; referencia una escena.
- `examples/*/solution.json`: posiciones y asesino privados.
- `models.py`: composición y validación del contrato público.
- `candidates.py`: pistas verdaderas derivadas de una solución sobre una escena fija.
- `selection.py`: selección incremental mediante contraejemplos del oráculo exacto.
- `generation.py`: objetivos por seed y ensamblado de variantes aceptadas.
- `human.py`: propagación y métricas de técnicas humanas, todavía sin calibración comercial.
- `clue_catalog.py`: contrato lógico de los tipos de pista.
- `solvers/ortools_solver.py`: solución exacta, unicidad y necesidad.
- `render.py`: documento público autocontenido.
- `scaling.py`: benchmark sintético; no produce contenido publicable.
