# Informe V2-beta: backtracking y arquitectura multi-solver

## Resultado

La V2-beta sustituye la validación exhaustiva como motor principal por un CSP de backtracking, sin eliminar el solucionador anterior. Cada puzle generado se valida ahora de dos formas independientes:

1. universo vectorizado NumPy usado durante la generación 6×6;
2. backtracking exacto construido desde `puzzle.json`.

Los cinco casos de referencia también se cruzaron con el solucionador exhaustivo estándar.

## Comparación en cinco casos reales 6×6

| Escenario | Backtracking | Exhaustivo | Aceleración |
|---|---:|---:|---:|
| Campamento | 2,591 ms | 1.831,957 ms | 707,0× |
| Hotel | 2,070 ms | 1.759,535 ms | 849,9× |
| Mansión | 1,797 ms | 881,518 ms | 490,4× |
| Restaurante | 3,959 ms | 1.258,067 ms | 317,8× |
| Dos casas | 5,022 ms | 1.004,563 ms | 200,0× |

Las dos implementaciones encontraron la misma solución única en los cinco casos. La aceleración media observada fue de aproximadamente **513×**.

## Benchmark de generación

Se generaron 25 casos, cinco por cada tablero manual:

- 25/25 generados;
- 25/25 con solución única según backtracking;
- 25/25 coinciden con la solución generada;
- tiempo medio de validación backtracking: 4,398 ms;
- máximo: 11,858 ms.

## Escalabilidad del solucionador

Benchmark sintético determinista, tres repeticiones:

| Tamaño | Tiempo medio | Solución única |
|---|---:|---:|
| 6×6 | 3,446 ms | Sí |
| 8×8 | 18,314 ms | Sí |
| 10×10 | 72,482 ms | Sí |
| 12×12 | 224,225 ms | Sí |

Este benchmark demuestra que el **solucionador** acepta más personajes. No demuestra todavía que el generador editorial pueda producir buenos casos 12×12: la selección de pistas continúa basada en máscaras exhaustivas 6×6.

## Librerías introducidas

- **Pydantic v2**: contrato JSON tipado y validación estructural.
- **NetworkX**: grafo de restricciones y desempate por grado.
- **Rich**: inspección de motores desde CLI.
- **Z3 / OR-Tools**: declarados como extras opcionales; la codificación completa queda pendiente y no se finge que esté validada.

## Algoritmo de backtracking

- dominios iniciales reducidos con pistas unarias;
- una fila y una columna distintas por personaje;
- MRV;
- desempate por grado del grafo;
- forward checking de relaciones binarias;
- LCV;
- cotas parciales de ocupación y composición de habitaciones;
- poda cuando las filas o columnas disponibles no bastan;
- parada en la segunda solución para comprobar unicidad.

## Pruebas

`10 passed`.

Incluyen:

- generación en los cinco tableros;
- igualdad backtracking/exhaustivo;
- escalado hasta 12 personajes;
- validación Pydantic;
- tarjetas dobles necesarias;
- fallo explícito de integraciones opcionales no instaladas.

## Próximo hito

Convertir el selector global de tarjetas en una búsqueda incremental que consulte el backtracking, en lugar de necesitar enumerar todas las soluciones. Ese cambio es el que permitirá que el **generador completo**, y no solo el solucionador, pase a 8×8 y 10×10.
