# Tactical Lens — contexto para Claude Code

## Qué es este proyecto
SaaS de análisis táctico por computer vision para fútbol amateur (empresa
ACIIES; es también el TFM de Alex). Pipeline: vídeo → corrección de
distorsión → detección (YOLOv8 + SAHI) → tracking en METROS → clasificación
de equipos → métricas colectivas → informe HTML.

Caso objetivo (difícil a propósito): cámara fija barata, jugadores de
15-40 px, equipaciones idénticas entre compañeros. El producto debe ser
100 % AUTOMÁTICO. Mercado inicial: **fútbol 7 de base** — por eso el
benjamín es la pata que manda y Villaviciosa (F11 panorámico) es el caso
difícil que espera.

**Alex es PRINCIPIANTE en ingeniería de software**: explicar decisiones,
código claro y comentado en español.

---

## Estado (27-ago-2026)

**Se ha procesado y validado UNA PARTE ENTERA** del benjamín (20 min,
11.989 frames, 211.282 detecciones, un solo fit de color). El sistema
aguanta la escala:

| | 5 min | 20 min |
|---|---|---|
| equipo equivocado (casado 1-a-1, radio 2 m) | 1,2 % | **1,2 %** |
| deriva de los minutos 5-20 | — | **plana** |

⚠️ **Tres avisos que costó una verificación adversarial, y sin los que
estos números se leen mal:**

1. **El casado tiene que ser 1-a-1.** Con "la fila más cercana" salía
   4,0 %, pero el 79 % de ese error estaba sobre filas que DOS personas
   del GT reclamaban a la vez: se le apuntaba al clasificador un fallo de
   DETECCIÓN. Con asignación óptima, 1,2 %. Y el NIVEL depende del radio
   (3,1 % a 1,0 m · 6,5 % a 5,0), así que un porcentaje sin radio no
   significa nada.
2. **El GT del benjamín cubre 29,5 s** (frames 9750-10635), el 2,5 % de
   la pasada. Comparar "5 min contra 20 min" mide el efecto de ENTRENAR
   EL FIT con más datos sobre la MISMA ventana del minuto 5. **No dice
   nada de los minutos 6-20.** Ahí solo hay señales estructurales sin GT.
3. **Los minutos 0-5 son OTRO RÉGIMEN**, y hay que excluirlos o tratarlos
   aparte: el fit de ese tramo se desvía **35 % de la distancia A−B**
   contra un nulo de remuestreo del 2,2 % (16× el ruido), los jugadores
   ocupan otra franja (`y p95` 26 m contra 35 m después), las identidades
   son más cortas (155 contra 213 obs) y solo el 15,9 % de los frames
   tiene el recuento correcto, contra el 42 % en 5-10.

Con esos avisos: **de los minutos 5 a 20 el fit NO deriva** (desvíos de
3,7-14,1 %, la distancia a su prototipo BAJA de 0,798 a 0,748 y el margen
A−B SUBE). El minuto 19 se parece al minuto 6 — no al minuto 1.

**Adoptado y en producción** (cada uno con su medición en `docs/`):
- Tracking: perfil `bytetrack` en el benjamín; `candidato` en el F11.
- Clasificación: fit de color con `n_init: 50`, orden de reglas
  árbitro → porteros → un_solo_arbitro → staff, `etiquetar_por_observacion`
  (ventana 1,5 s, solo benjamín).
- **Portero por CONJUNTO de fragmentos** con presencia sobre la unión
  (`docs/portero.md`). Invariante a la escala: 1,30 m a 60 s y 1,25 m a
  5 min, donde antes daba 1,30 y 5,30.
- Staff lento, exclusividad de árbitro, plausibilidad física, checkpoint
  con reanudación en el modo full, atajo de distorsión nula.

**Lo siguiente**: el frente del jugador se cierra aquí. Pasa al **BALÓN**,
que es lo que falta para el informe (`src/balon/tracking_balon.py` ya
tiene balón activo, fases aéreas y contactos; falta pasarlo por la parte
entera, que es GPU). Ideas de producto pendientes en `BACKLOG.md` 13 y 14.

### Dónde está cada cosa

| | |
|---|---|
| `src/tracking/perfiles.py` | composición única banco↔producción (`bytetrack`, `oficial`, `candidato`) |
| `src/tracking_data/processor.py` | end-to-end v2: modos `full` (GPU) y `desde_cache`; checkpoint y reanudación |
| `src/team_classification/` | `color_classifier` (fit), `pipeline_equipos` (orden de reglas), `porteros`, `arbitro`, `staff` |
| `src/balon/tracking_balon.py` | balón activo, fases aéreas, contactos |
| `src/report/` | `replay_tactico` (pizarra), `informe_v2`, `analisis_ia` (el LLM SOLO redacta desde números ya calculados) |
| `src/evaluation/` | banco contra el GT de CVAT (métricas propias + TrackEval) |
| `docs/` | una medición por fichero, negativos incluidos; `experimentos_tracking.md` es el registro largo |
| `BACKLOG.md` | ideas de producto con su comprobación previa pendiente |

---

## LA PRIORIDAD UNO: la ASOCIACIÓN

**Es el 100 % del margen medible.** Medido con oráculos contra el GT
(`docs/oraculos.md`):

| variante | centroide | anchura |
|---|---|---|
| sistema | 1,55 m | 0,93 m |
| + anclaje perfecto | 1,61 m | 1,03 m |
| **+ asociación perfecta** | **0,42 m** | **0,33 m** |

Y no está donde creíamos: sin re-entrada la pureza sube solo de 80,1 % a
84,4 %, así que **el 16 % restante se contamina DENTRO del seguimiento
continuo**, en los cruces. Hay que **partir y luego unir**.

Todo lo demás acaba desembocando aquí:

- **UNA PERSONA ES N IDENTIDADES.** El portero se parte en 5 y 21
  trozos sobre 20 minutos; el árbitro, en 10. Las reglas que coronaban a
  UNO se rompían al alargar el tramo. Con la restricción física de que
  **dos trozos simultáneos son un duplicado, no una continuación** (una
  persona no está en dos sitios a la vez).
- **El árbitro es un problema de ASOCIACIÓN disfrazado de color**
  (27-ago-2026). En un recorte suelto NO EXISTE: sus observaciones están
  a 0,884 de su prototipo y las de jugador a 0,936 — solapadas. Su verde
  flúor **solo aparece al promediar ~40 recortes**. Por eso solo es
  alcanzable con identidades largas y puras, y por eso llegará gratis
  cuando la asociación mejore. Línea cerrada hasta entonces
  (`docs/arbitro.md`).
- Las identidades con reparto 58/42 entre A y B no son fallos de color:
  **contienen a más de una persona**.

---

## Principios (cada uno costó una medición)

**Sobre el método**

- **Una herramienta de diagnóstico que RESUME puede mentir sobre el
  sistema que diagnostica.** Ya ha pasado cuatro veces: el "✓" de un
  caché vacío, el tick del balón, el `tail` que se comió un crash de
  OpenCV, y la pizarra pintando la MODA de la identidad en vez de la
  etiqueta del instante (`docs/pizarra_colapsaba.md`). Guarda viva en
  `tests/test_renderizadores_no_colapsan.py`.
- **Una guarda que CUENTA no puede detectar un fallo de IDENTIDAD.** Se
  adoptó un margen con una guarda que exigía "queda 1 en el tercer
  grupo": quedaba 1, pero no era el árbitro. El aviso debe dispararse
  sobre el EVENTO que cambia la identidad, no sobre el recuento final.
- **Comprobar el proxy antes de creerse el resultado.** Interpolar la
  posición del árbitro daba un "100 % es el fit" redondo; el control de
  color (H=62 S=248 contra H=118 S=56) dijo que no era él.
- **Comprobar que los barridos dan puntos DISTINTOS**, y desconfiar de un
  número imposible: es más fiable que releer un signo.
- **Mirar el ÍNDICE antes de commitear** (`git status`), no lo que
  acabas de añadir. Un `git add -A` que el hook aborta deja los ficheros
  en el índice.
- **Documentar los negativos.** Media semana se ahorra leyendo por qué
  algo ya se descartó.

**Sobre las medidas**

- **El suelo de ruido no es una barra de error.** Un A/B determinista
  sobre el mismo caché no tiene ruido; lo que dice es que la métrica es
  FRÁGIL. El test correcto es repetir el A/B sobre entradas perturbadas y
  comprobar que el SIGNO aguanta (`docs/suelo_de_ruido.md`).
- **Elegir el CENTRO de la meseta, no el valor que va justo.** Si no hay
  meseta común a las dos patas, el parámetro no existe.
- **Los umbrales van pegados al DETECTOR.** Al cambiarlo hay que
  re-barrer la asociación entera.
- **Un GT indexado por id del sistema caduca**: 27 de 30 identidades del
  mini-GT eran otra persona tras cambiar de detector. **Indexar por
  posición y tiempo.**
- **Medir cada cambio por separado contra LAS DOS patas** (benjamín y
  Villaviciosa), y no adoptar nada que degrade alguna.

**Sobre dónde está el valor**

- **Las reglas posicionales valen MÁS que el clasificador.** Color puro:
  8,7 m de centroide. Con las reglas de portero, staff, árbitro y
  `solo_cercanos`: 1,55 m. El valor está en el **conocimiento del
  dominio** —campo, áreas, banquillo, reglamento— no en la visión. Antes
  de mejorar un modelo, preguntarse qué se sabe de fútbol que el sistema
  todavía no usa.
- **El voto mayoritario no era robusto, era SESGADO.** Etiquetar por
  observación gana +6,2 puntos incluso en identidades PURAS. La robustez
  de un promedio depende de que lo que promedia no esté sesgado.
- **Dos señales débiles que juntas son fuertes.** Ninguna separa sola,
  pero cada impostor falla al menos una. Es la forma del staff lento, de
  las dos salvaguardas del portero y de `un_solo_arbitro`.
- **Actuar solo donde hay riesgo**: no aplicar un criterio ruidoso en
  todas partes, solo decidir mejor donde el sistema ya está adivinando.

---

## Vías CERRADAS, con la medición que las cerró

| vía | por qué se cerró |
|---|---|
| **Detección como palanca** | El v4 (mAP50 0,944 vs 0,900) no movió la aguja del producto. El esfuerzo de etiquetado se paró el 17-ago. |
| **Anclaje por pose** | El oráculo de anclaje perfecto EMPEORA el centroide (1,55 → 1,61 m). Un sesgo sistemático mueve el bloque pero no lo deforma. |
| **Tercer grupo por COLOR** (3 intentos) | El árbitro no está lejos de los prototipos en un histograma HS de 15-40 px. |
| **Puerta de distancia al prototipo** | Por identidad: Villaviciosa 0,718 → 0,682. Por observación (re-medida el 27-ago): 8 jugadores perdidos por cada árbitro cazado. |
| **`arbitro.margen_equipo: 0.68`** | Adoptado y revertido el mismo día: la ventana se mueve con el detector (0,62-0,75 en v3, ≤0,50 en v4). Hoy en 0,0. |
| **`cota_plantilla`** | Fusiona hasta llegar a ~23 y confunde identidades. Fuera del perfil por defecto. |
| **Regla de portero por ÁREA** | Corona a quien más observaciones acumula dentro del área: cuenta para decidir QUIÉN. Sustituida por `ultimo_hombre`. |
| **Suavizar el parpadeo** | Tres formas, tres negativos: el suavizado ya está en su óptimo (1,5 s). Y **el parpadeo es la señal de que la asociación acaba de fallar: taparlo esconde el fallo.** |
| **Feature de color en `float32`** | Ahorraría disco pero movería la entrada del KMeans, que es la pieza frágil. |

---

## Convenciones
- Comentarios y docstrings en **español**. Nombres descriptivos.
- Formato: Black + Flake8 `--max-line-length=100` (pre-commit hooks).
- Tests con pytest en `tests/`. **Después de CADA cambio: correr pytest**
  y no dar nada por terminado si falla.
- Configuración externalizada (umbrales en un YAML), nunca números
  mágicos hardcodeados.
- Logging con el módulo `logging` (no prints) en `src/`.
- Rama `experimento/asociacion-global`. **Nada se mergea a `main` sin el
  OK de Alex.** Nada se adopta como default sin su OK, **salvo** que
  mejore TODAS las métricas a la vez sin degradar ninguna.
- Si una vía no paga en DOS intentos, se abandona.

## Qué NO hacer
- NO commitear datos, vídeos, modelos (.pt), cachés (.pkl) ni exports de
  CVAT. Viven en Google Drive.
- NO tocar los notebooks de `notebooks/`: son el registro de experimentos.
- NO sustituir el tracker en metros por uno en píxeles de librería: el
  tracking en coordenadas de campo es la ventaja diferencial.
- NO usar boxmot (rompió el entorno). Fijar `numpy<2.1` y `scipy<1.14`.
- **Licencias**: nada AGPL (YOLO-pose, boxmot) y nada entrenado con
  SoccerNet (CC BY-NC). Código permisivo con pesos NC ⇒ hay que reentrenar.
- La **GPU no está en este Mac**: SAHI, YOLO y re-detección se hacen en
  Colab. Aquí se trabaja contra los cachés.

## Datos de trabajo (Alex los copia de Drive a `data/`, gitignored)
- `data/tracking_benja/cache_detecciones_benja_p1.pkl` (+ `_colores_`, 418
  MB): **la parte entera**, 11.989 frames, t=0-1200 s.
- `data/tracking_benja/cache_*_benja.pkl`: tramo de 60 s (min 5-6), sobre
  el que están medidas casi todas las métricas del banco.
- `data/tracking/cache_*_v4pre.pkl`: Villaviciosa, tramo de 60 s.
- Formato del caché: `{"cache": [{"frame_idx", "t", "dets": [(mx, my, x1,
  y1, x2, y2, conf)]}], "fps", "sample", "wh"}`. `(mx, my)` en METROS.
- GT: `data/annotations/gt_benja/annotations.xml` (offset 9750, paso 15;
  **NO anota al árbitro**) y `data/annotations/ground_truth_tracking/`
  para Villaviciosa (offset 7500).
- Homografías en el repo: `data/calibracion_benja/homografia_benja.npy`.
