# Protocolo de playtest

1. La persona recibe únicamente la URL del puzle y no ve la solución.
2. Resuelve sin ayuda externa.
3. Al terminar, pulsa el botón de descarga y entrega el JSON de sesión.
4. No se recogen nombres, posiciones jugadas, IP, navegador ni identificadores
   personales.

Para calibrar un nivel hacen falta al menos diez sesiones completas de personas
que no hayan visto ese puzle. Se comparan mediana de tiempo, abandono, errores y
comprobaciones. Las etiquetas fácil, medio, difícil y experto no se consideran
calibradas hasta tener rangos no solapados en esa muestra.

```bash
uv run murdoku-v2 build-site --output _site
uv run murdoku-v2 playtest-report \
  --catalog _site/catalog.json \
  --sessions playtests/ \
  --output playtest-report.json
```

El informe exige diez sesiones completas por puzle, rechaza duplicados y solo
acepta sesiones del catálogo publicado. `ready_for_editorial_calibration` pasa
cuando además existen los cuatro niveles y sus rangos centrales de duración
están ordenados sin solaparse.
