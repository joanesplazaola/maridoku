# Murdoku V2-beta — informe de entrega

## Caso representativo

- Tablero: **Restaurante y terraza**
- Semilla: `4016`
- Víctima: **Bruno**
- Asesino: **Alicia**
- Dificultad provisional: **medium (39/100)**
- Profundidad del grafo de dependencias: **5**
- Aristas de dependencia: **8**

### Tarjetas

**Alicia**
- Había una silla en la misma columna que Alicia, dentro de su habitación.

**Bruno — víctima**
- Bruno estaba a solas con otra persona. Esa persona es el asesino.

**Carla**
- Carla estaba sola en el jardín.

**Diego**
- Diego estaba 2 columnas al oeste de Elena.

**Elena**
- Elena no estaba junto a ninguna pared.

**Fabio**
- Fabio estaba en la entrada o en la despensa.

## Benchmark final

- Tableros: **5**
- Casos solicitados: **25**
- Casos válidos: **25**
- Fallos: **0**
- Éxito: **100%**
- Tiempo medio: **0.6367 s**
- Percentil 95: **0.8585 s**
- Todas las tarjetas necesarias: **25/25**
- Solucionador deductivo coincidente: **25/25**
- Profundidad media de dependencia: **4.24**
- Aristas medias de dependencia: **7.88**

## Lo que ya está demostrado

- Catálogo formal de 22 tipos de pista.
- Cinco tableros distintos sin lógica específica por tablero.
- Selector global de tarjetas simples.
- Selector global con tarjetas dobles probado mediante un caso sintético donde la doble es obligatoria.
- Rechazo explícito de tarjetas o afirmaciones redundantes.
- Informe de aceptación y rechazo por objetivo candidato.
- Grafo de dependencias entre tarjetas.
- Validador exacto independiente.
- Semillas reproducibles.
- Seis pruebas automáticas superadas.

## Limitaciones honestas

- El benchmark incluido es de 25 casos, no el objetivo final de miles.
- Los 25 casos reales del benchmark se resolvieron con tarjetas simples; la rama de tarjetas dobles está probada de forma sintética, pero todavía falta observar su frecuencia y calidad en generación masiva.
- La dificultad sigue sesgada hacia media/difícil/experta y requiere calibración humana.
- El solucionador exhaustivo sigue limitado a 6×6; 8×8 o más requerirá backtracking.
- Los textos están en castellano con reglas básicas de concordancia; falta una capa lingüística completa.

## Validación independiente

```json
{
  "solution_count_up_to_two": 1,
  "unique": true,
  "matches_generated_solution": true,
  "murderer_matches": true
}
```
