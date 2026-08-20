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

---

# RESULTADO CON PSEUDO-GT (19-ago-2026) — y siglip NO estaba descartado

## El pseudo-GT y su blindaje

El GT cubre 1 de cada 15 frames, así que solo 458 de 10.621 recortes
tenían etiqueta y el bin pequeño se quedaba en 3 parejas. Se densifica
usando las identidades del tracker, con dos cautelas:

1. **La pureza se verifica contra el GT, nunca contra el propio tracker.**
   Si nos fiáramos de "es pura porque el tracker no la partió",
   mediríamos el embedding sobre parejas que el tracker ya sabía
   emparejar: sesgo circular a favor de lo que ya funciona. Lo pidió Alex
   explícitamente y es el punto delicado de todo el montaje.
2. **Las parejas cruzan fragmentos.** Cuando dos identidades distintas
   resultan ser la misma persona del GT, sus recortes se emparejan entre
   sí — y esas son justo las parejas que **el tracker FALLÓ**, las
   re-entradas tras un hueco. Sin esto los positivos serían solo los
   aciertos del tracker y el bin de 2-5 s estaría sesgado hacia lo fácil.

Supervivientes del filtro: **29 identidades puras verificadas**, 14
contaminadas descartadas, 44 sin GT que las juzgue.

| bin | recortes | personas | parejas a 2-5 s | (antes) |
|---|---|---|---|---|
| **<20 px** | 263 | 12 | **788** | 3 |
| 20-30 px | 3.707 | 18 | 71.221 | 274 |
| >30 px | 1.325 | 12 | 24.425 | 285 |

5.295 recortes etiquetados frente a 458. La casilla que decide pasa de 3
parejas a 788: ya se puede aplicar el criterio.

## La tabla

TPR @ FPR 1 % sobre parejas de MISMO equipo:

| recortes | backbone | <1 s | **2-5 s** | >5 s | dist. equipo |
|---|---|---|---|---|---|
| **<20 px** | **siglip** | 0,438 | **0,200** | 0,047 | 0,246 |
| | resnet50 | 0,418 | 0,149 | 0,039 | 0,197 |
| | dinov2 | 0,253 | 0,106 | 0,051 | 0,208 |
| | HSV (control) | 0,231 | **0,018** | 0,005 | 0,000 |
| **20-30 px** | dinov2 | 0,429 | 0,211 | 0,137 | 0,156 |
| | siglip | 0,413 | 0,170 | 0,083 | 0,204 |
| | resnet50 | 0,420 | 0,162 | 0,055 | 0,314 |
| | HSV (control) | 0,247 | 0,074 | 0,067 | 0,192 |
| **>30 px** | dinov2 | 0,452 | 0,116 | 0,080 | 0,058 |
| | resnet50 | 0,476 | 0,054 | 0,023 | 0,024 |
| | siglip | 0,426 | 0,050 | 0,015 | 0,048 |
| | HSV (control) | 0,164 | 0,039 | 0,037 | **0,665** |

## Veredicto: gana siglip, y hay que retirar lo que dije antes

**siglip 0,200 frente a 0,018 del HSV: once veces mejor** en la casilla
que decide. Estable con tres semillas distintas (0,200 / 0,194 / 0,182),
así que no es ruido del muestreo.

**Y contradice lo que yo había concluido con el GT disperso**, donde
siglip empataba con el control (0,079 vs 0,082) y lo di por descartado.
Estaba midiendo con 274 parejas en el bin contiguo y ninguna en el
decisivo. La conclusión correcta es la de ahora, con 250 veces más
parejas — pero el episodio deja claro que **una tabla con casillas
mal pobladas no es "un poco menos fiable": puede invertir el orden.**

Nota para no sobreinterpretar: siglip gana en el bin pequeño y dinov2 en
el mediano (0,211 vs 0,170). Si el consumidor final trabaja sobre todo
con recortes de 20-30 px —que son la mayoría— la elección merece
revisarse. Para la re-entrada en el fondo del campo, que es el caso que
duele, manda siglip.

## Hallazgo que se mantiene: color y embedding no compiten

- **El color separa EQUIPOS**: HSV 0,665 en "distinto equipo" con
  recortes grandes, frente a 0,058 del mejor embedding.
- **El embedding separa PERSONAS**: siglip 0,200 frente a 0,018 del HSV
  en la casilla difícil.

Cada representación es buena en su pregunta, y son preguntas opuestas.
Confirma el principio de `docs/embedding_unico.md`: **el HSV se queda en
el clasificador de equipos; la apariencia va al tracker.**

Un matiz que aparece solo aquí: con recortes <20 px el HSV da **0,000**
en "distinto equipo". A esa escala el color no distingue ni equipos, y
los embeddings (0,197-0,246) son lo único que queda.

## Lección de método

Un criterio escrito a ciegas —que es lo correcto para no elegir la tabla
que nos gusta— **también hay que comprobar que tiene datos suficientes en
la casilla que decide, antes de dejar que dictamine.** Escribí el
criterio sin mirar la densidad del GT, y su primer veredicto fue matar la
línea de la apariencia con 3 parejas. Es la segunda vez que una casilla
mal poblada casi cierra una vía buena.

---

# DÓNDE OPERA EL EMBEDDING: un backbone, y es siglip (19-ago-2026)

`scripts/tamano_en_el_cruce.py`. La distribución global de tamaños no
sirve para elegir: el embedding no se consulta en todos los recortes,
sino en el CRUCE y en la RE-ENTRADA.

| momento | n | <20 px | 20-30 px | >30 px |
|---|---|---|---|---|
| todos los recortes | 9.511 | 5,0 % | 69,9 % | 25,1 % |
| en el cruce | 909 | 9,2 % | 63,6 % | 27,2 % |
| **en la re-entrada** | 132 | **42,4 %** | 51,5 % | 6,1 % |

**La re-entrada está dominada por recortes pequeños: 42,4 % frente al
5,0 % de la población general, un enriquecimiento de 8,5×.** Tiene
sentido físico: un track se pierde sobre todo cuando el jugador está
lejos, donde mide poco y se ocluye con facilidad.

Dos consecuencias:

1. **La casilla que elegimos a ciegas era la correcta.** `<20 px × 2-5 s`
   no era una esquina exótica: es el 42 % de las re-entradas, el momento
   exacto donde nacen las quimeras que resisten a todo.
2. **Gana siglip**, que es quien manda en ese bin (0,200 frente a 0,149
   de resnet50 y 0,106 de dinov2).

## El esquema por zonas está muerto, y no por el coste

La idea era siglip para pequeños y dinov2 para grandes. La medición que
la mata no es de coste:

| en las re-entradas | |
|---|---|
| el ANTES y el DESPUÉS caen en el MISMO bin | 95 (72 %) |
| caen en bins **DISTINTOS** | **37 (28 %)** |

En una re-entrada se compara el recorte de AHORA con los de ANTES. Si
cada bin usa un backbone distinto, **esas parejas viven en espacios
vectoriales distintos y no se pueden comparar**: un vector de siglip y
uno de dinov2 no tienen ninguna relación métrica.

O sea que el 28 % de las re-entradas quedaría sin poder juzgarse — y son
precisamente aquellas en las que el jugador ha cambiado de profundidad,
que suelen ser las de hueco más largo. **El esquema se rompe justo en el
caso al que sirve.**

## Coste de inferencia

Por recorte, en órdenes de magnitud (224×224):

| backbone | arquitectura | ~GFLOPs/recorte | relativo |
|---|---|---|---|
| resnet50 | CNN | ~4 | 1× |
| siglip-base | ViT-B/16, 196 tokens | ~17,5 | ~4× |
| dinov2-base | ViT-B/14, 256 tokens | ~23 | ~6× |

A escala de partido (≈10.600 recortes por minuto de vídeo con
`sample_every: 3`, ~950.000 en 90 min), siglip son unos 17 PFLOPs por
partido. **El número absoluto hay que medirlo en la próxima pasada de
Colab**, no estimarlo: depende del batch, de la GPU y del solape con la
decodificación. Lo que sí es firme es la relación entre los tres.

Nota sobre el esquema por zonas y el coste: enrutando por tamaño, cada
recorte pasa por UN modelo, así que el cómputo sería parecido al de un
solo backbone. Su coste real es otro — dos modelos en memoria, dos
cachés, y sobre todo la incomparabilidad de arriba. **Aunque saliera
gratis, no compensa.**

## Decisión

**Un solo backbone: siglip-base-patch16-224.** Apache-2.0, gana en el bin
que decide, y una sola representación mantiene comparables todas las
parejas. Menos complejidad y menos superficie de error.

Reserva anotada: dinov2 gana en 20-30 px (0,211 vs 0,170), que es donde
está el 70 % de los recortes. Si algún día el embedding se usa para algo
que opere sobre la población general —y no sobre re-entradas— hay que
volver a esta tabla.
