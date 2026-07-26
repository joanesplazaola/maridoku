# Arquitectura

## Flujo

```text
board.json + case.json
        ↓ load_puzzle()
puzle público autocontenido
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
- `clue_catalog.py`: contrato lógico de los tipos de pista.
- `solvers/ortools_solver.py`: solución exacta, unicidad y necesidad.
- `render.py`: documento público autocontenido.
- `scaling.py`: benchmark sintético; no produce contenido publicable.
