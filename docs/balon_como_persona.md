# El balón detectado como PERSONA: regla de forma (BACKLOG 16) — 8-oct-2026

Solo medición, local, sin GPU, sin tocar producción. El criterio
(`scripts/balon_como_persona.py::CRITERIO`) se commitea ANTES de ver ningún número.

## De dónde venimos

- BACKLOG 16: la identidad `id 62` (equipo B) era un balón. Visto otra vez el 25-sep en
  `docs/proximidad_deteccion.md` (caja de confianza 0,39 sobre el balón).
- `docs/reglas_fisicas.md` ya midió cada regla física **por separado** y dejó dos avisos:
  la relación de aspecto SOLA no sirve (personas: p1 0,27 y mediana 0,39 de ancho/alto; a 0,25
  ya cuesta 2 personas) y la altura mínima SOLA cuesta personas desde 0,40× la mediana.
- Producción hoy: solo `ancho_min_frac: 0.15` (las líneas del campo).

## La regla (UNA, fijada antes de medir)

Un balón no tiene proporciones de persona: es **bajo Y cuadrado a la vez**. Ninguna de las
dos señales separa sola (ver arriba), pero una persona agachada es baja y sigue siendo más alta
que ancha, y una persona tumbada es ancha pero no baja. Se quita una detección de persona si:

- altura implícita (`alto_px × escala lateral` de la homografía, en el pie de la caja)
  **< 0,40 × la mediana del partido** (≈ 0,6 m: el balón mide 0,2 m), **y**
- relación de aspecto ancho/alto **≥ 0,70** (el balón ≈ 1; la persona mediana 0,39).

Va en fracción de la mediana del partido, como el resto del filtro físico.

## Cómo se mide

Sobre el caché de la parte entera (`cache_detecciones_benja_p1.pkl`), con los filtros que ya
pasa producción (confianza y `ancho_min_frac`), antes del tracking.

1. **Jugadores reales perdidos en el GT de 14** (ventana 5:25-5:55 de archivo, 6:58-7:28 del
   reproductor): una detección cuenta como persona del GT si el centro de la caja del GT cae
   dentro de ella, o el pie de la caja del GT está a menos de media altura de su pie. Se toma la
   unión a propósito (protege más). ⚠️ La caja del GT es una plantilla fija (CLAUDE.md), así que
   NO sirve para medir la forma: se mide la forma de la detección del sistema.
2. **Jugadores reales perdidos en el partido entero** (no hay GT): las detecciones que la regla
   quita se separan en dos grupos con el caché de BALÓN ya limpio (plausibilidad y marcas
   estáticas, `src/balon/carga.py`): las que tienen una detección de balón dentro de la caja
   (en el mismo frame o a ±1) y las que no. **Las que no coinciden con un balón se miran TODAS
   a ojo** (o 60 al azar si son más), en una hoja de recortes sacados con
   `posicionar_en_frame()`. También 20 de las que sí coinciden, como control de que son balones.
3. **Lo que quita del id 62 y similares**: en el CSV de producción de hoy (regenerado desde el
   caché en un temporal), las filas que salen de una detección con forma de balón, y las
   identidades cuya MAYORÍA de filas reales son de esas. Los ids de hoy no son los del 28-ago
   (un GT indexado por id caduca): «similares» se busca por la forma, no por el número.

## Criterio de adopción (`CRITERIO`)

- **0 personas del GT perdidas.** Si quita una sola, no se adopta.
- **0 jugadores reales en la revisión a ojo del partido entero** (agachados, caídos, cortados por
  el borde, fundidos). Si hay uno, no se adopta.
- Y tiene que quitar algo que importe: **al menos 1 detección que coincide con el balón**.
- La segunda pregunta (¿qué podría estar inventando o rompiendo?): se cuentan también las
  quitadas que no son ni balón ni persona, para decir qué son.

Aunque pase, **no se activa en producción sin el OK de Alex**: se deja el resultado y la regla
escrita.

Intentos: como mucho dos. El segundo, si hace falta, solo puede ENDURECER la regla (quitar
menos), nunca aflojarla para cazar más.
