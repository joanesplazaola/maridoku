# Motor exacto

## OR-Tools CP-SAT

Motor exacto principal. Codifica filas, columnas, habitaciones y pistas públicas
como restricciones CP-SAT y hace una segunda consulta para comprobar unicidad.

Las regresiones comparan CP-SAT con fixtures de solución versionados y con
auditorías de unicidad y necesidad por seed. La ruta exhaustiva anterior fue
retirada.

## Pydantic

El `PuzzleModel` valida antes de resolver:

- tablero cuadrado;
- una tarjeta por personaje;
- una o dos afirmaciones por tarjeta;
- afirmaciones centradas en el propietario de la tarjeta;
- geometría y objetos dentro del tablero.
