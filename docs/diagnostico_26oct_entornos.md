# Diagnóstico 26-oct: los entornos (Mac contra Colab) y lo que falta para fusionar `fix-23oct-g`

Rama `fix-23oct-h`, sale de `fix-23oct-g`. Criterios escritos ANTES de medir; commit solo con pytest
en 0. **Nada se fusiona a `main`.**

**Punto de partida: la celda de Colab del chaleco PASÓ.**
- Salidas en Drive: `tactical-football-vision-data/salidas/chaleco_full/`.
- 600 frames y 10.908 detecciones.
- Chaleco dentro del bucle = pasada aparte (diferencia máxima 0); pista idéntica al 100 %.
- El chaleco cuesta 0,204 ms/frame (0,18 %).
- Entorno: Python 3.13, numpy 2.4.6, scipy 1.17.1, supervision 0.25.1, GPU Blackwell.

## 1. Cruce de entornos del chaleco (Colab → Mac)

**Qué se hace:**
- Con las cajas de `cache_B.pkl` (la caché de detección de Colab, que lleva su clave `chaleco`), se
  recalcula la puntuación en el Mac con el lector del ffmpeg CLI (`src/utils/video_ffmpeg.py`) y la
  misma corrección de distorsión (nula en el benjamín).
- Se compara detección a detección.
- Se corre la pista del árbitro (`desde_cache`, variante 2) dos veces sobre esas mismas cajas: una
  con la puntuación de Colab y otra con la del Mac.

**Criterio (antes de mirar):**
- puntuación dentro de **± 0,01 en ≥ 99 %** de las detecciones;
- pista del árbitro idéntica en **≥ 99,9 %** de los frames.
- Si no se cumple: cuánto difiere y de dónde viene (versión de ffmpeg, conversión de color o
  lectura del frame) y qué habría que volver a medir.

¿Qué podría estar inventando?
- Colab calculó dentro del bucle con `cv2.VideoCapture` (FFmpeg de Linux) y, en la pasada aparte,
  con el ffmpeg CLI de Linux; aquí es el ffmpeg CLI del Mac. Si coinciden, el número de la banda
  (medido en el Mac) vale en Colab.
- Se informa la versión del ffmpeg del Mac. La de Colab no está en sus salidas.

## 2. Control de ByteTrack: supervision 0.25.1 (Colab) contra 0.28.0 (Mac)

**Qué se hace:**
- En un venv aparte que hereda el entorno del Mac y SOLO cambia `supervision` a 0.25.1, se corre
  `desde_cache` del benjamín con las MISMAS cachés de detección:
  - la parte entera (`processor_benja_parte_entera.yaml`; la ventana del GT cae dentro);
  - el tramo de 60 s (`processor_benja.yaml`).
- Se compara contra el mismo `desde_cache` en el entorno del Mac (supervision 0.28.0).
- Medida: `src/evaluation/asociacion_desde_csv.py` contra el GT del benjamín, con **IDF1 y
  fragmentación** (identidades por persona); no se usa la pureza.
- Se informa además si los CSV salen idénticos byte a byte.

**Criterio (antes de medir)**:
- son **equivalentes** si la diferencia de IDF1 es **≤ 0,5 puntos** y la fragmentación es
  parecida. «Parecida» se fija aquí: la media de identidades por persona difiere **≤ 0,2**, el
  ruido de fase medido en la ablación 1/1 (0,21, `docs/plan_ablacion_1a1.md`).
- Si no son equivalentes: se dice, y se propone cuál es la canónica.

¿Qué podría estar inventando? El GT cubre 30 s del minuto 5. Un IDF1 igual en la ventana no prueba
que los tracks sean iguales en los 20 minutos; por eso se cuentan también los CSV idénticos y las
filas que cambian en el partido entero.

## 3. Documentación

- **CLAUDE.md**:
  - los pins `numpy<2.1` y `scipy<1.14` están desfasados;
  - el detector no corre en el Mac con numpy 2.4.6 (torch 2.2.2 es el último para Intel y está
    compilado contra numpy 1.x);
  - la detección larga va a Colab, o a un venv con numpy 1.26;
  - la receta de Colab, en UNA celda.
- **`requirements-colab.txt`**: alineado con lo validado en Colab (supervision 0.25.1), con la
  diferencia con el Mac anotada.

---

## Resultados

`scripts/diag26_entornos.py`. Las salidas, en `outputs/diagnostico_26oct/` (no van al repo).

### 1. El chaleco de Colab y el del Mac: IDÉNTICOS

| | resultado | criterio |
|---|---|---|
| detecciones comparadas | 10.908; 0 solo en Colab, 0 solo en el Mac | |
| puntuación dentro de ± 0,01 | **100 %**; idénticas el 100 %, diferencia máxima **0,0** | ≥ 99 % ✓ |
| pista del árbitro (592 frames en las dos) | **100 % idéntica**; el CSV, idéntico byte a byte | ≥ 99,9 % ✓ |

- ffmpeg del Mac: 8.1.1. La versión de Colab no está en sus salidas.
- **Qué significa**: la puntuación de Colab (dentro del bucle, con `cv2.VideoCapture` sobre el
  FFmpeg de Linux) es bit a bit la del ffmpeg CLI del Mac. La banda del chaleco, medida en el Mac,
  vale en Colab, y no hay nada que volver a medir.
- ¿Qué podría estar inventando? Es UN vídeo, de 1080p con distorsión nula. Con corrección de
  distorsión (Villaviciosa, k1 = −1,5), `cv2.undistort` entra en el camino y no está comprobado.

### 2. ByteTrack con supervision 0.25.1 y 0.28.0: EQUIVALENTES por el criterio, pero NO idénticos

| | parte entera, 0.28.0 (Mac) | parte entera, 0.25.1 (venv) | 60 s, 0.28.0 | 60 s, 0.25.1 |
|---|---|---|---|---|
| IDF1 (GT del benjamín) | 0,5887 | 0,5887 | 0,5875 | 0,5875 |
| IDSW | 43 | 43 | 43 | 43 |
| identidades por persona (media / mediana) | 3,07 / 3,5 | 3,07 / 3,5 | 3,07 / 3,5 | 3,07 / 3,5 |
| CSV idéntico byte a byte | — | **no** | — | **sí** |

- **Criterio**: diferencia de IDF1 0,0 puntos (≤ 0,5) y de fragmentación 0,0 (≤ 0,2). **Equivalentes.**
- **Pero en los 20 minutos los CSV no son iguales:**
  - 154.587 filas «distintas» comparando por (frame, id). Casi todo es **renumeración**: una sola
    identidad (de 435) se reparte de otra forma y desplaza la numeración de las que vienen detrás.
  - Comparando por posición: el **99,76 %** de las filas reales coincide (174.206 de 174.618), con
    **0 etiquetas distintas**.
  - **336 de 11.989 frames** tienen alguna fila real distinta, el primero en f666 (0:22,2 archivo /
    1:55,2 reproductor), y **27 frames** cambian el recuento A/B/otro.
  - B > 7: **8,45 % (0.28.0) contra 8,41 % (0.25.1)**.
- **Las dos son DETERMINISTAS**: repetida, cada una sale idéntica byte a byte, y la del Mac es
  idéntica a la de la adopción de ayer. La diferencia la pone la versión, no el azar.
- **Propuesta de canónica: 0.28.0, la del Mac.** Todos los números de `desde_cache` del proyecto
  están medidos con ella, y su suite pasa con ella.
  - En Colab, supervision NO toca la detección, que es lo único que allí se necesita: las cachés.
  - Si alguna vez un CSV de Colab tiene que coincidir con el del Mac, se instala allí la 0.28.0.

### 3. Documentación (hecho)

- **CLAUDE.md**:
  - los pins `numpy<2.1` / `scipy<1.14` están marcados como desfasados;
  - el detector no corre en el Mac (torch 2.2.2 con numpy 2.4.6), con la receta del venv con numpy
    1.26;
  - la nota de supervision, y la receta de Colab en una celda, sin reiniciar el kernel.
- **`requirements-colab.txt`**: supervision **0.25.1**, la validada en Colab, con la diferencia con
  el Mac anotada. ultralytics, sahi y pyyaml quedan fijados a las del Mac (8.4.71, 0.12.1 y 6.0.3)
  para que la celda sea reproducible.
