# Operación y privacidad

## Analítica

El jugador guarda progreso y métricas en `localStorage`. No realiza peticiones de
analítica. La exportación contiene únicamente identificador del puzle, tamaño,
identificador aleatorio de sesión, duración, comprobaciones, errores y estado
de finalización.

## Respaldo

Puzles, manifiestos y cambios editoriales se versionan en Git. Los artefactos de
Pages se regeneran desde un commit identificado; `solution.json` nunca se copia
al sitio público.

## Error de contenido

1. Retirar el manifiesto con `murdoku-v2 editorial-status --status retired`.
2. Publicar el commit de retirada.
3. Para un error de código, revertir el commit responsable y dejar que Pages
   despliegue de nuevo la última versión válida.
4. Conservar el seed y los hashes del manifiesto en el informe del incidente.

Un manifiesto retirado no puede volver a aprobarse; una corrección genera un
nuevo puzle y un nuevo manifiesto.
