# Roadmap de producto

## Principios

- La escena se diseña antes que la solución y nunca revela dónde ocurrió el crimen.
- La víctima está identificada con `V`; el asesino es quien quedó a solas con ella.
- CP-SAT demuestra solución, unicidad y necesidad. No decide si un caso es interesante.
- La dificultad depende de las técnicas deductivas, no del tamaño del tablero.
- Solo se publica contenido autorado que pase el contrato editorial.

## P0: caso de referencia

- [x] Retirar la “Sala del crimen” del contenido publicado.
- [x] Publicar una escena temática independiente de la solución.
- [x] Marcar explícitamente a la víctima.
- [x] Limitar a una pista necesaria por tarjeta.
- [x] Usar al menos cuatro familias y como máximo un 30 % de pistas direccionales.
- [x] Validar solución, asesino, unicidad y necesidad con CP-SAT.
- [x] Evitar que el jugador revele en vivo la verdad de cada pista.
- [x] Añadir marcas X, borrador y resaltado pista-objeto.
- [x] Añadir potenciales de personajes por casilla.

Criterio de salida: “Último servicio” puede jugarse completo y pasa el contrato
editorial automatizado.

## P1: lenguaje de casos

- [x] Separar formalmente plantilla de escena, solución y pistas.
- [x] Generar pools reproducibles de pistas verdaderas sobre una escena fija.
- [x] Seleccionar una pista necesaria por sospechoso mediante contraejemplos CP-SAT.
- [x] Generar soluciones y asesinos reproducibles sin una solución de entrada.
- [x] Exigir variedad entre objetos, habitaciones y relaciones, no solo entre subfamilias técnicas.
- [x] Completar pistas de ocupación y género en generación, CP-SAT y deducción humana.
- [x] Añadir unicidad junto a objetos y agrupar candidatos por tipo de mobiliario.
- [x] Añadir relaciones diagonales en generación, CP-SAT, jugador y deducción humana.
- [x] Separar pistas globales de tarjetas y soportar mínimos por habitación.
- [x] Seleccionar pistas globales necesarias mediante un perfil editorial explícito.
- [x] Añadir negaciones de proximidad a objetos de extremo a extremo.
- [ ] Corregir toda semántica espacial contra el glosario, incluida “al lado”.
- [ ] Completar de extremo a extremo los tipos exactos ya modelados antes de añadir otros.
- [ ] Añadir pistas globales, negativas, diagonales y de unicidad como cortes verticales completos.
- [ ] Ampliar objetos solo cuando una escena aprobada los necesite.
- [x] Modelar zonas superpuestas y pistas de borde.
- [ ] Modelar secuencias temáticas para mecánicas especiales.
- [x] Admitir tableros rectangulares con personajes según el lado menor.
- [ ] Verificar generación y render en tamaños de 5×5 a 16×16.
- [x] Sustituir la generación editorial de `scaling.py` por variantes sobre una escena fija.
- [ ] Crear tres casos de referencia: fácil, medio y difícil.

Criterio de salida: tres casos distintos, cada uno con mapa, objetos y técnica
central propios; ninguno deriva su geometría de la solución.

## P2: dificultad humana

- [x] Implementar un propagador de candidatos por técnicas humanas.
- [x] Exigir una ruta deductiva sin ensayo y error además de unicidad exacta.
- [x] Medir pasos, profundidad, bifurcaciones y técnica más difícil.
- [ ] Calibrar fácil, medio, difícil y experto con pruebas ciegas.

Criterio de salida: la etiqueta de dificultad está respaldada por una ruta
deductiva y por datos de personas.

## P3: catálogo comercial

- [ ] Generar candidatos sobre plantillas aprobadas y enviarlos a revisión.
- [ ] Publicar 15 casos autorados antes de volver a plantear un catálogo de 50.
- [ ] Revisar licencia y procedencia de todos los recursos visuales.
- [ ] Completar QA en Chrome, Firefox y Safari, escritorio y móvil.
- [x] Desplegar builds verificadas en GitHub Pages.
- [x] Mantener solución privada y retirada reproducible de casos.

## Fuera de alcance

- Cuentas, pagos y multijugador antes de validar 15 casos.
- Más motores exactos mientras CP-SAT cumpla el presupuesto.
- Generar volumen para ocultar falta de variedad editorial.
