# Roadmap de producto

## Estado actual

- [x] CP-SAT es el único motor exacto y valida solución y unicidad.
- [x] Hay generación editorial 6x6 y generación escalable sintética 8x8+.
- [x] El catálogo formal cubre 22 familias de pistas.
- [x] El catálogo visual cubre 11 objetos con huellas `1x1`, `1x2`, `2x2` y `L3`.
- [x] Los tableros, objetos y puzles se validan con Pydantic.
- [x] Existe una hoja HTML autocontenida para revisión editorial.
- [ ] El generador editorial escala más allá de 6 personajes.
- [ ] Existe un jugador interactivo usable.
- [ ] La dificultad está calibrada con personas.
- [ ] Existe un flujo reproducible de publicación y regresión de contenido.

## Dirección técnica

`scaling.py` es la base del futuro generador editorial. La ruta 6x6 de
`engine.py` queda como referencia temporal para comparar calidad y fixtures,
pero no recibirá nuevas funciones.

No volveremos a hacer default un selector CP-SAT que dependa del universo
enumerado o que termine silenciosamente en máscaras. Una nueva etapa solo
sustituirá a la anterior cuando pase sus criterios de salida sin fallback.

Enfoques descartados:

- beam basado únicamente en conteos CP-SAT capados;
- ejecutar primero CP-SAT y repetir después toda la selección por máscaras;
- CEGIS construido sobre los pools y objetivos del generador enumerativo.

## P0: generador escalable

Objetivo: producir 8x8 y 10x10 variados sin enumerar `(n!)²`.

1. [x] Extraer personajes y objetivo parametrizados desde `scaling.py`.
2. [x] Extraer la construcción parametrizada del tablero escalable.
3. [x] Generar pools editoriales verdaderos sin `enumerate_base_solutions()`.
4. [x] Construir pistas y demostrar unicidad exclusivamente mediante CP-SAT.
5. [x] Comprobar necesidad de cada tarjeta y afirmación de sospechoso con CP-SAT.
6. [ ] Sustituir las cadenas sintéticas por familias variadas del catálogo formal.
7. [x] Añadir un gate reproducible de unicidad, necesidad y presupuesto para 6x6, 8x8 y 10x10.
8. [ ] Superar 100 seeds consecutivas por tamaño y conservar fixtures de regresión.
9. [ ] Mover `generate` a la ruta escalable y retirar selector, máscaras y universo antiguos.

Criterio de salida: 100 casos consecutivos por tamaño, todos únicos, sin pistas
redundantes y dentro del presupuesto publicado. Ningún caso aceptado puede
registrar fallback al generador enumerativo.

## P1: jugador web

Objetivo: probar puzles completos sin herramientas de desarrollo.

- [ ] Seleccionar sospechoso y colocarlo, moverlo o retirarlo del tablero.
- [ ] Mostrar restricciones de fila, columna y ocupación mientras se juega.
- [ ] Añadir deshacer, reiniciar, comprobación y persistencia local.
- [ ] Adaptar tablero y tarjetas a escritorio, tableta y móvil.
- [ ] Cubrir navegación por teclado, foco visible, contraste y lectores de pantalla.
- [ ] Registrar finalización, errores, ayudas y tiempo de resolución sin datos personales.
- [x] Publicar una preview estática en GitHub Pages mediante GitHub Actions.

Criterio de salida: una sesión completa funciona con ratón, táctil y teclado en
Chrome, Firefox y Safari actuales, y la misma build está accesible en GitHub Pages.

## P2: calidad editorial

Objetivo: que dificultad y claridad sean propiedades medidas, no etiquetas heurísticas.

- [ ] Crear un propagador no enumerativo para explicaciones y pistas.
- [ ] Versionar la redacción y traducciones fuera de la lógica.
- [ ] Ejecutar pruebas ciegas y calibrar fácil, medio, difícil y experto.
- [ ] Detectar ambigüedad lingüística, pistas dominantes y soluciones por descarte técnico.
- [ ] Revisar licencia y procedencia de todos los recursos visuales.

Criterio de salida: cada nivel cumple su rango de tiempo, abandono y ayudas en
una muestra de prueba definida.

## P3: publicación

Objetivo: convertir generación, revisión y entrega en un flujo repetible.

- [ ] Crear un manifiesto por puzle con versión, seed, solución y métricas editoriales.
- [ ] Separar datos privados de solución de los datos enviados al jugador.
- [ ] Añadir revisión editorial, aprobación y retirada de puzles.
- [ ] Exigir tests y build correctos antes de desplegar GitHub Pages.
- [ ] Promover a producción únicamente artefactos generados por un commit identificado.
- [ ] Definir analítica, privacidad, backups y respuesta ante errores de contenido.

Criterio de salida: un puzle aprobado pasa de seed a producción y puede retirarse
sin editar archivos manualmente.

## Fuera de alcance por ahora

- Cuentas, pagos y multijugador antes de validar el jugador.
- Más motores exactos mientras CP-SAT cumpla los presupuestos.
- Un sistema de diseño independiente antes de estabilizar la interacción.
