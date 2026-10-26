# Árbitro por observación, intento 2 (el último): la PUERTA chaleco contra césped (19-oct-2026)

Solo medición. El criterio (`scripts/puerta_chaleco_cesped.py::CRITERIO`) se commitea ANTES de medir.
El intento 1 falló porque la banda de color (H 55-75) cogía CÉSPED (`docs/plan_arbitro_por_observacion.md`).
Esta vez se mide primero si el chaleco y el césped se pueden separar; solo si pasa se construye la señal.

## Cómo se midió el chaleco en septiembre (la verdad de 59 de 60 frames)

Recuperado de la sesión del 21-sep (`4d6fb07d`; el código nunca se commiteó, solo el documento
`docs/arbitro_y_baile_de_colores.md`):
- recorte: filas 15-55 % del alto de la caja, columnas 25-75 % del ancho;
- píxel flúor: H 35-85, **S ≥ 110**, V ≥ 150 (OpenCV); la fila es árbitro si su fracción supera 0,08;
- **tres pistas que no son el color**: se quedaba con la fila de MÁS fracción de cada frame (supone que
  hay exactamente un árbitro por frame), solo entre las filas que NO casaban con ninguna persona del GT, y
  apartaba al portero de B por la posición y el GT.

**¿Generaliza fuera de la ventana? No tal cual.** Fuera no hay GT con el que descartar a los jugadores,
y «la fila de más fracción del frame» siempre corona a alguien, esté o no el árbitro a la vista. Además,
S ≥ 110 deja fuera el chaleco en los minutos en que cae a S ≈ 72-104: funcionó en esa ventana porque es un
minuto de S alta. Sirvió como verdad LOCAL para calibrar el proxy, no como detector.

## La puerta (fijada antes)

Tres poblaciones de píxeles, todas del CENTRO del torso (filas 20-45 %, columnas 35-65 % de la caja), leídas
del vídeo con lectura secuencial (nunca `cap.set`), 20 frames por minuto (uno cada 3 s), minutos 0-19:
- **(a) chaleco**: cajas de filas que el proxy (`arbitro_medicion.py`) marca como árbitro. Cada minuto se
  clasifica por la mediana de S de sus píxeles: **S alta** si ≥ 170, **S baja** si ≤ 120 (entre medias,
  «mixto», se informa aparte);
- **(b) césped**: «cajas vacías» del mismo tamaño que una caja real, desplazadas en horizontal hasta donde no
  solapan ninguna detección, con el pie dentro del campo; se reparten en tres franjas de profundidad
  (x 0-20, 20-40, 40-62 m);
- **(c) portero de B**: cajas de filas etiquetadas `portero_B`.

**El rango del césped**, minuto a minuto: el rectángulo (S, V) entre sus percentiles 1 y 99 en ese minuto.
**Solape** = fracción de los píxeles de chaleco de ese minuto que caen dentro de ese rectángulo.

**Criterio de cierre (la propuesta de Alex):** si **más del 10 % de los píxeles de chaleco de los minutos
de S BAJA** caen dentro del rango del césped, **la vía se cierra sin construir**. Se usa el solape de todos
los minutos de S baja juntos. Si no hay ningún minuto de S baja, la puerta es NO CONCLUYENTE.

Se informa también H de las tres poblaciones (por si H separa lo que (S, V) no separa), pero la puerta se
decide en (S, V), como se acordó.

## Solo si la puerta pasa

La señal sobre el centro del torso, con el portero excluido por posición (dentro de su área), y el mismo
criterio que el intento 1: como mucho 1 jugador o portero convertido en árbitro en la ventana del GT, y las
20 cajas de más fracción que no son árbitro, miradas a ojo.

## Resultado (19-oct-2026): la puerta es NO CONCLUYENTE — no se construye el paso 3

`python scripts/puerta_chaleco_cesped.py --trabajo outputs/arbitro_obs` (fuera de git). 20 minutos, 20
frames por minuto, centro del torso.

**Veredicto del criterio: NO CONCLUYENTE (no hay ningún minuto de S baja).** Por el plan, el paso 3 solo
se hace si la puerta pasa: **no se construye la señal**.

**La premisa de la que salía la puerta no se cumple en PÍXELES.** La mediana de S del chaleco está
entre 171 y 178 en TODOS los minutos (17 «S alta», 3 «mixtos» entre 162 y 168, ninguno ≤ 120). La
alternancia S ≈ 248 / S ≈ 72-104 de CLAUDE.md se midió sobre el HISTOGRAMA del caché de color (los bins
de la feature del catálogo), no sobre los píxeles del vídeo: es una propiedad de esa representación, no
del chaleco.

**Solape (S, V) con el césped del mismo minuto: entre el 0,1 % y el 4,6 %** en los minutos de S alta, y
hasta el 8,4 % en el peor minuto mixto (el 15). Nunca pasa del 10 %.

| | H (p25-p50-p75) | S | V |
|---|---|---|---|
| chaleco | 45 · **46** · 47 | 160 · 175 · 185 | 231 · **247** · 255 |
| césped x 0-20 m | 55 · **55** · 57 | 72 · 78 · 86 | 106 · **113** · 119 |
| césped x 20-40 m | 54 · 54 · 56 | 74 · 81 · 87 | 117 · 122 · 127 |
| césped x 40-62 m | 36 · 53 · 55 | 68 · 79 · 90 | 120 · 128 · 147 |
| portero de B | 39 · 50 · 54 | 79 · 112 · 138 | 127 · 160 · 185 |

**Lo que dicen los datos, sin construir nada:**
- **El chaleco es H ≈ 46, no H ≈ 62**, y el césped es H ≈ 54-55. La banda del intento 1 (H 55-75)
  estaba justo encima del césped y por encima del chaleco: por eso medía césped y casi nunca veía al
  árbitro.
- Lo que más separa al chaleco del césped es el **brillo (V ≈ 247 contra 113-128)**, y también del
  portero de B (V ≈ 160).
- ⚠️ **Sesgo de selección**: los píxeles de chaleco salen de las filas que marca el proxy, que pide
  masa en la región flúor del histograma con S ≥ 80. Si hay minutos en que el chaleco no llega a eso,
  el proxy no los ve y esta medida tampoco. «Ningún minuto de S baja» vale para el árbitro que el proxy
  encuentra.

**Este era el segundo y último intento.** Por la regla de los dos intentos, la vía del árbitro por
observación con un umbral de color queda **cerrada como está planteada**. Si se quisiera retomar con lo
que se ha aprendido (H ≈ 46 y V alto), sería un experimento NUEVO, con su plan y su criterio, y con la
validación fuera de ventana que espera a las marcas de Alex en la hoja de revisión.
