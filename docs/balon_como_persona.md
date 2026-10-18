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

## Resultado (8-oct-2026): NO SE ADOPTA — pierde jugadores reales

Reproducir: `scripts/balon_como_persona.py medir`, `hoja` y `veredicto --personas-a-ojo 7`.

| | |
|---|---|
| detecciones de persona (parte entera, tras los filtros de producción) | 206.812 |
| **quitadas por la regla** | **4.839** |
| … con un balón dentro (caché de balón limpio, f ± 1) | **136** |
| … sin balón | 4.703: 3.972 fuera del campo, 632 cortadas por el borde inferior, 99 dentro |
| personas del GT de 14 perdidas | **0** de 794 (la persona más baja del GT mide 0,50× la mediana) |
| **jugadores reales en la revisión a ojo** (60 al azar de las «sin balón») | **7 de 60** |

**Los 7 son el mismo caso: la cabeza de un jugador de camiseta negra cortado por el borde
inferior**, a 4:23,5, 6:45,1, 13:38,6, 17:07,4, 18:45,5, 19:48,6 y 19:49,1 de archivo (5:56,5,
8:18,1, 15:11,6, 18:40,4, 20:18,5, 21:21,6 y 21:22,1 del reproductor). Una caja cortada es baja Y
cuadrada: tiene la forma de un balón. El GT de 14 no lo veía porque en su ventana nadie está así.
Es la misma lección de siempre: **una muestra corta no ve el caso que rompe la regla**.

El resto de la hoja: **unos 35 de 60 son CONOS** de entrenamiento junto al banquillo, y el resto
balones fuera del campo (el del otro campo o los de reserva) y pies. El control (20 «con balón») sí
son balones los 20.

**Lo que quitaría del «id 62 y similares»** (CSV de producción de hoy, 174.618 filas reales): 2.941
filas salen de una caja con forma de balón, **pero solo 44 tienen un balón dentro**. 35 identidades
son mayoritariamente de esa forma: 24 `staff` (muy probablemente los conos, por la hoja; no se ha
comprobado identidad a identidad), 8 `B`, 2 `portero_A` (el portero cortado) y 1 `otro`. (La
etiqueta de cada identidad es la de su primera fila.) El equivalente de hoy del id 62 es **el id 70** (15 filas de `B`, las 15 con
balón dentro). El balón como persona existe, pero es pequeño: 136 detecciones en 20 minutos.

**Decidido por los datos** (Alex fijó «si pierde jugadores reales, no se adopta»): no se adopta y no
hay segundo intento. El único endurecimiento evidente, excluir las cajas que tocan el borde inferior,
sería otra regla con su propio criterio, no este intento. Hallazgo de paso: **los conos son
detecciones de persona** (identidades `staff` como la 851, con 189 filas). Hoy no hacen daño porque
salen como `staff`, fuera de los bloques.
