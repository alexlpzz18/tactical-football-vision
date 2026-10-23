# Diagnóstico 23-oct (f): el chaleco en la pasada de detección, la máscara de zona de juego y una hoja de GT de balón

Rama `fix-23oct-f`, sale de `adopcion-viterbi` (con `fix-23oct-e` fusionada): la adopción del
árbitro es el punto de partida del bloque 1. **Nada va a `main`.** Criterios escritos y commiteados
ANTES de medir; un commit por bloque, solo con pytest en código 0. Producción solo cambia tras flag.

Relojes del benjamín: frame / 29,97 = tiempo del **archivo**; el reproductor de Alex va **+1:33**.

---

## Bloque 1 — la puntuación de chaleco dentro de la pasada de detección (modo `full`)

**Hoy**: la variante 2 necesita `rutas.cache_chaleco`, que sale de una pasada APARTE en CPU
(`scripts/cache_chaleco.py`). El modo `full` no la genera.

**Cambio**:
- En el bucle de `detectar_y_cachear`, para cada detección y del MISMO fotograma ya corregido con el
  que se saca la feature de color, se calcula la fracción de píxeles del torso en la banda del
  chaleco.
- La función es UNA y la comparten la pasada aparte y la de detección: se mueve de
  `scripts/diag23a_chaleco.py` a `src/team_classification/chaleco.py`.
- Se guarda en la caché de detección, clave raíz `chaleco: {(frame, det): fracción}`.
- La banda va en el config: `deteccion.chaleco_banda: [H0, H1, S0, V0]`.
  - F7 (benjamín): `[38, 48, 112, 173]`, la medida el 23-oct (a).
  - F11: `null`. No se calcula porque **no hay banda medida para Villaviciosa** (la mide la celda
    de Colab del 23-oct c). Calcularla con la banda del benjamín costaría lo mismo, pero guardaría
    una puntuación de otro chaleco bajo un nombre que dice lo contrario, así que no se hace.
- La banda entra en la FIRMA de la caché **solo si está puesta**: una caché de F11 conserva su firma
  y su reanudación.
- En `desde_cache`, la fuente de la puntuación es, por orden:
  1. `rutas.cache_chaleco` (la pasada aparte, como hoy);
  2. la clave `chaleco` de la caché de detección.
  - Si la pista está encendida (F7) y no hay ninguna de las dos: **error explícito**, que dice las
    dos formas de arreglarlo.

**Criterios (antes de medir)**, en el benjamín (parte entera):
1. **≥ 99 % de las detecciones** con puntuación idéntica (± 0,005) a la de la pasada aparte.
2. **La pista Viterbi sale idéntica en ≥ 99,9 %** de sus frames, alimentada con la puntuación de la
   caché de detección.
3. **Coste añadido < 5 %** del tiempo de la pasada de detección.

**Qué se puede probar en local y qué no:**
- En local no hay GPU. La pasada de detección entera (SAHI) no se ejecuta.
- **Sí se prueba la parte que no es SAHI.** El código del bucle que va después de la detección
  (feature de color + chaleco) se saca a una función. Se alimenta con las cajas de la caché de
  producción y con los fotogramas del vídeo decodificados con el ffmpeg CLI, el decodificador de
  producción, y se compara contra la pasada aparte (criterio 1) y contra la pista (criterio 2).
- ⚠️ **En local eso es casi una tautología**: la misma función, los mismos píxeles. Lo que puede
  romperse en Colab es el DECODIFICADOR. El modo `full` lee con `cv2.VideoCapture`, que en Linux usa
  FFmpeg; en este Mac usaría AVFoundation, que no coincide con producción (CLAUDE.md). Por eso la
  validación de verdad es la celda de Colab.
- **El coste**: en local se mide el tiempo del chaleco por frame en CPU. Se compara con el tiempo
  por frame de la pasada en GPU que dan los logs de la parte entera. La celda de Colab lo mide de
  verdad, con y sin chaleco en el mismo tramo.

¿Qué podría estar inventando? Una coincidencia del 100 % en local solo prueba que el código hace lo
mismo dos veces. Lo que importa (los píxeles de `cv2` en Linux) lo dice Colab.

## Bloque 2 — máscara de zona de juego en la imagen (flag `balon.mascara_zona`)

- `balon.mascara_zona` en el YAML del campo: un polígono en PÍXELES `[[x, y], ...]` o `null`
  (APAGADO = la selección de siempre, idéntica byte a byte).
- Con el polígono puesto, las candidatas de balón con el centro FUERA se descartan **antes de
  elegir**: tanto las detecciones como las readmitidas como vuelo. El sitio es el principio de
  `seleccionar_balon_activo`, que comparten el vídeo y la pizarra.
- **El polígono lo marca Alex, NO se ajusta a datos**:
  - `scripts/marcar_mascara_zona.py`: 6-8 clics sobre un frame, a lo largo del borde superior de la
    grada y del perímetro de la zona de juego;
  - deshacer con `z`, guardar con Enter;
  - escribe el JSON y, con `--escribir-yaml`, la clave en `configs/campo_benja.yaml`.
  - Frame de ejemplo listo: `data/calibracion_benja/frame_mascara.png`.
  - Las candidatas etiquetadas el 23-oct (e) NO se miran para marcarlo; solo sirven para medir.

**Criterios (antes de medir), cuando Alex haya marcado el polígono:**
1. «campo de al lado» de **7 → ≤ 2** de los 30 paneles del 22-oct. Un panel sigue mal si el balón
   elegido sigue siendo una candidata del campo de al lado.
2. **Ningún panel «ok» empeora**: los 13 conservan la misma detección elegida.
3. **Balón real dentro ≥ 95 % en los DOS tramos**, con las etiquetas del 23-oct (e) (minuto 5: 38;
   minutos 14-16: 36), **incluidos los saques con el balón sobre la cabeza** (C09 y C25 del
   control).
4. **Control**: el mismo polígono desplazado 100 px (hacia abajo, en `y`) tiene que empeorar al
   menos uno de: campo de al lado fuera (con las etiquetas) o balón real dentro. Si no empeora nada,
   el polígono no está haciendo lo que se cree.

Hasta que Alex marque el polígono, el bloque 2 queda **implementado y NO MEDIDO**.

¿Qué podría estar inventando? Un polígono que pasa en estos dos tramos puede fallar con otra luz o
con la cámara movida. Es una máscara de UNA instalación de cámara: si la cámara se mueve, hay que
volver a marcarla, igual que la homografía.

## Bloque 3 — hoja rápida de GT del balón (para Alex, ≤ 20 min)

- **300 frames, no se mide nada.**
  - 200 del benjamín (parte entera), al azar y estratificados por zona.
  - Villaviciosa: **no hay caché de balón** de Villaviciosa (`data/tracking/` no tiene ninguna), así
    que no entra. Se dice.
- **Estratos** (semilla 0, separados ≥ 3 s entre sí):
  - 60 + 60 + 60 frames con candidata, por tercil de metros por píxel en la candidata ELEGIDA
    (cerca / media / lejos);
  - 20 frames SIN ninguna candidata, para ver si el balón estaba y no se detectó.
- **La hoja**: una página HTML local, una imagen por frame con la candidata elegida marcada (y las
  demás, más tenues).
  - Teclas: `A` acepta (la candidata marcada es el balón), `R` rechaza (no lo es, y el balón no se
    ve), clic sobre el balón (está en otro sitio, o no había candidata), `N` no se puede decir.
  - Guarda sola en el navegador y descarga un CSV.
- **Salida**: `gt_balon_por_frame.csv` (frame, respuesta, x_px, y_px) y un `leer` que lo pasa a
  `data/`.
