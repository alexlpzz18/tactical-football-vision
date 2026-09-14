# BACKLOG autónomo (12-ago-2026)

Reglas: rama por tarea, medir contra el banco, tests, documentar en
`docs/experimentos_tracking.md`. Nada se adopta como default sin OK de
Alex — se deja "provisional en la rama" con la tabla delante. **Excepción
vigente**: si algo mejora TODAS las métricas sin degradar ninguna, se
adopta y se marca como tal.

| # | tarea | estado |
|---|---|---|
| 1 | Fix v2 + auditoría de consumidores + test e2e | ✅ **HECHO** (`e84a521`) |
| 2 | Rematar piloto del balón | ✅ **HECHO** (`c0518d8`) |
| 3 | Muestra estética | ✅ **HECHO** (`ec65347`), 1 min en vez de 3 |
| 4 | Pizarra táctica interactiva v1 | ⬜ pendiente |
| 5 | Informe v2 para F7 pulido | ✅ **HECHO** — muestra del benja generada |
| 6 | Preparar el v4 final (dataset 840 + W&B) | ✅ **HECHO** — dos celdas listas |
| 7 | Robustez: TODOs, validaciones, sed frágil | ⬜ pendiente |
| 8 | Barrido COMBINADO de la asociación | 🔄 en curso |
| 9 | Barrido de suavizado × interpolación | ✅ **HECHO** — dos presets, ninguno adoptado |
| 10 | Barrido del fit del clasificador | ✅ **HECHO** — radio 45 adoptado |
| 11 | Repetir 8 y 10 con cachés v2color | ⚠️ **PARCIAL** — benja OK (empate), Villaviciosa con detector equivocado |

## Detalle de los bloqueos

### 2 — Piloto del balón: PENDIENTE-ALEX

**Qué falta**: los cachés. `data/tracking_benja/` solo tiene el tramo de
1 minuto; los `*piloto5min` y `cache_balon_piloto.pkl` nunca se llegaron
a generar (la sesión de Colab murió con el bug del salto, ya arreglado en
`39acfbe`).

**Qué necesito de ti**: correr los pasos 3-5 de
`docs/sesion_colab_completa.md` y bajarme:

- `data/tracking_benja/cache_balon_piloto.pkl`
- `data/tracking_benja/cache_detecciones_benja_piloto5min.pkl`
- `data/tracking_benja/cache_colores_benja_piloto5min.pkl`

Con eso, sin GPU, salen el CSV conjunto, el vídeo con cajas, el replay y
los números (% con balón, % en fase aérea, contactos).

### 11 — Barridos con v2color: PENDIENTE-ALEX

**Qué falta**: los cachés v2 (paso 6 de la guía). El fix ya está, así que
la generación debería correr limpia.

**Preparado para que sea un comando**: los scripts de barrido aceptan
`--config` y `--config-tracking`, así que en cuanto estén los cachés se
disparan apuntando a `configs/evaluation_v4pre_v2color.yaml`.

## 3 — Nota sobre la muestra estética

Se entregó con **1 minuto** (5:00–5:59 del vídeo), no 3, por el mismo
motivo que el punto 2: no hay cachés de 5 min. Cuando lleguen, regenerar
es un comando.

## 12. Apariencia en la ASOCIACIÓN (abierta 17-ago-2026)
Diseño en `docs/apariencia_en_asociacion.md`. Es donde viven las 5-8
quimeras que resisten al detector nuevo y al barrido del fit.
- [ ] Paso 0 — DIAGNÓSTICO: ¿las 8 quimeras de Villaviciosa nacen en
      frames con solape de cajas? Si la mayoría no nace ahí, toda la
      hipótesis es falsa y no hay que construir nada encima.
- [ ] Camino A — veto de color SOLO en el instante de cruce (no global:
      cortar con señales ruidosas en todos los frames ya salió mal tres
      veces).
- [ ] Camino B — asociación propia con coste mixto IoU+color, solo si A
      confirma la hipótesis.
Criterio: quimeras 8 → menos SIN degradar cobertura 0,598, IDF1 0,484 ni
concurrencia 23.

## 13. La animación tiene que respetar lo que la cámara TAPA (idea de Alex, 27-ago-2026)

Si sabemos que la cámara tapa una zona —por ejemplo la esquina inferior
izquierda— y un jugador aparece de repente ahí, no ha aparecido de la
nada: **viene de ahí**. La ficha del replay debería entrar desde la zona
tapada en vez de materializarse en el sitio, que es lo que hoy se lee
como un fallo del sistema.

Es la misma familia de ideas que ya pagó dos veces en este proyecto: el
valor está en el CONOCIMIENTO DEL DOMINIO —dónde está la cámara, qué
tapa, por dónde se entra al campo— y no en el modelo.

Lo que haría falta, en orden:
- [ ] Declarar las zonas ciegas en el config del campo (son una propiedad
      de la CÁMARA de ese partido, como `espejar`).
- [ ] Comprobar la premisa antes de construir: ¿las apariciones súbitas
      se concentran de verdad en esas zonas? Si aparecen por todo el
      campo, la explicación es otra (fallo de asociación) y taparla con
      una animación la escondería.
- [ ] Solo entonces, la entrada/salida animada desde el borde de la zona.

⚠️ El riesgo conocido: una animación que rellena lo que no se vio es una
posición INVENTADA. Tiene que distinguirse de una medida (el replay ya
tiene el desvanecido por antigüedad para eso) o el replay pasa de mostrar
lo que el sistema ve a mostrar lo que suponemos.

## 14. Analizar el SAQUE DE PUERTA como unidad táctica (idea de Alex, 27-ago-2026)

Nace de mirar el minuto 18:21 de la parte entera del benjamín: el naranja
saca jugado desde portería, el bloque sale escalonado y el sistema lo
pinta bien entero (solo falla el árbitro). Ese frame ya contiene la
información táctica; lo que falta es **recortarlo como evento y contarlo**.

Lo que Alex quiere ver, con sus palabras: los 5-6 saques de puerta del
rival, en vídeo y en una pizarra donde poder **mover fichas y dibujar**,
y que el informe lo redacte — *"el rival juega con central abierto y el
90 % de las veces busca pase con lateral cercano"*, *"un 60 % de las
veces han conseguido sacar el balón bien"*. Igual con los saques a favor,
y con la presión: la que hacemos y la que nos hacen.

### Lo que YA existe (no se parte de cero)

- **Balón**: `src/balon/tracking_balon.py` (balón activo, fases aéreas,
  contactos por ángulo y por velocidad), `scripts/detectar_balon.py` y un
  modelo piloto a conf 0,35 (P 0,958 / R 0,836). Falta pasarlo por la
  parte entera, que es GPU.
- **Redacción**: `src/report/analisis_ia.py`, ya con el principio
  correcto — *el CÓDIGO calcula, el LLM SOLO redacta a partir de esos
  números y tiene prohibido inventar*. Añadir una familia de métricas es
  añadirlas al JSON y al catálogo de `configs/informe.yaml`.

### Lo que NO existe

- **Segmentación en eventos** (dónde empieza y acaba un saque de puerta).
- **Pizarra EDITABLE**: la de hoy es un visor, no un editor.

### El orden, y por qué

⚠️ Las tres preguntas de Alex no cuestan lo mismo, y conviene no
mezclarlas:

1. **"Central abierto"** = forma del bloque en el instante del saque.
   **Solo necesita POSICIONES, que ya tenemos.** Es lo más barato de todo
   y no depende del balón.
2. **"Han conseguido sacarlo bien" (60 %)** = necesita el evento y, sobre
   todo, una DEFINICIÓN. Eso no es visión por computador, es una
   pregunta para Alex: ¿tres pases seguidos?, ¿pasar del medio campo?,
   ¿no perderla en 10 s?
3. **"El 90 % busca al lateral cercano"** = necesita detección de PASES,
   o sea posesión atribuida frame a frame. Es lo más caro y lo que más
   depende del recall del balón (0,836 se compone a lo largo de una
   jugada).

### La comprobación barata que va PRIMERO

¿Se pueden encontrar los saques de puerta **sin balón**, solo con las
posiciones de la parte entera? Un saque de puerta tiene firma: juego
detenido, portero hundido en su área, los dos bloques recolocándose. Si
sale, el punto 1 se desbloquea sin GPU y sin balón.

- [ ] Alex: los TIMESTAMPS de los saques de puerta de esta parte (es el
      GT del experimento) y su definición de "sacarlo bien".
- [ ] Buscarlos solo con posiciones y medir contra esos timestamps.
- [ ] Si aparecen: forma del bloque en cada uno (el "central abierto").
- [ ] Si no aparecen: la vía es el balón, y entonces toca GPU.

Precedente que manda aquí: *las reglas posicionales valen MÁS que el
clasificador* (CLAUDE.md, 20-ago-2026). Antes de meter el balón, mirar
qué se puede sacar de lo que ya sabemos del fútbol.


## 15. RIESGO DE PRODUCTO: el clip corto que empieza en el saque inicial

Medido el 27-ago-2026 (`docs/verificacion_adversarial_27ago.md`): el
tramo 0-5 de un partido es **otro régimen** —saque inicial, jugadores
colocándose, gente entrando al campo— y su fit se desvía un **35 % de la
distancia A−B** contra un nulo de remuestreo del 2,2 %.

Sobre una parte entera eso no importa: ese tramo es una cuarta parte de
la muestra y los otros 15 minutos lo diluyen (quitarlo mueve el fit 1,8 %
y no cambia ni una observación).

⚠️ **Pero el día que un cliente suba un clip recortado que empiece en el
saque inicial, ese régimen será el 100 % del fit.** Es el peor caso
posible y llega por la vía más normal: un entrenador que recorta "los
primeros minutos" para probar el producto.

La palanca ya existe y está apagada: `entrenamiento.desde_s`. Lo que
falta antes de activarla:

- [ ] Medir el daño de verdad: fitear SOLO sobre 0-5 y evaluar contra el
      GT. Hoy solo está medido el caso contrario (quitarlo de una pasada
      larga), que no dice nada de este.
- [ ] Decidir la respuesta de producto, que puede no ser técnica.
      **Prioridad de Alex (27-ago-2026), y el razonamiento es de venta,
      no técnico:**
      1. **Fitear con los últimos N minutos del clip.** La preferida:
         **no le pide nada al cliente**. Es la que hay que medir primero.
      2. Exigir una duración mínima → *fricción de venta*.
      3. Avisar de que dará peor resultado → *es decirle que el producto
         funciona a medias*.

Precedente que aplica: **actuar solo donde hay riesgo**. No tocar el fit
en general — solo decidir mejor cuando el clip es corto y arranca en el
minuto 0, que es detectable sin ambigüedad.

## 16. El detector de PERSONAS está marcando el BALÓN (28-ago-2026)

Visto en los recortes de intrusos: la identidad `id 62`, etiquetada como
jugador del equipo B, es **un balón** en t=59 s (`outputs/intrusos_equipo_B.png`).

Es un falso positivo que el **filtro de plausibilidad física** debería
cazar sin ayuda: `src/tracking/plausibilidad_fisica.py` ya deriva la
altura real de una caja con `alto_px × σ_min(J)`, y **un balón no tiene
proporciones de persona** — ni su altura implícita (0,2 m contra 1,5) ni
su relación de aspecto (1:1 contra 1:3).

- [ ] Comprobar cuántas detecciones de "persona" tienen relación de
      aspecto de balón, y si el filtro actual ya las quita o se cuelan.
- [ ] Si se cuelan: la relación de aspecto es la señal más barata, y ya
      hay dónde ponerla. Pero medir antes cuántos jugadores agachados o
      en el suelo se perderían — es la segunda señal débil de siempre.

Coste hoy: pequeño en número, pero **suma al recuento del equipo B**, que
es lo primero que un entrenador mira.

## 17. La banda del esquema mixto tiene que salir de la HOMOGRAFÍA (29-ago-2026)

`BANDA_LEJOS = (540, 720)` en `scripts/detectar_balon.py` es donde el
esquema mixto trocea. Está **medida sobre la cámara del benjamín**: la
altura en la imagen predice el tamaño del balón con correlación +0,924
(perspectiva pura), los 47 huecos del fondo arrancan entre y=590 y y=642,
y esa banda —el 17 % del alto— contiene el 100 % de ellos y el 100 % de
los balones de menos de 12 px.

⚠️ **Es exactamente el tipo de número que NO viaja entre partidos.** Ya
nos pasó dos veces: `arbitro.margen_equipo` (adoptado y revertido el mismo
día, la ventana se movía con el detector) y las franjas de profundidad. Y
aquí el fallo sería silencioso: una banda heredada de otro encuadre
trocearía césped vacío y dejaría el fondo sin trocear, y el informe no se
quejaría — diría que el esquema mixto no cierra huecos, que es un negativo
falso sobre una idea buena.

- [ ] Derivarla de la homografía: proyectar a la imagen la línea del campo
      a x = `zona_min` metros y coger la banda con margen, en vez de dos
      números fijos.
- [ ] Guarda que falle si la banda calculada no contiene los huecos del
      fondo del caché que se está usando. El test de hoy
      (`test_la_banda_cubre_donde_arrancan_los_huecos_del_fondo`) fija los
      590-642 del benjamín: sirve de candado, no de cálculo.

**No antes de saber si el mixto gana**: si pierde contra SAHI 3×5, la
banda no hace falta para nada.

## 18. Medir el BALÓN ACTIVO, que es lo que dice si los falsos positivos importan (29-ago-2026)

SAHI cierra 47 de 47 huecos del fondo pero sube los candidatos por frame a
1,59. Ese número **no dice nada por sí solo** (Alex): lo que decide es si
el balón ACTIVO elegido sigue siendo el correcto. Si el selector descarta
bien los distractores, 1,59 candidatos es ruido inofensivo.

Hoy no se puede medir con el comparador: `seleccionar_balon_activo` agrupa
por **continuidad espacial entre frames consecutivos**, y los 248 frames
de la comparación están desperdigados por 20 minutos. Correrlo ahí no
mediría el selector, mediría el vacío. Lo que hay mientras tanto es el
proxy `distractores`: candidatos plausibles a más de 40 px del balón bueno
en los frames de control.

- [ ] Tramo CONTIGUO de 30-60 s que contenga huecos del fondo. **Puede
      salir del piloto de 5 min, que ya tiene caché** (`cache_balon_piloto.pkl`).
- [ ] Pasarlo entero con cada esquema, aplicar `seleccionar_balon_activo`
      y contar frames que acaban con el balón EQUIVOCADO — no candidatos
      totales.
- [ ] El control: comparar contra el mismo tramo con frame entero, donde
      sabemos que el balón elegido es el bueno.

## 19. El postproceso de SAHI puede estar comiéndose JUGADORES (29-ago-2026)

Demostrado sobre el balón (`docs/sahi_balon.md`): `get_sliced_prediction`
fusiona con **`GREEDYNMM` y métrica `IOS`** (intersección sobre la caja
MENOR), umbral 0,5. Con IOS, **una caja grande que contiene a otra
pequeña da 1,00** aunque sean objetos distintos, y la fusión se queda con
la CONFIANZA de la pequeña y la GEOMETRÍA de la grande.

En el balón eso hacía desaparecer detecciones perfectamente buenas: la
caja resultante proyectaba fuera del campo y el filtro de plausibilidad la
tiraba. Confianzas de las perdidas: 0,67 · 0,59 · 0,70 · 0,74, contra una
mediana de control de 0,69 — **no eran las del filo**.

⚠️ **El detector de JUGADORES usa SAHI 2×4 con los mismos defaults**
(`deteccion.sahi` en los configs). Un jugador dentro de una caja grande
—un grupo apiñado, una portería, una sombra— daría IOS = 1,00 y
desaparecería igual. Y hay un síntoma esperando explicación desde hace
semanas: **el recuento de jugadores sale corto, 5-6 contra 7-8**.

No está medido que sea esto. Está medido que el mecanismo existe.

- [ ] Pasar unos frames con `postprocess_match_metric="IOU"` en vez de
      `IOS` y comparar el número de jugadores detectados. Es un parámetro,
      no un cambio de modelo.
- [ ] Si sube el recuento: mirar si los recuperados son los que faltaban
      (posición y equipo), no solo cuántos. **Más detecciones no es
      mejor** — puede ser una caja grande partida en dos.
- [ ] El control: los frames donde el recuento YA era correcto no pueden
      empeorar.

Coste hoy: desconocido, pero toca la métrica que un entrenador mira
primero.
