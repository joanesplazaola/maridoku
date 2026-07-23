# Arquitectura multi-solver

## Backtracking

Motor exacto principal. Mantiene un dominio de casillas por personaje y usa:

- MRV: selecciona el personaje con menos posiciones posibles.
- Degree heuristic: desempata usando el grafo de restricciones de NetworkX.
- Forward checking: exige soporte para las relaciones binarias.
- LCV: prueba primero la posición que menos opciones elimina a los demás.
- Poda por filas y columnas disponibles.
- Cotas inferiores y superiores para población y género en habitaciones.
- Parada al encontrar dos soluciones cuando solo se comprueba unicidad.

## Exhaustivo

Oráculo independiente, conservado únicamente para 6×6. Recorre las permutaciones de filas y columnas y permite detectar regresiones en el motor nuevo.

## Pydantic

El `PuzzleModel` valida antes de resolver:

- tablero cuadrado;
- una tarjeta por personaje;
- una o dos afirmaciones por tarjeta;
- afirmaciones centradas en el propietario de la tarjeta;
- geometría y objetos dentro del tablero.

## NetworkX

El grafo de restricciones conecta personajes relacionados por pistas. Su grado interviene en el orden de búsqueda y queda disponible para diagnósticos posteriores.

## Z3 y OR-Tools

Se mantienen como extras opcionales en `pyproject.toml`. No se presentan como motores funcionales todavía: activar una codificación incompleta sería peor que declarar honestamente que queda pendiente.
