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
