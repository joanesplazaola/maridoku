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

## P0: generador escalable

Objetivo: producir 8x8 y 10x10 variados sin enumerar `(n!)²`.

- [ ] Parametrizar personajes y retirar el límite fijo de 6x6.
- [ ] Hacer del selector CP-SAT la ruta principal y eliminar el selector por máscaras.
- [ ] Sustituir las cadenas sintéticas por selección completa del catálogo de pistas.
- [ ] Definir presupuestos de tiempo y tasas mínimas de éxito para 6x6, 8x8 y 10x10.
- [ ] Conservar un conjunto pequeño de seeds de regresión en `examples/`.

Criterio de salida: 100 casos consecutivos por tamaño, todos únicos, sin pistas
redundantes y dentro del presupuesto publicado.

## P1: jugador web

Objetivo: probar puzles completos sin herramientas de desarrollo.

- [ ] Seleccionar sospechoso y colocarlo, moverlo o retirarlo del tablero.
- [ ] Mostrar restricciones de fila, columna y ocupación mientras se juega.
- [ ] Añadir deshacer, reiniciar, comprobación y persistencia local.
- [ ] Adaptar tablero y tarjetas a escritorio, tableta y móvil.
- [ ] Cubrir navegación por teclado, foco visible, contraste y lectores de pantalla.
- [ ] Registrar finalización, errores, ayudas y tiempo de resolución sin datos personales.
- [ ] Publicar una preview estática en GitHub Pages mediante GitHub Actions.

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
