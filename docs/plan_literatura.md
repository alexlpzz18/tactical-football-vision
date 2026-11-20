# Métodos de la literatura frente a lo nuestro (plan, 19-nov-2026)

Encargo de Alex: probar seis métodos de SoccerNet 2025-2026 y de artículos de seguimiento deportivo,
**solo para comparar**. Rama `literatura-sota` (sale de `alevinb-preparacion`). Reglas del encargo:

- no se toca `main`, ni los YAML de producción, ni `data/`; las salidas van a carpetas nuevas de `outputs/`;
- con los interruptores apagados, la salida tiene que ser **idéntica byte a byte a la de `main`**, y se
  comprueba antes de dar ningún resultado;
- nada se fusiona: al final, una tabla de cada método frente a lo actual, y decide Alex.

Y las del proyecto: criterio escrito antes de medir, dos intentos por ruta, todo detrás de interruptores,
y no repetir una ruta cerrada de CLAUDE.md sin un argumento nuevo escrito antes.

## Licencias (leídas en los repositorios el 19-nov)

| método | código | pesos | ¿al producto? |
|---|---|---|---|
| Deep-EIoU | **sin licencia** (no hay fichero LICENSE) | sin términos | **no se copia código**: implementación propia de la idea del artículo |
| GTA-link | MIT | OSNet entrenado en SportsMOT, sin términos | la idea, con código propio; sin sus pesos |
| RTMPose (MMPose) | Apache-2.0 | sin restricción declarada | sí, revisando la licencia del modelo concreto |
| SigLIP base | Apache-2.0 (tarjeta del modelo) | Apache-2.0 | sí |
| WASB-SBDT | MIT | **sin términos**; el entrenamiento figura como «TBA» | solo con pesos entrenados por nosotros |

## Cómo se mide (igual para todos)

- **Patas con GT**: benjamín (60 s, GT de 30 s), alevín A / «Villaviciosa» (60 s, GT de 30 s) y benjamín
  parte entera (20 min; el GT cae en su minuto 5).
- **Contra el GT** (casado 1-a-1 a ≤ 2 m, `scripts/banco_lit.py`):
  - recall (personas del GT casadas);
  - **IDF1 global** y **dentro de cada equipo**;
  - **fragmentación**: identidades del sistema por persona del GT;
  - **intercambios entre rivales en cruces**: una identidad del sistema que pasa de seguir a la persona P a
    seguir a la persona Q, con P y Q de equipos distintos y a ≤ 2,5 m en ese momento. Se cuentan también
    entre compañeros;
  - equipo equivocado, centroide y anchura (`banco_mision`).
- **Pizarra** (`linea_base_mision`): cambios de color por minuto y apariciones/desapariciones por minuto en
  el tramo **14:00-15:30 del benjamín** (840-930 s de la parte 1) y en el alevín B (sin GT).
- **Control del instrumento**: la variante «base» de cada pata tiene que dar las cifras ya conocidas (el
  benjamín, 1,245 % de equipo equivocado; el tramo 14:00-15:30, 27,3 apariciones/min).

## 1. Deep-EIoU sin reidentificación, en lugar de ByteTrack (CPU)

- **Qué**: asociación por **IoU de cajas ampliadas**, en rondas en las que la ampliación crece (0,7 y
  0,8), sobre la última caja de cada pista (**sin Kalman**). Detecciones altas y bajas como en ByteTrack.
  Interruptor `bytetrack.asociacion: eiou` (por defecto, ByteTrack).
- **Argumento nuevo frente a lo cerrado**: las rutas cerradas de asociación cambiaban la señal (apariencia
  en el camino B, color en B1) o cortaban después (B2). Esta no añade señal: cambia la **geometría del
  emparejamiento**. Con jugadores de 15-40 px el IoU entre fotogramas se hunde, y por eso hoy ByteTrack
  corre con `umbral_emparejamiento: 0.995` (acepta IoU de 0,005): en un cruce elige entre solapes casi
  nulos y su Kalman predice con velocidades de cajas diminutas. La caja ampliada da solape graduado a
  distancia, y sin Kalman la pista no deriva en el cruce. Lo que se cambia es la etapa de asociación en
  píxeles, igual que ByteTrack: las posiciones siguen en metros.
- **Criterio (el de Alex)**: IDF1 global sube **≥ 5 puntos** sin bajar el recall, y los intercambios entre
  rivales en cruces bajan **≥ 30 %**, en el benjamín y en el alevín A. Se informa también de la pizarra y
  de la exactitud de equipo (no pueden empeorar más de 0,5 puntos).
- **¿Qué podría estar inventando?** Una caja ampliada empareja a distancia: puede unir a dos personas que
  pasan cerca. Control: la fragmentación y los intercambios entre COMPAÑEROS no pueden subir.

## 2. Postproceso global tipo GTA-link (CPU)

- **Qué**: (a) **partir** cada trayectoria donde la etiqueta de equipo por observación cambia de forma
  sostenida (≥ 1,5 s seguidos del otro equipo); (b) **unir** los trozos con un **agrupamiento jerárquico
  global** dentro de cada equipo: nunca dos trozos que se solapen en el tiempo (una persona no está en dos
  sitios), y solo si cabe físicamente, Δd ≤ v_max·Δt + margen. La apariencia (SigLIP) solo para cajas de
  más de 60 px, si existe y si ayuda. Interruptor `fichas.gta`.
- **En qué se diferencia de lo cerrado**:
  - «Cortar en cruces y reenlazar» (B2, con y sin color) cortaba en **cada cruce** (IoU > 0,1) y
    fragmentaba; aquí solo se corta donde la etiqueta de equipo, decidida sobre ventanas de 1,5 s, cambia
    durante ≥ 1,5 s;
  - «Corte por color sostenido» (`corte_color`) cortaba por **distancia de color de recortes sueltos** al
    modelo de la pista; aquí la señal es la etiqueta ya decidida del equipo;
  - el reenlace de B2 y el de mi H3 emparejan **de dos en dos** (sucesor inmediato); el jerárquico une
    cadenas enteras y puede saltar por encima de un trozo intermedio, con la restricción de solape como
    regla dura de todo el grupo.
- **Criterio (el de Alex)**: apariciones/min en la pizarra bajan **≥ 50 %** (tramo 14:00-15:30 del
  benjamín y alevín B) **sin bajar el IDF1 dentro de cada equipo** (benjamín y alevín A). Equipo
  equivocado: no más de +0,5 puntos.
- **¿Qué podría estar inventando?** Uniones entre personas distintas del mismo equipo: el IDF1 dentro del
  equipo es justo lo que lo ve, y además los saltos de la pizarra no pueden subir.

## 3. Punto de suelo por pelvis (pose; GPU o CPU en ventanas)

- **Qué**: modelo de pose ligero (RTMPose vía `rtmlib`, Apache-2.0) sobre cada caja. Punto de suelo =
  (x de la pelvis, y de los tobillos), en vez del centro del borde inferior de la caja.
- **Argumento nuevo frente a «anclaje por pose» (cerrado)**: aquel cierre midió el oráculo de anclaje
  perfecto contra el **centroide**, y un sesgo sistemático mueve el bloque sin deformarlo. Aquí lo que se
  mide es el **temblor** (el borde inferior de la caja salta 4-6 px y lejos 1 px son 0,38 m: el 97 % de los
  saltos del F11 venía de ahí) y el error por jugador.
- **Criterio**: en jugadores parados (≤ 0,5 m/s según el GT) del tercio lejano, el temblor de posición
  baja ≥ 30 %; el error contra el GT no sube en ninguna franja; cobertura (cajas con pose fiable) ≥ 80 %.
  Si cumple, se repite «fichas por equipo en metros» (cerrada) con este punto de suelo como argumento
  nuevo: aquella ruta murió porque el pie sin suavizar tiembla metros en el fondo.

## 4. Recortes por franjas para el tercio lejano del F11 (GPU)

- **Qué**: además de los 15 recortes de SAHI, recortes más pequeños solo en la franja lejana (a imgsz 640,
  ampliación ×2-×3 en vez de ×1,07).
- **Criterio**: recall de jugadores de < 20 px en el GT del alevín A sube ≥ 15 puntos, falsos positivos
  por fotograma suben ≤ 10 %, y se informa de inferencias por fotograma (coste).
- Ruta «detección como palanca» cerrada en agosto: el argumento nuevo es que aquella medía el mAP global
  de un modelo nuevo; aquí se ataca solo la franja donde se pierde el 35 % de las personas.

## 5. Equipos con SigLIP + UMAP + K-means (CPU en ventanas; GPU para partidos enteros)

- **Qué**: embedding SigLIP del centro del jugador → UMAP 3D → K-means de 2 grupos (el método de
  `roboflow/sports`), comparado con el histograma actual.
- **Argumento nuevo frente a DINOv2 (cerrado el 12-nov)**: otro modelo (SigLIP, entrenado con texto),
  otra reducción (UMAP antes de agrupar) y recorte del centro del cuerpo.
- **Criterio**: el error de equipo baja en el F11 (alevín A, y el alevín B con la hoja de Alex cuando
  esté) y no sube en el benjamín.

## 6. Balón con WASB (GPU)

- **Qué**: red de mapas de calor de 3 fotogramas (HRNet, 512×288), entrenada con nuestras etiquetas.
- **Bloqueo conocido**: el entrenamiento figura como «TBA» en el repositorio y sus pesos no tienen
  licencia declarada. Sin código de entrenamiento oficial, hay que escribirlo, y hacen falta etiquetas
  del balón en juego (la hoja de 40 fotos decide si merece la pena etiquetar).
- **Criterio** (cuando haya etiquetas): detección del balón cerca de la cámara ≥ YOLO actual + 10 puntos y
  balones inventados ≤ los del YOLO actual.

---

## Estado al cortar (19-nov, límite de uso)

- **Hecho y commiteado** (`761082c`): plan, licencias, métodos 1 (EIoU, código propio) y 2 (GTA) tras
  interruptores, banco con IDF1/fragmentación/intercambios, y la comprobación de identidad con `main`:
  **idéntica byte a byte** en Villaviciosa, benjamín 60 s y benjamín entero.
- **Sin commitear todavía** (falta pasar la suite): `scripts/banco_mision.py` (`--configs-de`),
  `scripts/lit_siglip_equipos.py`, `lit_evaluar_equipos.py`, `lit_pose_suelo.py`, `lit_evaluar_pose.py`,
  `lit_franjas_lejanas.py`.
- **Corriendo en segundo plano** (salidas en `outputs/literatura/`): banco de los métodos 1 y 2
  (`banco/resultados.json`), embeddings SigLIP de las dos ventanas (`siglip/`), pose de las dos ventanas
  (`pose/`). Control del banco OK: «lo actual» da 27,3 apariciones/min en el tramo 14:00-15:30.
- **Método 4, chequeo de 3 frames**: corre, pero el CONTROL NO PASA todavía: la variante «produccion» en
  CPU reproduce solo el 85,9 % de las cajas del caché de producción (hecho en GPU). Hay que entender esa
  diferencia (¿CPU frente a CUDA, versión de sahi/ultralytics, modelo?) antes de leer nada de recall.
- **Siguiente**: evaluar SigLIP (`lit_evaluar_equipos.py`) y pose (`lit_evaluar_pose.py`) cuando acaben;
  leer el banco; resolver el control del método 4; método 6 bloqueado (sin código de entrenamiento oficial
  ni etiquetas del balón en juego). Correr con `OMP_NUM_THREADS` limitado: con todo a la vez la carga
  llegó a 182.

## Resultados de los intentos 1 y criterio de los intentos 2 (escrito ANTES de correrlos)

| | benjamín IDF1 · interc. rivales en cruce · equipo mal | alevín A IDF1 · interc. · equipo mal | apariciones/min (tramo 14:00-15:30 · alevín A · alevín B) |
|---|---|---|---|
| actual | 0,628 · 20 · 1,245 % | 0,493 · 67 · 23,6 % | 27,3 · 96,2 · 70,4 |
| EIoU (artículo, e = 0,7 + 0,1) | 0,653 · 27 · 2,22 % | 0,513 · 73 · 24,4 % | 17,3 · 77,1 · 66,8 |
| GTA (racha 1,5 s, hueco 3 s) | 0,646 · 12 · 1,245 % | 0,502 · 69 · 23,6 % | 27,3 · 58,1 · 99,7 |

- **Método 1, intento 1: NO CUMPLE** (IDF1 +2,5 y +2,0 puntos, pedía +5; los intercambios entre rivales
  SUBEN). **Intento 2**: la ampliación del código público, w·(2 + 2e) (`eiou.variante: codigo`), con el
  mismo criterio.
- **Método 2, intento 1: NO CUMPLE** (apariciones −40 % en el alevín A, sin cambio en el tramo del
  benjamín y SUBEN en el alevín B). Sí baja mucho el parpadeo de color (benjamín 45 → 9/min). El
  mini-GT del alevín B no vale con GTA: renumera las fichas y el casado del mini-GT busca por número.
  **Intento 2**: cortar menos y unir más: racha sostenida de 3 s (en vez de 1,5) y hueco de unión de
  5 s (en vez de 3), con el mismo criterio.

### Método 3, intento 1: NO CUMPLE (y el porqué)

Punto de suelo = (x de la pelvis, y de los tobillos), sobre las MISMAS detecciones que producción:

| | error mediano contra el GT (cerca · medio · lejos) | temblor de parados (cerca · medio · lejos) | con pose fiable |
|---|---|---|---|
| benjamín, producción | 1,23 · 0,38 · 0,59 m | 0,087 · 0,209 · 0,161 m | — |
| benjamín, pelvis | 1,30 · **1,63 · 2,50 m** | 0,098 · 0,222 · 0,152 m | 86 % |
| alevín A, producción | 0,41 · 0,76 · 0,74 m | 0,216 · 0,195 · 0,396 m | — |
| alevín A, pelvis | 1,06 · 1,27 · 0,78 m | 0,220 · 0,280 · 0,480 m | **31 % (lejos: 3,4 %)** |

- No es un fallo del código: los puntos caen donde deben (caderas al 50 % del alto de la caja, tobillos al
  87 %). Es un SESGO de la definición: el tobillo está un 13 % del alto por encima del borde inferior de
  la caja (la caja incluye la zapatilla y margen), y proyectarlo pone al jugador metros más lejos.
- **Y el dato que cierra el F11**: en el tercio lejano del alevín A la pose solo es fiable en el 3,4 % de
  las detecciones. Justo donde tenía que bajar el temblor, el modelo no ve a jugadores de 15-20 px.
- **Intento 2 (criterio igual, escrito antes)**: quitar el sesgo vertical. Dos variantes, y vale la mejor:
  (a) x de la pelvis e y del borde inferior de la caja (solo corrige el lateral); (b) y de los tobillos
  más el desfase mediano tobillo → borde inferior, medido en la propia pata (en altos de caja).

### Método 3, intento 2: NO CUMPLE. Ruta cerrada (no se repite «fichas por equipo»)

| temblor de parados en el tercio lejano | producción | (a) x pelvis, y borde | (b) y tobillos + desfase (12,5 % del alto) |
|---|---|---|---|
| benjamín | 0,161 m | 0,158 m (−2 %) | 0,145 m (−10 %) |
| alevín A | 0,396 m | 0,396 m (0 %) | 0,468 m (+18 %) |

Error contra el GT: (a) igual que producción en todas las franjas; (b) mejora el fondo del benjamín
(0,59 → 0,54 m) y empeora las demás. El criterio pedía −30 % de temblor lejano sin empeorar ninguna
franja: ninguna variante llega. **La causa en el F11 es de cobertura**: la pose solo es fiable en el
3,4 % de las detecciones lejanas (jugadores de 15-20 px), así que allí casi siempre se cae al punto de
producción. Como la condición para repetir «fichas por equipo en metros» era que este punto mejorase,
esa ruta no se reabre.

## Intentos 2 de los métodos 1 y 2: NO CUMPLEN. Rutas cerradas

| | benjamín IDF1 · interc. rivales · equipo mal | alevín A IDF1 · interc. · equipo mal | apariciones/min (tramo · alevín A · alevín B) |
|---|---|---|---|
| actual | 0,628 · 20 · 1,245 % | 0,493 · 67 · 23,6 % | 27,3 · 96,2 · 70,4 |
| EIoU (código, w·(2+2e)) | 0,638 · 25 · 2,47 % | 0,497 · 73 · 25,7 % | 16,0 · 70,1 · 53,0 |
| GTA 2 (racha 3 s, hueco 5 s) | 0,666 · 15 · 1,245 % | 0,505 · 69 · 23,6 % | 30,0 · 82,1 · 108,8 |

- **EIoU**: ninguna de las dos ampliaciones sube el IDF1 5 puntos ni baja los intercambios entre
  rivales; las dos EMPEORAN el equipo equivocado del benjamín (1,2 → 2,2-2,5 %). Lo que sí hace es bajar
  apariciones (menos pistas que mueren), a costa de pegar pistas a la persona equivocada.
- **GTA**: sube el IDF1 global (benjamín +3,7 puntos) y baja el parpadeo de color (45 → 9-21/min en el
  benjamín, 123 → 48-83 en el alevín B), pero las apariciones SUBEN: cortar por equipo crea más trozos de
  los que el agrupamiento une. Su acierto de equipo es por construcción el de «actual» (no cambia
  etiquetas, solo fichas).
- **Método 4, control**: con el criterio ya validado (IoU ≥ 0,9), la CPU reproduce el 85,9 % de las cajas
  del caché de producción (hecho en GPU) en Villaviciosa; en el benjamín, en octubre, fue el 100 %. La
  diferencia probable es la corrección de lente sobre fotogramas decodificados de otra forma. Por la
  regla del control, las cifras ABSOLUTAS de la CPU no valen como «producción»; la comparación RELATIVA
  (las dos variantes por el mismo camino) sí, y se mide así. Corregido además un sesgo de mi script: solo
  la variante con franjas pasaba por una segunda fusión, y eso le bajaba los falsos positivos.

## Método 5 (SigLIP + UMAP + K-means), intento 1: NO CUMPLE (mejora mucho el F11, empeora el F7)

Error de equipo contra el GT, mismas detecciones y mismo voto para los dos métodos
(`lit_evaluar_equipos.py`; clasificador HS e identidades de una pasada de producción con configs de
`main`):

| | por recorte: HS · SigLIP | con voto de 1,5 s: HS · SigLIP |
|---|---|---|
| alevín A (F11) | 24,8 % · **13,2 %** | 27,0 % · **12,6 %** |
| benjamín (F7) | **7,1 %** · 10,0 % | **6,1 %** · 9,8 % |

Criterio: baja en el F11 y no sube en el benjamín. Baja a la mitad en el F11, pero sube 3,7 puntos en el
benjamín. **Intento 2 propuesto (no corrido)**: que cada partido elija entre HS y SigLIP con la
consistencia física ya construida (`seleccion_feature.py`: una persona no cambia de equipo entre
profundidades), en vez de un método único. Es una vía con argumento propio: la premisa ya se cumplió con
el brillo en las tres patas.

## Método 4, primera medida completa: INVÁLIDA (fallo mío, corregido)

Las tres variantes daban cifras idénticas hasta el decimal. Causa: `get_prediction` de SAHI devuelve las
cajas en coordenadas del recorte, y no las desplacé al fotograma; las cajas extra caían en la esquina
superior izquierda (fuera del campo: ni casaban ni contaban como falso positivo). Corregido con
`get_shifted_object_prediction()`; en un frame de control la variante ya añade 2 cajas dentro de la
banda. El resultado inválido se conserva como `outputs/literatura/franjas/resultado_INVALIDO_sin_desplazar.json`.

## Método 4 (recortes extra en la franja lejana), intento 1 corregido: NO CUMPLE

100 frames del GT del alevín A, en CPU. Control: la CPU reproduce el 83,2 % de las cajas del caché de
producción (hecho en GPU): las cifras absolutas no son «producción», la comparación entre variantes sí
(todas por el mismo camino y el mismo postproceso).

| | recall < 20 px (418) | 20-30 px (1.238) | ≥ 30 px (562) | falsos positivos/frame | inferencias/frame |
|---|---|---|---|---|---|
| producción (CPU) | 52,4 % | 93,3 % | 99,3 % | 0,39 | 9 |
| + franja, recortes de 320 px | 55,5 % | 94,3 % | 99,5 % | 0,58 | 19 |
| + franja, recortes de 240 px | 54,5 % | 94,0 % | 99,3 % | 0,56 | 23 |

Criterio: recall < 20 px +15 puntos con los falsos positivos ≤ +10 %. Sale +3,1 puntos con +49 % de
falsos positivos y el doble de coste. Ampliar ×2-×3 no basta para un jugador de 15-20 px con este
detector. Un segundo intento tendría que cambiar algo más que el tamaño del recorte (p. ej. un detector
entrenado con jugadores pequeños): con recortes aún más pequeños, la red ve trozos de 1-2 jugadores sin
contexto. No se ha corrido.
