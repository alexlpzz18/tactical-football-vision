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

---

### Actualización de BACKLOG 19 (29-ago-2026): la premisa del recuento corto, REFUTADA

Medido en local sobre la parte entera: **el detector saca 17,6 cajas por
frame** (mediana 18, p10 14, p90 21), y en un fútbol 7 hay 16 personas en
campo, 17 con el árbitro.

**El recuento corto (5-6 contra 7-8) no puede nacer en la detección**: hay
cajas de sobra. Nace después — tracking, clasificación de equipos o la
forma de contar. Eso convierte BACKLOG 19 en una mejora posible pero
PEQUEÑA (orden 0,5 jugadores por frame), no en "la mayor que queda sobre
la mesa".

Y abre la pregunta que sí lo es: **si hay 17,6 cajas y solo se cuentan
5-6 por equipo, ¿dónde se pierden las otras?** Esa es la siguiente
medición, y no necesita GPU.

Dos huellas locales que NO sirvieron, documentadas para no repetirlas:

1. **Cajas gigantes**: para el balón el impostor es una caja absurda; para
   un jugador es la caja de OTRO JUGADOR, plausible. La absorción es
   invisible en el tamaño (solo el 0,16 % implican más de 2,5 m).
2. **"No deberían quedar pares anidados"**: razonamiento equivocado.
   **GreedyNMM es greedy, no exhaustivo**: consume la caja de mayor score,
   fusiona lo que casa con ella y la saca del conjunto, así que pares
   anidados entre cajas ya consumidas sobreviven. Quedan 5.851 (0,49 por
   frame) y reaplicar el postproceso quita otro 2,9 %. Su presencia no
   prueba nada en ninguna dirección.

Celdas de Colab listas en `docs/colab_ios_jugadores.md`, con el control de
que las cajas recuperadas tengan altura de persona.

## 20. ¿Dónde se pierden las cajas entre el detector y el recuento? (29-ago-2026)

Sale de refutar la premisa de BACKLOG 19. **17,6 detecciones por frame
entran**, y el recuento por equipo sale en 5-6 cuando deberían ser 7-8.
Entre una cosa y la otra hay: tracking (ByteTrack), plausibilidad física,
clasificación de equipos y las siete reglas sobre medias de identidad.

- [ ] Contar, frame a frame, cuántas de las 17,6 llegan a cada etapa:
      detección → track con id → etiqueta de equipo → recuento final.
      Es un embudo, y el escalón donde caiga es la respuesta.
- [ ] No necesita GPU: todo está en el caché y en el CSV.
- [ ] ⚠️ El control: parte de las 17,6 son banquillo, árbitro y público, y
      SE TIENEN que perder. Lo que hay que separar es cuántas se pierden
      por ser correctas-pero-descartadas contra cuántas se pierden bien.

## 21. El balón FANTASMA: un objeto fijo detectado como balón (29-ago-2026)

`docs/balon_fantasma.md`. Un objeto estático en el píxel (372, 628) sale
detectado como balón en **7.974 frames** de los 17.983, y en 3.144 de
ellos es la ÚNICA detección. El 80,9 % anunciado es un **58,3 %** real.

La guarda que existe para esto (`seleccionar_balon_activo`) no lo quita
porque exige `distancia al jugador más cercano > 25 m` y el fantasma está
a 12,4 m. Medido: solo el **0,63 %** de los instantes llegan a 25 m, así
que **la guarda no puede dispararse**.

- [ ] Añadir la señal que sí separa: un candidato **anclado al mismo píxel
      durante minutos** no es un balón. Es independiente de la distancia a
      los jugadores, que es la condición que aquí no sirve.
- [ ] ⚠️ NO bajar simplemente el umbral de 25 m sin medir: la segunda
      condición existe para no cargarse un balón parado en un saque de
      banda, que sí está cerca de un jugador.
- [ ] Medir contra LAS DOS patas antes de adoptar.
- [ ] Y re-medir el % de balón después: el titular del esquema mixto hay
      que corregirlo en los docs que lo citen.

## 22. El cajón "otro": 0,89 jugadores por frame sin equipo (29-ago-2026)

Del embudo (BACKLOG 20). De las 14,57 personas por frame que se trackean
dentro del campo, **2,11 acaban con una etiqueta que no es de equipo**:

| etiqueta | por frame | en la BANDA (y<3 o y>37) | y mediana | ids |
|---|---|---|---|---|
| `staff` | 1,09 | **98,5 %** | −1,0 | 63 |
| `otro` | 0,89 | **3,3 %** | 20,1 | 53 |
| A | 4,96 | 5,9 % | 20,6 | 257 |
| B | 6,27 | 5,7 % | 20,3 | 255 |

`staff` está bien: vive en la banda. **`otro` se distribuye como A y como
B** —centro del campo, misma mediana de y— así que son jugadores sin
asignar. Es la parte recuperable del recuento, y son 53 identidades.

- [ ] Mirar esas 53: ¿son identidades cortas, contaminadas, o de color
      ambiguo? La distinción decide el arreglo.
- [ ] ⚠️ El control: recuperarlas NO puede empeorar el 1,2 % de equipo
      equivocado. Meter 0,89 jugadores por frame con el equipo mal sería
      peor que no meterlos.

---

### Cierre de BACKLOG 20 y 22 (17-sep-2026)

**BACKLOG 20 (el embudo) — resuelto**, `docs/recuento_no_es_el_encuadre.md`.
Con el balón en el fondo (campo visible al 100 %) se cuentan **12,08 de 14**
jugadores de campo, y el recuento apenas se mueve con la posición del
balón: **el encuadre explica como mucho 1 jugador**. El reparto del
déficit en frames limpios: **1,61 nunca se detectan**, 0,36 se pierden en
el tracking y ~0 en el etiquetado. No es oclusión (correlación −0,26 con
el apiñamiento); es que el bloque estirado pone a sus extremos en las
zonas duras (−0,39 con el spread).

⇒ **Tracking y etiquetado quedan exculpados.** Quien quiera subir el
recuento tiene que ir al DETECTOR, y esa palanca ya está cerrada por otro
sitio (el v4 con mAP50 0,944 no movió la aguja).

**BACKLOG 22 (el cajón "otro") — cerrado en NEGATIVO.** No son jugadores
recuperables: es el **árbitro**. El 84,7 % de los frames tiene 0 o 1, su
color está lejos de los DOS prototipos (0,90 y 0,78, contra 0,03 de una
identidad de A al suyo) y `pipeline_equipos.py` le asigna `"otro"` a
propósito tras el catálogo arbitral. Lo recuperable es el exceso sobre 1:
**~0,15 jugadores por frame**. No mueve el recuento.

⚠️ El diagnóstico anterior ("son jugadores porque se distribuyen como A y
B") era mío y estaba mal: no me pregunté qué OTRA cosa produce esa misma
distribución.

## 23. El detector pierde 1,6 personas por frame con el campo a la vista (17-sep-2026)

Sale de cerrar el 20. En los frames donde se ve el campo entero se
detectan **15,39 personas dentro del campo** de 17 esperadas (14 + 2
porteros + árbitro). No es oclusión y no es encuadre.

La señal que sí correlaciona: **el bloque estirado** (−0,39). Los
extremos caen en el fondo (jugadores de ~26 px) o en el borde cercano.

- [ ] Localizar QUÉ personas faltan: comparar, en los frames limpios, la
      posición de las detecciones con la de la jugada anterior y la
      siguiente por continuidad de identidad. Una persona que estaba y
      vuelve a estar, pero no está ahora, es una pérdida localizable.
- [ ] ⚠️ El control: parte de esas 1,61 pueden ser gente legítimamente
      ausente (un cambio, alguien tumbado fuera del campo). Hay que
      separar antes de llamarlo fallo.
- [ ] Y antes de tocar el detector: comprobar si es el mismo techo de
      resolución de Villaviciosa. Si lo es, la vía ya está cerrada.

---

### BACKLOG 23 — CERRADO EN NEGATIVO el mismo día que se abrió (17-sep-2026)

`docs/backlog23_no_hay_deficit.md`. **No faltan 1,6 personas por frame.**
El déficit salía de contar 16 personas en el campo cuando en **fútbol 7
son 14** (7 por equipo incluyendo al portero; el GT tiene 14 tracks). Con
la cifra correcta, las 15,39 detecciones de los frames limpios son un
EXCEDENTE de 0,39, no un déficit.

Medido contra el GT: el detector encuentra al **96,7 %** de las personas
anotadas (27 ausencias de 814, 0,45 por frame), **rotando** entre 9 tracks
al 2-10 % cada uno, con 5 tracks sin ningún fallo y 36 de 60 frames
limpios del todo. Y de esas 27, varias son deriva de la anotación.

⚠️ Y el error hacía parecer falsa la hipótesis de Alex: con la plantilla
correcta, **B está completo (7,38 de 7) y el que falta es A (6,17)**, que
es el equipo que defiende el lado visible al 15 %. **El recuento corto SÍ
es del encuadre.**

No queda nada que perseguir en la detección de jugadores.

---

### La contradicción del recuento, RESUELTA (17-sep-2026)

`docs/la_contradiccion_del_recuento.md`. **No había nada roto.** Cada
persona tiene fila del sistema a <2 m el 86,5 % de las veces, y exigir las
siete a la vez da 0,865⁷ = 36,2 % por pura combinatoria — contra el 38,7 %
observado. El 1,2 % de equipo equivocado es por OBSERVACIÓN y entre las que
casan: miden cosas distintas.

Hallazgos que sí quedan vivos:

- **El error de posición cerca de la cámara es 1,29 m contra 0,41 m en el
  centro.** No estaba medido, y explica que A salga peor en toda métrica
  con radio. El 60 % de las personas "que faltan" son una "que sobra"
  desplazada 2,48 m: la misma persona contada dos veces.
- **A falla por defecto (66,3 %) y B por exceso (33,0 %).** Leer "45 %
  correcto" como "faltan jugadores" era la mitad de la historia.
- El exceso real sale de 8 identidades, y dos tienen nombre: **id 292**
  (mezcla al árbitro, 1,10 m/s) e **id 62** (un balón como persona,
  1,20 m/s). Un jugador de campo va a 1,5-2,5 m/s.

⚠️ NEGATIVO: **quitar identidades no arregla el recuento.** Sin la id 292
sube +2,1 pts, pero sin las tres que más sobran BAJA 2,4 pts, porque en los
frames donde B estaba bien pasan a faltar.

## 24. Retirar "recuento exacto = 7" de las métricas de producto (17-sep-2026)

Es una métrica de igualdad exacta sobre catorce personas: castiga por
combinatoria (36 % es el techo con un 86,5 % por persona) y no distingue
"falta un jugador" de "sobra el árbitro".

- [ ] Sustituirla en el informe por el recuento MEDIANO por equipo y el
      error por observación, que es lo que ya está medido y validado.
- [ ] ⚠️ Control: comprobar que la métrica nueva sigue bajando cuando se
      introduce un fallo de verdad. Una métrica más amable que no se mueve
      ante un fallo real es peor que la frágil.
