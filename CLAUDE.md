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
3. **Los minutos 0-5 son OTRO RÉGIMEN**: el fit de ese tramo se desvía
   **35 % de la distancia A−B**
   contra un nulo de remuestreo del 2,2 % (16× el ruido), los jugadores
   ocupan otra franja (`y p95` 26 m contra 35 m después), las identidades
   son más cortas (155 contra 213 obs) y solo el 15,9 % de los frames
   tiene el recuento correcto, contra el 42 % en 5-10.
   **Pero NO hay que quitarlos del fit**: medido, hacerlo mueve los
   prototipos 1,8 % contra un ruido propio de 1,1 % y no cambia ni una
   observación (`entrenamiento.desde_s`, existe y está en None). En 20
   minutos ese tramo es una cuarta parte y el resto lo diluye. ⚠️ El
   peligro está en los tramos CORTOS que arranquen en el minuto 0: ahí
   ese régimen sería el 100 % del fit.

Con esos avisos: **de los minutos 5 a 20 el fit NO deriva** (desvíos de
3,7-14,1 %, la distancia a su prototipo BAJA de 0,798 a 0,748 y el margen
A−B SUBE). El minuto 19 se parece al minuto 6 — no al minuto 1.

**Adoptado y en producción** (cada uno con su medición en `docs/`):
- Tracking: perfil **`bytetrack` en las dos patas** (`configs/processor.yaml`
  y `processor_benja_parte_entera.yaml`). `candidato` y `oficial` siguen
  en `perfiles.py` para el banco, pero NO son producción.
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
- **Un interruptor de config que nadie lee es peor que no tenerlo**: da
  una falsa sensación de control. `cota_plantilla.activa: false` estaba en
  los cuatro configs y `perfiles.py` no leía la clave, así que la fusión
  —el fracaso canónico del proyecto— corría en el perfil `candidato`
  creyéndola apagada (106 identidades contra 58). Estaba dormido porque
  producción usa `bytetrack`. Guarda de COMPORTAMIENTO en
  `tests/test_interruptores_de_config.py`: apagar el interruptor tiene
  que cambiar el resultado. ⚠️ Un test de "claves de config sin usar" NO
  lo habría cazado — `activa` sí aparece en el código, solo que en otra
  rama. Es una omisión de CAMINO.
- **Una guarda que CUENTA no puede detectar un fallo de IDENTIDAD.** Se
  adoptó un margen con una guarda que exigía "queda 1 en el tercer
  grupo": quedaba 1, pero no era el árbitro. El aviso debe dispararse
  sobre el EVENTO que cambia la identidad, no sobre el recuento final.
- **Comprobar el proxy antes de creerse el resultado.** Interpolar la
  posición del árbitro daba un "100 % es el fit" redondo; el control de
  color (H=62 S=248 contra H=118 S=56) dijo que no era él.
- **Comprobar que los barridos dan puntos DISTINTOS**, y desconfiar de un
  número imposible: es más fiable que releer un signo. **Y comprobarlo
  ANTES de lanzarlo cuando se pueda**: el barrido de solape de SAHI se
  refutó sin gastar GPU, calculando que la banda de solape mide 57 px y
  el balón 10,5 — los tres puntos habrían salido iguales.
- **UN CRITERIO DE ADOPCIÓN QUE SOLO MIRA LO QUE QUIERES MEJORAR NO VE
  LO QUE ROMPES.** El caso canónico, y no hay otro más claro: **los 47/47
  huecos del fondo que celebramos se cerraron con MARCAS PINTADAS DEL
  CAMPO** — el punto central, el de penalti, una mancha junto al muro. La
  métrica medía exactamente lo que se le pidió, *"¿se cierra el hueco?"*,
  y aun así engañaba, **porque las marcas están justo donde estaban los
  huecos**. Si el criterio hubiera llevado *"y comprueba que lo detectado
  se MUEVE como un balón"*, se habría cazado el mismo día: las marcas dan
  0,02 m por muestra y el balón 0,20-0,30.
  ⇒ Todo criterio lleva dos preguntas, no una: *¿qué arregla?* y **¿qué
  podría estar INVENTANDO?** Y cuando se mide un OBJETO, la segunda
  pregunta tiene una forma concreta: *¿se comporta como ese objeto?* La señal estaba delante
  (1,59 candidatos por frame) y se leyó como ruido inofensivo.
  ⇒ Y vale igual para un DIAGNÓSTICO propio: se concluyó que el cajón
  `otro` eran jugadores recuperables porque se distribuían como A y B,
  sin preguntarse qué otra cosa produce esa distribución. Era el
  árbitro.
- **ANTES DE CULPAR AL SISTEMA, COMPROBAR LA ARITMÉTICA DEL DOMINIO.**
  Se persiguió durante días un "faltan 1,6 personas por frame" que no
  existía: salía de contar **16 personas en el campo cuando en fútbol 7
  son 14** (7 por equipo INCLUYENDO al portero). El GT lo decía desde el
  principio — tiene 14 tracks. Y encima el mismo error hacía parecer
  falsa la hipótesis correcta de Alex, que el recuento corto es del
  encuadre. ⇒ Un número esperado también es una medida, y hay que
  comprobarlo igual que los demás.
- **UNA MÉTRICA DE IGUALDAD EXACTA CASTIGA POR COMBINATORIA, NO POR
  FALLOS.** El "solo el 38,7 % de frames tiene el recuento de B correcto"
  parecía contradecir el 1,2 % de equipo equivocado. No se contradicen:
  cada persona tiene fila a menos de 2 m el **86,5 %** de las veces, y
  exigir que SIETE ocurran a la vez da 0,865⁷ = **36,2 %**, que es lo
  observado. No había ningún fallo escondido. ⇒ Antes de buscar un bug
  detrás de una tasa mala, calcular qué daría el sistema **sin ningún
  fallo extra**. Y no usar igualdad exacta en el informe: la mediana o el
  error por observación dicen lo mismo sin el castigo.
- **UNA MEDIANA POR ZONA NO ES DE LA ZONA SI UNA PERSONA VIVE ALLÍ.** Duró
  un día el "1,29 m de error cerca de la cámara contra 0,41 en el centro".
  **Era el portero de A**: aporta 57 de las 81 observaciones de esa zona
  —porque es el único que la habita— con un sesgo de 1,44 m, y los tres
  jugadores de campo que pasan por allí dan 0,23. Sin él, el error crece
  con la profundidad (0,33 · 0,33 · 0,48 · 0,77 m), que es lo que manda la
  óptica. ⇒ Antes de atribuir un número a una ZONA, contar **cuántas
  personas distintas** lo sostienen. Y el aviso estaba puesto: el error
  cercano era un **SESGO** con todo el intercuartil del mismo lado, y **un
  sesgo tiene dueño; el ruido no**.
- **CONTRASTAR CADA NÚMERO CONTRA LA FÍSICA DEL PROBLEMA, NO SOLO CONTRA
  OTROS NÚMEROS.** Lo anterior lo cazó Alex sin medir nada: cerca de la
  cámara 1 px vale 3 cm, así que 1,29 m son **38 px** y eso no puede ser.
  La homografía quedó exculpada por tres vías (Monte Carlo de ruido de
  clic: la zona cercana es la MÁS estable, 0,09 m contra 0,29 del fondo;
  la envolvente de los 19 puntos; y reajustar sin los clics del borde)
  (`docs/homografia_zona_cercana.md`).
- **UNA MÉTRICA DE "EQUIPO EQUIVOCADO" NO VE LO QUE SE MANDA AL CAJÓN.**
  Solo cuenta filas etiquetadas A o B, así que un jugador mandado por error
  a `otro` (árbitro) o `staff` es INVISIBLE. El catálogo arbitral por
  observación tenía un 78,5 % de aciertos al mover 3.555 filas a `otro`, y el
  21,5 % restante incluía **al portero de A** (camiseta negra, ~500 filas,
  ids 420, 468…). Todo criterio que mueva filas hacia un cajón lleva una
  segunda medida: *¿cuántas de las movidas NO son lo que el cajón dice?*
  (`docs/arbitro_y_baile_de_colores.md`).
- **UN UMBRAL DE SATURACIÓN QUE FALLA NO SE ARREGLA BAJÁNDOLO.** El chaleco
  del árbitro alterna entre S≈248 y S≈72-104 según el minuto (el catálogo
  pide S≥170: acierta el 3 % o el 98 % de los minutos). Bajar el umbral con
  la regla del bin dominante recupera el 93 % del árbitro y captura además
  el 6,4 % de todas las ventanas A/B. Lo que separa es otra medida (la MASA
  en la región), no otro número.
- **UN CAMBIO DE ETIQUETA NO ES SIEMPRE UN FALLO.** En la ventana del GT, 8 de
  los 18 cambios A↔B corrigen una etiqueta y 10 la rompen: casi la mitad es
  la etiqueta ACERTANDO al pasar a otra persona (la identidad mezcla). Un
  suavizado del baile de colores destruiría esos aciertos: es la misma
  lección que el parpadeo de posición.
- **UN RECORTE SE SACA CON `posicionar_en_frame()`, NUNCA CON `cap.set`.**
  En este mp4 pedir el frame 9750 aterriza en el 10077 (11 s), y las cajas
  salen correctas sobre el fotograma equivocado. Ya estaba documentado en
  `processor.py` y aun así se volvió a caer en ello en un script de
  trabajo. El síntoma que lo delata: cajas sobre césped vacío.
- **El sesgo del portero cercano era de la REGLA**: el GT del track 6 está
  en el PECHO (el dorsal), no en los pies, en las 20 muestras. Lo real es
  otra cosa: **está cortado por el borde inferior en 47 de 57** y el
  sistema lo pone ~1,4 m lejos de su portería (`docs/portero_cortado.md`,
  BACKLOG 25). No se agacha nunca.
- **UN CRITERIO DE EMPAREJADO ES UN PARÁMETRO, NO UNA VERDAD.** Sobre los
  mismos 814 casos del GT: "pie a <20 px" da 1,62 ausencias por frame,
  IoU≥0,3 da 4,65 y "el centro cae dentro de la caja" da 0,45. El GT del
  benjamín es una PLANTILLA FIJA de 40×18 px, así que su "pie" no es el
  pie de un jugador cercano a la cámara (47 px de desfase en el portero,
  que salía "sin detectar el 100 % de las veces" siendo visible), y el
  IoU castiga que las cajas del detector sean 1,47× más altas. Antes de
  leer una tasa de fallo, medir el SESGO del emparejado con parejas que
  no estén seleccionadas por ese mismo criterio.
- **Un test de mutación tiene que verificar que el fichero CAMBIÓ** antes
  de interpretar el resultado. Una mutación cuyo `str.replace` no
  coincide es un no-op, y entonces "7 passed" no dice que el código esté
  bien: dice que no has probado nada. Es el ✓ engañoso de siempre, y la
  misma trampa que ya nos tendió black comiéndose un `replace` en el
  generador de la hoja de GT.
- **Mirar el ÍNDICE antes de commitear** (`git status`), no lo que
  acabas de añadir. Un `git add -A` que el hook aborta deja los ficheros
  en el índice. **Y mirar el REMOTO antes de decir que algo está
  subido**: la rama llegó a acumular 27 commits sin pushear, y el
  síntoma le llegó a Alex como "el fichero no existe".
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
- **POR QUÉ LAS REGLAS DE POSICIÓN AGUANTAN Y LAS DE COLOR SE ROMPEN.**
  No es suerte, y explica meses de resultados:

  > **Dos personas se funden en una identidad porque estaban CERCA.** Así
  > que la mediana de POSICIÓN de una identidad contaminada sigue cayendo
  > donde estaban las dos y sigue siendo plausible. El COLOR no tiene esa
  > propiedad: mezclar verde flúor con naranja da un tono que **no es de
  > nadie**, y que además cae justo entre los dos prototipos de equipo.

  De ahí que las reglas posicionales valgan más que el clasificador, que
  el voto de color por identidad fuera sesgado, y que el catálogo
  arbitral fallara sobre una identidad de 3.187 recortes. Hay **siete**
  reglas que deciden sobre medias de identidad y el riesgo de cada una
  sale de esta distinción (`docs/reglas_sobre_medias_de_identidad.md`).
- **NO ES CANTIDAD, ES PUREZA.** El catálogo arbitral no fallaba por falta
  de muestra: el `id 292` tiene **3.187 recortes** y no dispara, porque
  mezcla al árbitro con jugadores. Aplicado POR OBSERVACIÓN, el recuento
  correcto del equipo B pasa de 13 % a 43 % con **un** jugador sacrificado
  de 814 (los tres intentos anteriores morían a 8 jugadores por árbitro).
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
