# Modelo espacial de objetos

## Huella

Cada objeto declara todas las casillas que ocupa:

```json
{
  "id": "bed-ab",
  "type": "bed",
  "cells": [[0, 5], [1, 5]],
  "occupiable": true,
  "blocks_character": false
}
```

La primera casilla se conserva también como `row`/`column` al cargar el tablero para compatibilidad con herramientas antiguas, pero la lógica V2-alpha usa siempre `cells`.

## Capas

- `floor`: elementos de suelo, actualmente alfombras.
- `furniture`: camas, sillas, sofás, mesas, televisiones y plantas.

## Superposiciones

Matriz actual:

| Objeto A | Objeto B | Permitido |
|---|---|---|
| Alfombra | Silla | Sí |
| Cualquier otra pareja | — | No |

El cargador rechaza el tablero antes de generar el puzle si encuentra una combinación inválida.

## Posición de personajes

- `blocks_character: true`: ningún personaje puede ocupar esas casillas.
- `occupiable: true`: la huella puede producir pistas como «era la única persona en una cama».

En el tablero actual:

- ocupables: silla, cama, sofá y alfombra;
- bloqueantes: mesa, televisión y planta.

## Pistas multicasilla

- `unique_on_object`: usa la unión de todas las casillas de todos los objetos del tipo.
- `object_same_row_in_room`: basta con compartir fila con cualquiera de sus casillas, dentro de la misma habitación.
- `object_same_column_in_room`: equivalente para columnas.
- `adjacent_object`: se calcula respecto a todo el perímetro ortogonal de la huella.

## Rótulos

Cada habitación declara una casilla `label_anchor`. Debe:

1. pertenecer a la habitación;
2. no coincidir con ninguna casilla ocupada por objetos.

La validación falla si alguna de estas condiciones no se cumple.
