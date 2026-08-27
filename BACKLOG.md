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
- [ ] Decidir la respuesta de producto, que puede no ser técnica: avisar
      al usuario de que un clip corto desde el inicio da peor resultado,
      o exigir una duración mínima, o fitear con los últimos N minutos
      del clip en vez de con todo.

Precedente que aplica: **actuar solo donde hay riesgo**. No tocar el fit
en general — solo decidir mejor cuando el clip es corto y arranca en el
minuto 0, que es detectable sin ambigüedad.
