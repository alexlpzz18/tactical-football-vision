# Tactical Lens — contexto para Claude Code

## Qué es este proyecto
SaaS de análisis táctico por computer vision para fútbol amateur (empresa ACIIES).
Pipeline: vídeo de partido → corrección de distorsión → detección de jugadores
(YOLOv8 + SAHI) → tracking → clasificación de equipos → proyección a metros
(homografía) → métricas colectivas → informe HTML.

Caso objetivo (difícil a propósito): cámara fija gran angular barata, jugadores
diminutos (15-40 px), equipaciones idénticas entre compañeros. El producto debe
ser 100% AUTOMÁTICO (sin intervención humana por partido).

## Estado del código (actualizado 12-jul-2026)
- Pipeline NUEVO integrado en `src/` y seleccionable por config:
  - `src/tracking/perfiles.py`: composición única banco↔producción
    (perfil `oficial` = goloso conservador; `candidato` = rescate + cosido
    global + exclusión espacial con salvaguarda + cota de plantilla).
    **`candidato` es el default de producto** (cobertura colectiva 0.456
    vs 0.184; docs/experimentos_tracking.md registra TODAS las variantes
    medidas y por qué se adoptaron o rechazaron).
  - `src/evaluation/`: banco de evaluación contra GT de CVAT
    (`scripts/evaluar_tracking.py`: métricas propias en metros + TrackEval
    + cobertura colectiva; soporta `--perfil oficial|candidato`).
  - `src/team_classification/color_classifier.py` + `pipeline_equipos.py`:
    clasificador 2 fases + agregación por cercanía + regla de porteros.
  - `src/tracking_data/processor.py`: v2 end-to-end (modos full/desde-caché,
    `configs/processor.yaml`, CLI `scripts/procesar_partido.py`); el flujo
    viejo (`process_video`, ByteTrack) sigue como fallback `pipeline: legacy`.
- PENDIENTE: validar el modo `full` en Colab con `best_v3.pt` (la detección
  requiere GPU; en local todo corre desde los cachés).
- El usuario es PRINCIPIANTE en ingeniería de software: explicar decisiones,
  código claro y comentado en español.

## Convenciones
- Comentarios y docstrings en ESPAÑOL. Nombres de variables descriptivos.
- Formato: Black + Flake8 (hay pre-commit hooks configurados).
- Tests con pytest en `tests/`. Después de CADA cambio: correr pytest y no dar
  nada por terminado si falla.
- Configuración externalizada (parámetros físicos y umbrales en un config,
  p. ej. `configs/tracking.yaml`), nunca números mágicos hardcodeados.
- Logging con el módulo `logging` (no prints) en el código de src/.

## Hallazgo que ordena el trabajo de tracking (17-ago-2026)
**La DETECCIÓN deja de ser la palanca** (decisión de Alex, 17-ago-2026):
su esfuerzo de etiquetado se para aquí. El frente es ASOCIACIÓN y
CLASIFICACIÓN. El v4 (mAP50 0,944 vs 0,900) no movió la aguja del
producto lo que costó.
Al cambiar de detector hay que RE-BARRER la asociación: los parámetros
van pegados al detector. Medido — con la caja de cambios del v4pre el v4
daba 8 quimeras; con la suya (`conf 0.45 · buffer 1.5 · empar 0.995 ·
minf 2 · hueco 4 · color 0.9`) da 3, y bate al v4pre en todo en
Villaviciosa. En el benjamín sigue por debajo, así que NO está adoptado.
Dónde nacen las quimeras (`scripts/diagnostico_quimeras.py`): el solape
de cajas es factor débil (1,8×) y minoritario; la señal limpia es la
RE-ENTRADA tras perder el track (3,0×). Línea abierta: meter la
apariencia en la asociación, con la puerta en la re-entrada. Diseño en
`docs/apariencia_en_asociacion.md`.

Corolario práctico: **un GT indexado por id del sistema caduca al cambiar
el detector** (medido: 27 de 30 identidades del mini-GT del benjamín son
otra persona con el v4, mediana 38 m). Los GT deben indexarse por
posición y tiempo.

## Qué NO hacer
- NO commitear datos, vídeos, modelos (.pt), caches (.pkl) ni exports de CVAT
  (están/deben estar en .gitignore; viven en Google Drive).
- NO tocar los notebooks de `notebooks/` (son el registro de experimentos).
- NO sustituir el diseño del tracker en metros por un tracker en píxeles de
  librería: el tracking en coordenadas de campo es la ventaja diferencial.
- NO usar boxmot (rompió el entorno: su v19 cambió la API y subió numpy a 2.5).
  Fijar numpy<2.1 y scipy<1.14 si hace falta scipy.
- La GPU NO está disponible en este Mac: todo lo que requiera inferencia
  (SAHI, YOLO, re-detección) se hace en Colab, NO aquí. Aquí se trabaja
  contra el caché de detecciones ya generado.

## Datos de trabajo (el usuario los copia de Drive a `data/`, gitignored)
- `data/tracking/cache_detecciones_min5_60s.pkl`: caché de detecciones del tramo de
  validación (min 5-6 de un partido, ~500 frames, 1 de cada 3, dt=0.12s).
  Formato pickle: {"cache": [ {"frame_idx": int, "t": float,
  "dets": [(mx, my, x1, y1, x2, y2, conf), ...]} ], "fps": float,
  "sample": int, "wh": (w, h)}. (mx, my) = posición en METROS (pies
  proyectados con homografía); (x1..y2) = caja en píxeles.
- `data/annotations/ground_truth_tracking/annotations.xml`: ground truth de tracking etiquetado a
  mano en CVAT, formato "CVAT for video 1.1". Tracks con identidad persistente.
  Labels: `player` (atributo `team`: A / B / portero_A / portero_B) y `referee`.
  Frames: gt_NNNNNN.jpg donde NNNNNN = índice de frame global del vídeo,
  1 de cada 15 frames reales del mismo tramo min 5-6.
  ⚠️ Alineación: el caché tiene 1 de cada 3 frames; el GT 1 de cada 15
  → evaluar sobre los frames comunes (los múltiplos de 15).
- `data/calibracion/homografia.npy`: matriz H 3x3 píxel→metros (ya en el repo).

## Hallazgo que reordena el proyecto (20-ago-2026)
**La ASOCIACIÓN es el 100 % del margen medible en métricas de producto;
el anclaje es cero.** Medido con tests de oráculo contra el GT de
identidad del benjamín (`docs/oraculos.md`):

| variante | centroide | anchura |
|---|---|---|
| sistema | 1,55 m | 0,93 m |
| + anclaje perfecto | 1,61 m | 1,03 m |
| **+ asociación perfecta** | **0,42 m** | **0,33 m** |

Arreglar la asociación divide el error de centroide por 3,7. Arreglar el
anclaje no lo mejora — un sesgo sistemático mueve el centroide pero no
deforma el bloque, y las métricas colectivas apenas lo notan. Por eso el
anclaje por pose baja de prioridad a comprobación barata.

Y la mezcla no está donde creíamos: sin re-entrada la pureza sube solo de
80,1 % a 84,4 %, así que **el 16 % restante se contamina DENTRO del
seguimiento continuo**, en los cruces. Un grafo global que solo una
tracklets tiene ahí su techo: hay que **partir y luego unir**.
