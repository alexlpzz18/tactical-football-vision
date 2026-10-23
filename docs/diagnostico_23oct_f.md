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

---

## Resultado del bloque 1 — chaleco en la pasada de detección: PASA en local; la validación con GPU, preparada y SIN ejecutar

**Implementado:**
- `src/team_classification/chaleco.py`: la ÚNICA implementación de la puntuación. La usan la pasada
  aparte (`scripts/cache_chaleco.py`, `scripts/diag23a_chaleco.py`) y el modo `full`.
- `processor.features_del_frame`: lo que se calcula después de SAHI (feature de color + chaleco),
  sacado del bucle para poder probarlo sin GPU.
- `deteccion.chaleco_banda`: `[38, 48, 112, 173]` en los configs F7 y `null` en F11.
- La banda entra en la firma solo si está puesta, y se recupera del checkpoint al reanudar.
- `desde_cache` toma la puntuación de `rutas.cache_chaleco` o, si no está, de la clave `chaleco`
  de la caché de detección. Si no hay ninguna de las dos y la pista está encendida: error, que dice
  las dos formas de arreglarlo.
- Tests nuevos: `tests/test_chaleco_en_deteccion.py`, 5.

**Probado en local** (`scripts/diag23f_chaleco.py`, `outputs/diagnostico_23oct_f/bloque1_chaleco.json`).
La parte del bucle posterior a SAHI se reprodujo sobre los 11.989 frames, con las cajas de la caché
de producción y el ffmpeg CLI:

| criterio | resultado |
|---|---|
| 1. puntuación igual a la pasada aparte (± 0,005), ≥ 99 % | **100 %** de 211.282 (diferencia máxima 0,0) |
| control: la feature de color sale igual que la caché de producción (el fotograma es el mismo) | **100 %** de 209.705 |
| 2. pista Viterbi desde la caché de detección «con chaleco» (sin `rutas.cache_chaleco`), ≥ 99,9 % | **100 %** de 11.642 frames; el CSV, **idéntico byte a byte** al de la variante 2 |
| 3. coste < 5 % | chaleco **0,34 ms/frame** en CPU contra 95 ms/frame de la pasada en una T4 = **0,36 %**; +3,4 MB en la caché |

Además, sin cambios:
- Villaviciosa (`desde_cache`): **idéntica byte a byte a `main`**.
- El benjamín por defecto: **idéntico** al CSV de la adopción.

**NO probado en local** (no hay GPU, y el decodificador del Mac no es el de producción):
- El bucle real con SAHI, y que `cv2.VideoCapture` en Linux dé los mismos píxeles que el ffmpeg
  CLI.
- **Celda preparada, SIN ejecutar**:

  ```
  !python scripts/colab_chaleco_full.py --salida /content/chaleco_full
  ```

  - Pasa el modo `full` dos veces sobre el tramo de 60 s del minuto 5, sin banda y con banda.
  - Comprueba que las cajas son las mismas.
  - Calcula la pasada aparte con el ffmpeg CLI sobre esas cajas.
  - Mide los tres criterios y el tiempo del chaleco dentro del bucle.

¿Qué podría estar inventando?
- **El 100 % de local es casi una tautología**: es la misma función sobre los mismos píxeles. Lo
  único que prueba es que el índice de cada detección y la corrección de distorsión casan. El
  número que importa es el de Colab.
- **El coste se midió como la diferencia entre dos cronómetros de CPU**, no en GPU. En la pasada
  real, el chaleco corre en CPU mientras la GPU ya ha acabado, así que se SUMA. Aun multiplicado
  por 10 seguiría por debajo del 5 %.
- **F11 no guarda la puntuación** (no hay banda medida). El criterio decía «si es barato»: es
  barato, pero sería otro chaleco bajo el mismo nombre.

## Resultado del bloque 2 — máscara de zona de juego: implementada, herramienta lista, NO MEDIDA

- **Flag** `balon.mascara_zona`, en `configs/campo_benja.yaml`, `null` = APAGADO.
  - `ParametrosBalon.mascara_zona`, `filtrar_por_mascara_zona` y `dentro_del_poligono` (regla
    par-impar, admite polígonos cóncavos).
  - Se aplica al principio de `seleccionar_balon_activo`, sobre las detecciones y también sobre las
    que se readmitirían como vuelo. Es el único punto que comparten el vídeo y la pizarra.
- **Apagado = igual que antes**: el CSV de `procesar_balon.py` (parte entera, 191.805 filas) es
  **idéntico byte a byte** al de `fix-23oct-e`.
- Tests nuevos: `tests/test_mascara_zona_balon.py`, 4. Uno es de comportamiento: con la máscara, la
  candidata de fuera, que ganaba, deja de elegirse.
- **La herramienta, para Alex** (6-8 clics, `z` deshace, Enter guarda):

  ```
  python scripts/marcar_mascara_zona.py marcar --escribir-yaml
  ```

  - El frame de ejemplo ya está extraído con el decodificador de producción:
    `data/calibracion_benja/frame_mascara.png`, f9306 (5:10,5 archivo / 6:43,5 reproductor). Sale
    el balón del campo de al lado y la grada despejada.
  - Guarda en `data/calibracion_benja/mascara_zona_benja.json` y, con `--escribir-yaml`, en el
    config del campo.
- **La medida, lista para cuando haya polígono**:

  ```
  python scripts/diag23f_mascara.py --salida outputs/diagnostico_23oct_f
  ```

  Calcula los 4 criterios, el control desplazado 100 px incluido.
  - Solo se ha pasado una **prueba de humo** con un polígono que es la imagen entera, que no es
    ningún ajuste: 7 de 7 paneles siguen mal, ninguno cambia, 100 % de balón real dentro y el
    control no empeora nada. Es lo esperado para una máscara que no quita nada: el script corre de
    punta a punta.
- ⚠️ **Una precisión del criterio 2.** Los paneles del 22-oct no guardaron QUÉ frames eran «ok»
  (13 de 30), solo cuántos por estrato. Se mide de forma más ESTRICTA: ninguno de los 23 paneles que
  no son del campo de al lado puede cambiar de detección elegida. Si alguno cambia, se mira a ojo.
