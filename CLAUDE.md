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
    **`candidato` es el default de producto** (cobertura colectiva 0.376
    vs 0.140; docs/experimentos_tracking.md registra TODAS las variantes
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
