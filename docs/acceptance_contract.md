# Contrato de aceptación y rechazo

Cada distribución objetivo recibe un registro dentro de `generation_report.json`.

## Rechazos previos al selector

- `subject_without_candidates`: algún sospechoso no tiene ninguna pista discriminativa.

## Rechazos del selector

Ejemplos:

- `contradiction`
- `card_no_information`
- `solved_before_all_cards`
- `not_unique`
- `redundant_card`
- `redundant_statement`
- `too_few_families`
- `too_many_coordinates`
- `too_many_relative_clues`
- `family_overrepresented`
- incompatibilidad con el perfil de dificultad

## Rechazo posterior

- `victim_card_redundant`: las tarjetas de sospechosos ya resuelven el caso sin necesitar la declaración de la víctima.

El último objetivo del informe tiene estado `accepted`. Si se agota `max_target_attempts`, la generación falla explícitamente.
