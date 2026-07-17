# BRIEFING PARA CLAUDE CODE — Tactical Lens
### Documento de arranque: contexto, estado del repo, tareas y reglas
*(Preparado el 3-jul-2026. Pegar la sección "PROMPT INICIAL" en Claude Code; guardar la sección "CLAUDE.md" como archivo CLAUDE.md en la raíz del repo.)*

---

## PARTE 1 — CLAUDE.md

(El contenido de esta parte está en el archivo `CLAUDE.md` de la raíz del repo.)


---

## PARTE 2 — CÓDIGO VALIDADO A MIGRAR (referencia para Claude Code)

Los notebooks de Colab contienen estas piezas validadas (el usuario puede
pegarlas si Claude Code las pide; resumen de cada una):

### 2.1 Tracklets conservadores (Etapa A) — validado: 309 tracklets puros
- Clase `Tracklet`: id, listas ts/pos (metros)/det_idxs, vel suavizada
  (0.6/0.4), `predecir(t)` por velocidad constante.
- Asociación por frame: matriz de distancias predicción↔detecciones en METROS,
  húngaro (scipy `linear_sum_assignment`), radio físico
  `RADIO = V_MAX(7.0 m/s) × dt + MARGEN(0.8 m)`.
- **Regla anti-robo (clave):** si la 2ª mejor opción está a < 70% de distancia
  extra (AMBIG_FACTOR=0.7) en fila o columna → NO asociar (cortar tracklet).
  Preferimos fragmentar limpio a contaminar.
- Cierre de tracks: sin verse > MAX_GAP = 3×dt → a cerrados. Filtro final:
  tracklets con ≥3 frames.
- `det_idxs` guarda qué detección del caché es de cada track en cada frame
  (imprescindible para pintar sin bugs y para extraer colores).

### 2.2 Cosido de tracklets (Etapa B v2) — validado: 309 → 94 identidades
- Candidato (A,B): B empieza tras A (hueco ∈ (0, MAX_HUECO=6.0 s]);
  distancia entre `pos_final_A + vel_A × hueco` y `pos_inicial_B` ≤
  `TOL_BASE(1.2) + TOL_POR_SEG(3.0) × hueco`; color compatible (veto SUAVE:
  distancia de histogramas > 1.2 → veto; el color en esta cámara es señal
  débil: mediana de distancias entre pares legítimos = 0.90, p90 = 1.16).
- Coste = dist/tolerancia + 0.3×(hueco/MAX_HUECO) + 0.15×coste_color.
- Unión golosa ordenada por coste, sin conflictos (cada tracklet recibe una
  continuación y es continuación de uno) → cadenas = identidades.

### 2.3 Clasificador de equipos 2 fases — validado en frames sueltos
- `TeamClassifierColor`: `_color_torso(crop)` = banda del pecho (12-45% alto,
  15-85% ancho) + máscara anti-verde HSV (35-85, 40+, 40+) + histograma HS
  16×16 normalizado.
- `fit(crops)`: KMeans k=8 generoso → fusión jerárquica (linkage average sobre
  centros) con umbral AUTO (maximiza equilibrio-top2 × separación-del-3º en
  barrido 0.5-1.3) → 2 meta-grupos más grandes POR TAMAÑO = equipos →
  prototipos (media de features) de A, B y "otros".
- `predict_color(feat)`: distancia a prototipos → 'A' / 'B' / 'otro'.
- Pendiente de conectar: agregación por identidad (color medio de todos los
  recortes de una identidad cosida → una clasificación por identidad).

---

## PARTE 3 — TAREAS EN ORDEN (una rama y un commit por tarea)

### Tarea 1 — Banco de evaluación de tracking (`feature/banco-evaluacion`)
Construir en `src/evaluation/`:
1. Parser del ground truth "CVAT for video 1.1" (annotations.xml) → estructura
   interna: por frame, lista de (track_id_gt, caja o punto, team).
2. Adaptador del resultado de nuestro pipeline (identidades cosidas sobre el
   caché) al formato de evaluación.
3. Cálculo de métricas: HOTA, IDF1, ID switches, fragmentaciones + accuracy de
   clasificación de equipos por identidad. Evaluar dos vías y elegir la más
   práctica documentando por qué: (a) librería `trackers` de Roboflow
   (Apache 2.0, comando `trackers eval`), (b) TrackEval (estándar académico).
   ⚠️ La asociación GT↔predicción puede hacerse por distancia en metros
   (proyectar el pie de la caja GT con la homografía) o por IoU de cajas;
   elegir, justificar y documentar.
4. Script `scripts/evaluar_tracking.py` que: carga caché + GT, corre el
   pipeline actual (Etapa A + cosido v2 con los parámetros validados), imprime
   la tabla de métricas. → **Entregable: la PRIMERA MEDICIÓN del pipeline
   actual (baseline).**
5. Tests: parser con un XML mínimo de juguete; métricas con un caso sintético
   de resultado conocido (p. ej. tracker perfecto → IDF1=1.0).

### Tarea 2 — Modularización a producción (`feature/tracking-modular`)
1. `src/tracking/field_tracker.py`: Tracklet + Etapa A (clase
   `ConservativeTracker`), parámetros desde `configs/tracking.yaml`.
2. `src/tracking/stitcher.py`: Etapa B (clase `TrackletStitcher`).
3. `src/team_classification/color_classifier.py`: `TeamClassifierColor`
   (sustituirá al TeamClassifier viejo, que se deja intacto de momento).
4. `src/tracking/cache_io.py`: carga/validación del caché de detecciones.
5. Docstrings en español, type hints, logging, tests pytest de cada módulo
   (trayectorias sintéticas para el tracker: 2 jugadores que se cruzan sin
   robarse el ID; cosido de un tracklet partido artificialmente; clasificador
   con colores sintéticos).
6. NO tocar processor.py todavía (la integración final es una tarea posterior,
   cuando llegue el modelo v4).

### Tarea 3 — Iteración de mejoras CONTRA la métrica (`feature/optimizacion-tracking`)
Solo cuando la Tarea 1 esté validada. Probar variantes UNA A UNA, medir cada
una contra el banco, conservar solo lo que mejora IDF1/HOTA sin subir los ID
switches, y documentar resultados en un markdown de experimentos:
- Barrido de parámetros (V_MAX, MARGEN, AMBIG_FACTOR, MAX_HUECO, TOL_*,
  umbral y peso del color).
- Kalman con incertidumbre creciente en la Etapa A (la zona de búsqueda de un
  track perdido crece con el tiempo perdido) en lugar de velocidad constante pura.
- Cosido global en grafo (asignación óptima, p. ej. húngaro sobre la matriz
  de costes tracklet→tracklet o formulación min-cost) en vez de goloso.
- Segunda pasada de cosido sobre las identidades ya cosidas (huecos largos).
- Interpolación de huecos DENTRO de una identidad cosida (solo entre dos
  posiciones reales; nunca extrapolar) → mejora métricas de cobertura.
- "Repesca guiada por tracks": donde una identidad predice posición y no hay
  detección en el caché, aceptar detecciones de confianza baja si existieran
  en el caché ampliado (si no las hay, documentar que requiere re-cachear en
  Colab con umbral más bajo y dejar preparada la interfaz).
- Poda de identidades-ruido (muy cortas y sin continuidad) con criterio medible.

### Tarea 4 (si hay tiempo) — Utilidades de visualización (`feature/viz`)
- `src/visualization/`: pintado de vídeo de validación con supervision
  (BoxAnnotator/LabelAnnotator/TraceAnnotator), color estable por identidad,
  export directo a H.264 (usar ffmpeg con -pix_fmt yuv420p; el mp4v de OpenCV
  sale corrupto/verde).

---

## PARTE 4 — PROMPT INICIAL (pegar tal cual en Claude Code)

```
Lee el archivo CLAUDE.md de la raíz para el contexto del proyecto.

Vamos a trabajar la Tarea 1 del briefing (briefing_claude_code.md, Parte 3):
el banco de evaluación de tracking. Antes de escribir código:
1. Explora la estructura del repo y confírmame qué hay en src/ y tests/.
2. Comprueba que existen data/tracking/cache_detecciones_min5_60s.pkl y
   data/annotations/ground_truth_tracking/annotations.xml, y muéstrame un resumen de su contenido
   (nº de frames del caché, nº de tracks del GT y sus labels/atributos).
3. Propónme el diseño de src/evaluation/ (archivos, clases, flujo) y espera
   mi OK antes de implementar.
Trabaja en la rama feature/banco-evaluacion. Después de cada pieza: corre
pytest, enséñame el diff resumido y haz commit con mensaje descriptivo.
```

---

## PARTE 5 — CHECKLIST PREVIA DEL USUARIO (antes de arrancar Claude Code)

- [ ] Copiar de Drive al repo local: `cache_detecciones_min5_60s.pkl` →
      `data/tracking/` y `annotations.xml` → `data/annotations/ground_truth_tracking/`.
- [ ] Verificar que `data/` está en .gitignore (si no, añadirlo ANTES).
- [ ] `git status` limpio (commitear o descartar cambios pendientes).
- [ ] Crear la rama: `git checkout -b feature/banco-evaluacion`.
- [ ] Guardar la Parte 1 como `CLAUDE.md` en la raíz y este documento como
      `briefing_claude_code.md` (estos DOS sí se commitean).
- [ ] Abrir la pestaña Code de la app de Claude sobre la carpeta del repo y
      pegar el PROMPT INICIAL.
- [ ] Regla de oro: revisar cada diff, tests en verde antes de cada commit,
      push a GitHub solo al validar cada tarea completa.
```
