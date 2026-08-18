# Cómo se elige el backbone (decidido ANTES de medir, 19-ago-2026)

Escrito antes de generar un solo embedding, a propósito: con tres
candidatos y varias métricas es demasiado fácil elegir a posteriori la
tabla que favorece al que ya nos gustaba.

## Para qué queremos el embedding

El punto 1 lo dejó claro: **el 85-90 % de los fallos de equipo son de
ASOCIACIÓN**, no del clasificador. Así que el embedding se elige por lo
que necesita el tracker, no por lo que necesita la clasificación:

> ¿Distingue a DOS PERSONAS DISTINTAS, y en particular a dos compañeros
> con la MISMA equipación?

Ese es el caso #43 de Alex y el techo conocido de la puerta de color.

## La métrica que decide

Con el GT de Villaviciosa (23 identidades con posición y equipo) se
construyen tres tipos de pareja de recortes:

| pareja | qué mide |
|---|---|
| **misma persona**, frames distintos | ¿reconoce a alguien pese al movimiento y la oclusión? |
| **distinta persona, MISMO equipo** | **el caso difícil** — visten igual |
| distinta persona, distinto equipo | el caso fácil (es lo que ya resuelve el color) |

**Métrica principal: TPR @ FPR = 1 % sobre las parejas de MISMO EQUIPO.**
O sea: de cada 100 reencuentros reales del mismo jugador, cuántos
reconoce, con el umbral puesto donde solo 1 de cada 100 parejas de
compañeros distintos se confunde.

No es AUC, y la razón es doctrina del proyecto: **fragmentar es
recuperable, mezclar no.** Un falso positivo aquí es una quimera; un
falso negativo es un fragmento que el cosido puede recoser. El punto de
operación tiene que estar donde casi nunca se mezcla, y el AUC promedia
sobre puntos de operación que jamás usaríamos.

## Estratificado por tamaño de recorte, obligatorio

Nuestros jugadores miden **13-40 px**. Una media global la sostienen los
jugadores cercanos y **esconde el fallo en el fondo del campo**, que es
justo donde hay que decidir. La tabla se da por bins:

| bin | por qué |
|---|---|
| < 20 px | el fondo del campo; el caso que importa |
| 20-30 px | medio campo |
| > 30 px | primer plano; el caso fácil |

**El ganador se decide por el bin < 20 px**, no por la media.

## La línea base no es opcional

**El histograma HSV actual entra en la tabla como un candidato más.** Sin
esa columna no se puede saber si un embedding aporta algo, y este
proyecto lleva tres cortes adoptados por buenos que medían peor
(velocidad, post-proceso, color). Si ningún backbone bate al HSV en el
bin pequeño, la respuesta correcta es **no adoptar ninguno**.

## Regla de decisión, escrita antes

1. **Gana** el backbone con mayor TPR @ FPR 1 % en parejas de mismo
   equipo, **en el bin < 20 px**, siempre que bata al HSV.
2. **Empate técnico** (diferencia < 3 puntos): gana el más barato —
   menos dimensiones y más rápido. Con igual señal, el coste decide.
3. **Si ninguno bate al HSV en ese bin**: se declara que a 13-40 px **no
   hay señal de apariencia que extraer**, y toda la línea de partir
   quimeras por apariencia (punto 3, GTA-Link) queda muerta. Sería un
   resultado negativo válido y hay que estar dispuesto a aceptarlo — es
   el "riesgo 2" de `docs/embedding_unico.md`.

## Métricas secundarias (informan, no deciden)

- TPR @ FPR 1 % en parejas de **distinto equipo**: si aquí también gana,
  sirve además para clasificar (el ~9 % restante de los fallos).
- Dimensiones, tamaño del caché y tiempo de inferencia por 1.000 recortes.
- Efecto de PCA a 128 dims sobre la métrica principal: si no la mueve,
  producción va con 128 y el caché baja de ~1,6 GB a ~270 MB por partido.

## Nota de método

El benchmark se hace sobre **embeddings SIN PCA**. Aplicar PCA antes
mediría la PCA además del backbone, y con tres candidatos de dimensiones
distintas (768, 768, 2048) sería comparar cosas diferentes. La PCA se
evalúa después, sobre el ganador, como optimización de producción.

---

## Adición: estratificar TAMBIÉN por separación temporal (19-ago-2026)

Petición de Alex, y corrige un punto ciego del criterio original.

El paso 0 midió que las quimeras nacen sobre todo al **RECUPERAR un track
perdido** (ratio 3,0×), no en el cruce instantáneo (1,8×). O sea: el
momento en que el embedding tiene que decidir es justo aquel en que la
geometría ya no dice nada, porque han pasado segundos y el jugador puede
estar en cualquier parte.

**Un embedding que solo reconozca reencuentros inmediatos no sirve para
el caso que duele.** Y la métrica original lo habría dado por bueno: las
parejas de "misma persona" en frames contiguos son casi el mismo píxel, y
cualquier backbone las empareja.

Por eso las parejas de MISMA persona se parten por separación temporal:

| bin | qué representa |
|---|---|
| < 1 s | continuidad; el caso fácil, que ya resuelve el IoU |
| 2-5 s | **la re-entrada típica** (el buffer es de 1,5 s) |
| > 5 s | el hueco largo, donde solo queda la apariencia |

**El ganador se decide por el bin de 2-5 s**, cruzado con el bin de
tamaño < 20 px. Esa casilla —jugador pequeño, reencuentro tras varios
segundos— es exactamente la situación que produce las quimeras que
resisten a todo lo demás.

Si un backbone gana en la media y pierde ahí, no vale.

No hace falta regenerar nada: la separación sale de los `frame_idx` que
el caché ya guarda, y ahora también lleva `fps` y `sample` para no
depender del caché de detecciones.

---

# RESULTADO (19-ago-2026)

`scripts/benchmark_embeddings.py`, criterio aplicado tal cual.

## TPR @ FPR 1 % sobre parejas de MISMO equipo

| recortes | backbone | dims | <1 s | **2-5 s** | >5 s | dist. equipo |
|---|---|---|---|---|---|---|
| **<20 px** | dinov2 | 768 | — | **0,000** | 0,000 | — |
| | resnet50 | 2048 | — | — | 0,000 | — |
| | siglip | 768 | — | — | 0,000 | — |
| | HSV (control) | 256 | — | — | 0,000 | — |
| **20-30 px** | **dinov2** | 768 | 0,462 | **0,179** | 0,129 | 0,136 |
| | resnet50 | 2048 | 0,362 | 0,172 | 0,084 | 0,245 |
| | siglip | 768 | 0,377 | 0,079 | 0,072 | 0,086 |
| | HSV (control) | 256 | 0,273 | 0,082 | 0,050 | 0,280 |
| **>30 px** | dinov2 | 768 | 0,250 | 0,071 | 0,064 | 0,303 |
| | resnet50 | 2048 | 0,306 | 0,168 | 0,045 | 0,234 |
| | siglip | 768 | 0,100 | 0,000 | 0,000 | 0,153 |
| | HSV (control) | 256 | 0,216 | 0,068 | 0,042 | **0,812** |

## La casilla que decide NO se puede medir con este GT

El criterio decía "gana el bin <20 px × 2-5 s". Esa casilla tiene **3
parejas**. No es un resultado negativo: es que no hay datos.

| bin | recortes con GT | personas | parejas misma-persona a 2-5 s |
|---|---|---|---|
| <20 px | **17** | 9 | **3** |
| 20-30 px | 282 | 23 | 274 |
| >30 px | 159 | 15 | 285 |

La causa es la densidad del GT, no los backbones: de los 10.621 recortes
solo **458 casan con el GT**, porque el GT está etiquetado 1 de cada 15
frames y el caché va 1 de cada 3 (la alineación conocida de CLAUDE.md).
De esos 458, los de menos de 20 px son 17.

**Por tanto el veredicto automático —"ninguno bate al HSV, la línea de la
apariencia queda muerta"— no vale.** Sale de una casilla vacía, y matar
una línea de trabajo con 3 parejas sería el error más caro posible.

## Lo que SÍ dicen los datos

En la casilla poblada más cercana a la intención (**20-30 px × 2-5 s**,
274 parejas), los dos candidatos serios **doblan al HSV**:

- dinov2 **0,179**, resnet50 0,172, frente a HSV **0,082**
- siglip 0,079, que empata con el HSV y queda descartado

Y hay un hallazgo que confirma el principio de arquitectura: **el HSV
gana de calle en "distinto equipo"** (0,812 con recortes grandes, frente
a 0,303 del mejor embedding). Es decir, cada representación es buena en
lo suyo — el color para separar EQUIPOS, el embedding para separar
PERSONAS. Justo lo que predecía `docs/embedding_unico.md`: invariancias
opuestas, y por eso umbral (y aquí incluso representación) por consumidor.

## Qué hacer, sin tocar el criterio

El criterio se mantiene. Lo que falta es poder aplicarlo, y para eso hay
que subir la densidad del GT en recortes pequeños. Dos vías:

1. **Etiquetar GT en más frames** del tramo (los múltiplos de 3 en vez de
   los de 15). Caro y es justo el esfuerzo que Alex paró.
2. **Usar las identidades del tracker como pseudo-GT** para las parejas
   POSITIVAS, restringido a identidades que el GT confirma puras. No
   inventa etiquetas: aprovecha que una identidad pura ya es, por
   definición, la misma persona en todos sus frames — y multiplica por
   ~20 las parejas disponibles.

La 2 es barata y no pide más trabajo manual. Es lo que propongo antes de
declarar nada sobre el bin pequeño.
