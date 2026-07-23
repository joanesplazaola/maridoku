# Arquitectura multi-solver

## OR-Tools CP-SAT

Motor exacto principal. Codifica filas, columnas, habitaciones y pistas públicas
como restricciones CP-SAT y hace una segunda consulta para comprobar unicidad.

## Exhaustivo

Oráculo independiente, conservado únicamente para 6×6. Recorre las permutaciones de filas y columnas y permite detectar regresiones en el motor nuevo.

## Pydantic

El `PuzzleModel` valida antes de resolver:

- tablero cuadrado;
- una tarjeta por personaje;
- una o dos afirmaciones por tarjeta;
- afirmaciones centradas en el propietario de la tarjeta;
- geometría y objetos dentro del tablero.

## Z3

Se mantiene como adaptador experimental opcional.
