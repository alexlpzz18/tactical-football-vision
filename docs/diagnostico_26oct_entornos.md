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
