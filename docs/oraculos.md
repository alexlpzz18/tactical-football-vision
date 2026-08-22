# Tests de oráculo: dónde está el margen, medido (20-ago-2026)

Rama `experimento/asociacion-global`. `scripts/oraculos.py`.

Se sustituye una etapa por su versión perfecta —usando el GT del
benjamín— y se mira cuánto sube el resultado. Un mes decidiendo por
intuición dónde estaba el margen; esto lo mide.

## Resultado

Error contra el GT en **métricas de producto** (mediana sobre los
fotogramas del GT):

| variante | nIds | centroide | anchura | profundidad |
|---|---|---|---|---|
| SISTEMA (línea base) | 84 | **1,55 m** | 0,93 m | 1,48 m |
| + contacto: clics CRUDOS | 84 | 2,57 m | 1,02 m | 1,46 m |
| + contacto: clics CORREGIDOS | 84 | 1,61 m | 1,03 m | 0,03 m* |
| **+ oráculo de ASOCIACIÓN** | **14** | **0,42 m** | **0,33 m** | 1,02 m |
| + asociación y contacto | 14 | 0,00 m* | 0,00 m* | 0,03 m* |

\* circular: el GT se construye con esos mismos clics corregidos, así que
la profundidad y el caso conjunto salen cero por construcción. Sirven de
comprobación de que el montaje es coherente, no de medida.

## Lectura: el margen está en la ASOCIACIÓN, no en el anclaje

**Arreglar la asociación divide el error de centroide por 3,7** (1,55 →
0,42 m) y el de anchura por 2,8. Y baja de 84 identidades a 14, que es el
número real de personas.

**Arreglar el anclaje no mejora el centroide**: 1,55 → 1,61 m con los
clics corregidos, y a peor (2,57 m) con los crudos. La anchura tampoco
(0,93 → 1,03).

Eso es un dato duro contra la prioridad que traía la segunda opinión: el
anclaje por pose ataca un sesgo que **las métricas colectivas apenas
notan**, porque un desplazamiento sistemático de todos los jugadores en
la misma dirección **mueve el centroide pero no deforma el bloque**, y ni
siquiera mueve mucho el centroide si el sesgo es parecido para todos.

## Dos limitaciones del oráculo de contacto, dichas claras

1. **Solo altera 1 de cada 5 fotogramas del caché.** El GT está a 1 de
   cada 15 y el caché a 1 de cada 3, así que en el 80 % de los fotogramas
   el anclaje sigue siendo el borde de la caja. El efecto medido es una
   **cota inferior**.
2. **No existe un anclaje "perfecto" disponible.** Los clics crudos
   llevan el sesgo hacia arriba (marcaron el cuerpo, no el suelo) y los
   corregidos se derivaron de las cajas. No hay tercera fuente — y por eso
   la medición en PÍXELES contra RTMPose es la vía correcta para zanjarlo,
   como propuso Alex.

## Un bug que delató un resultado implausible

La primera pasada daba el oráculo de contacto **16,9 m peor** que el
sistema. Eso no es un hallazgo, es un fallo: el conversor a CVAT numera
los tracks 0..N−1 por orden de `jugador`, así que `obj_id` **no** es el
número de jugador. Cada detección recibía la posición de otro niño.

Sin el reflejo de desconfiar de un número imposible, la conclusión habría
sido "el anclaje por pose empeora el producto" — falsa, y habría cerrado
la línea por el motivo equivocado.

## Qué queda por medir de este punto

- **Oráculo de homografía**: no se me ocurre una aproximación honesta con
  los datos actuales. Haría falta una referencia independiente de la
  propia homografía (un objeto estático de posición conocida). Queda
  abierto y no bloquea nada.

---

# PUNTO 3: ¿cuánta contaminación mete nuestra propia puerta? (20-ago-2026)

`scripts/pureza_sin_reentrada.py`. Se desactiva la re-entrada —buffer a
cero, cada reaparición abre tracklet nuevo— y se mide la pureza contra el
GT del benjamín.

| buffer de re-entrada | tracklets | puros | % puros | **pureza obs** | frag. |
|---|---|---|---|---|---|
| **0,0 s (SIN re-entrada)** | 30 | 13 | 43 % | **84,4 %** | 2,1 |
| 0,5 s | 25 | 10 | 40 % | 80,0 % | 1,8 |
| **1,5 s (el adoptado)** | 24 | 9 | 38 % | **80,1 %** | 1,7 |
| 3,0 s | 23 | 9 | 39 % | 78,1 % | 1,6 |

(14 personas reales en el GT)

## Dos lecturas, y la segunda reordena el punto 4

**1. Nuestra puerta mete poca contaminación: 4,3 puntos.** De 84,4 % sin
re-entrada a 80,1 % con el buffer adoptado. A cambio baja la
fragmentación de 2,1 a 1,7 tracklets por persona. El intercambio es
razonable y el buffer se queda.

**2. Y esto es lo importante: SIN re-entrada la pureza sigue siendo solo
84,4 %, y apenas el 43 % de los tracklets son puros.** O sea que **la
mezcla ocurre mayoritariamente DENTRO del seguimiento continuo** —en los
cruces, fotograma a fotograma— y no en las reapariciones.

Es un resultado incómodo: la puerta de re-entrada, que es donde hemos
invertido las últimas semanas, ataca 4 puntos mientras 16 vienen de otro
sitio.

## Consecuencia directa para el punto 4

**Un grafo global que solo UNA tracklets no puede alcanzar el oráculo.**
El oráculo de asociación (centroide 0,42 m) supone identidad perfecta
*por observación*; los tracklets que entrarían al grafo ya vienen
contaminados en un 16 %, y unir bien piezas sucias no las limpia.

Así que el diseño del punto 4 tiene que ser **partir y unir**, no solo
unir:

1. **Partir** los tracklets contaminados (clustering de embeddings dentro
   de cada uno — que es exactamente lo que hace GTA-Link, cuyo algoritmo
   es MIT aunque su checkpoint no sirva).
2. **Unir** globalmente los trozos limpios con el grafo.

En ese orden. Sin el primer paso, el segundo tiene un techo del 84 %.

---

# 4a: PARTIR los tracklets con la apariencia (20-ago-2026)

`src/tracking/partir_tracklets.py` + `scripts/medir_particion.py`.

No con DBSCAN sobre embeddings sueltos, sino con **detección de punto de
cambio**: en una identidad, un intercambio de persona es un cambio
ORDENADO EN EL TIEMPO, no un grupo cualquiera. Se busca el instante que
maximiza la distancia entre la firma de antes y la de después.

La salvaguarda contra el cuarto negativo del proyecto: se compara la
**media de una ventana**, nunca un embedding suelto, y solo se corta en el
mejor punto de cada tracklet.

## Primera tabla — y por qué NO se puede leer tal cual

| variante | tracklets | puros | % puros | pureza obs | frag. |
|---|---|---|---|---|---|
| sin partir (base) | 24 | 9 | 38 % | 80,1 % | 1,7 |
| umbral 0,04 | 83 | 62 | 75 % | **91,3 %** | 5,9 |
| umbral 0,06 | 55 | 37 | 67 % | 89,4 % | 3,9 |
| umbral 0,08 | 35 | 18 | 51 % | 87,8 % | 2,5 |
| umbral 0,10 | 24 | 9 | 38 % | 80,1 % | 1,7 |
| umbral 0,13 | 24 | 9 | 38 % | 80,1 % | 1,7 |

Parece que gana 0,04 con +11 puntos de pureza. **Es falso**, y por la
misma trampa que ya nos pilló con la accuracy de equipos: **la pureza
premia fragmentar.** Un trozo de una sola observación es 100 % puro por
definición. A 0,04 el cortador está troceando casi al máximo permitido.

## El control que lo zanja: cortar en puntos AL AZAR

Mismo número de cortes, colocados al azar:

| umbral | por apariencia | al azar | **ventaja real** |
|---|---|---|---|
| 0,04 | 91,3 % | 88,3 % | **+3,0** |
| 0,06 | 89,4 % | 84,3 % | **+5,1** |
| **0,08** | 87,8 % | 81,8 % | **+6,0** |

**La señal de apariencia aporta ~6 puntos de pureza, no 11.** El resto era
trocear.

Y el óptimo se invierte: **gana 0,08**, el umbral que MENOS corta, porque
es el que mejor aprovecha cada corte. Cortar más añade fragmentación sin
comprar pureza real.

## Punto de operación y lo que le deja al grafo

Con **umbral 0,08**: 24 → 35 tracklets, pureza **80,1 % → 87,8 %**,
fragmentación de 1,7 a 2,5 por persona. El coste de fragmentación que
Alex pidió medir en vez de asumir: **×1,5**, no ×3,5 como sugería el
umbral agresivo.

**El grafo recibirá piezas con ~88 % de pureza, no 100 %.** Ese es su
techo real, y conviene tenerlo delante antes de construirlo: el oráculo
de asociación (centroide 0,42 m) supone identidad perfecta por
observación, y desde 88 % no se llega ahí solo uniendo.

El 12 % que la apariencia no ve son, previsiblemente, los cruces entre
compañeros del mismo equipo — el caso #43, donde dos niños con la misma
equipación tienen embeddings casi iguales. Es el techo estructural que ya
estaba anotado.

---

# 4b: EL GRAFO NO ES EL PROBLEMA (20-ago-2026)

`scripts/grafo_4b.py`. Las dos preguntas, antes de construir nada.

## La barata: el filtro de plausibilidad física funciona

Sobre los 116 tracklets partidos, de **4.735 pares ordenados posibles**:

| filtro acumulado | aristas | % del total |
|---|---|---|
| hueco temporal ≤ 8 s | 1.279 | 27,0 % |
| + velocidad (v_max·Δt + 2σ) | 414 | 8,7 % |
| + equipo compatible | 359 | 7,6 % |
| + escala compatible | **271** | **5,7 %** |

Candidatas por tracklet: **media 2,3, mediana 2**.

| candidatas | tracklets |
|---|---|
| 0 | 37 (32 %) |
| 1 | 13 (11 %) |
| 2 | 20 (17 %) |
| 3 | 13 (11 %) |
| más de 3 | 33 (28 %) |

**El 60 % de los tracklets tiene 2 candidatas o menos.** La física sola
descarta el 94 % de las uniones posibles. La intuición de Alex era
correcta: medio problema se resuelve sin tocar la apariencia.

## La que importa: el ORÁCULO DEL GRAFO dice que NO merece la pena

Todas con equipos del GT, para que la comparación sea justa:

| variante | piezas | pureza | centroide | anchura |
|---|---|---|---|---|
| base SIN partir, unión perfecta | 89 | 80,1 % | 1,81 m | 0,64 m |
| **partido 0,08, unión PERFECTA** | 116 | 87,8 % | **1,68 m** | 0,45 m |
| oráculo de ASOCIACIÓN (100 % puro) | — | 100 % | **0,42 m** | 0,33 m |

**Un grafo perfecto sobre piezas del 88 % llega a 1,68 m. La asociación
perfecta llega a 0,42 m.**

Alex puso el listón en "si sale 0,9 m, el grafo perfecto no arregla el
producto". Salió **1,68 m**: casi el doble de su umbral de descarte.

### El reparto del margen, que es lo decisivo

Del margen total (1,81 → 0,42 m = 1,39 m):

- **partir mejor las piezas**: 1,81 → 1,68 m = **0,13 m (9 %)**
- **unir perfectamente**: ya incluido arriba, es lo que hace el oráculo
- **el 12 % de contaminación que queda dentro**: 1,68 → 0,42 m =
  **1,26 m (91 %)**

**El 91 % del margen está en la PUREZA de las piezas, no en la unión.**

## Consecuencia: no se construye el grafo

Construir el grafo real —coste, resolución global, exclusión,
multi-hipótesis— es semanas de trabajo para disputar el 9 % del margen,
y con un techo demostrado de 1,68 m que ni siquiera bate al sistema
actual (1,55 m con los equipos del clasificador).

**El frente es el 12 % de contaminación que la apariencia no ve**, y ya
sabemos qué es: los cruces entre compañeros del MISMO equipo, donde dos
niños con la misma equipación tienen embeddings casi idénticos. El caso
#43 de Alex.

Y como la apariencia es ciega ahí por construcción, lo único que queda es
**geometría**: continuidad de movimiento a través del cruce — quién
entra por dónde y quién sale por dónde, con la velocidad y la dirección
que traía. Es la línea que abre este resultado.

Lo medido aquí no se tira: el filtro de plausibilidad (5,7 % de aristas,
mediana 2 candidatas) y la partición (+6 puntos de pureza real) siguen
siendo útiles si algún día las piezas llegan limpias.

---

# LOS CRUCES: hay señal geométrica, modesta pero real (20-ago-2026)

`scripts/cruces.py`. Medir el fenómeno antes de construir nada, como
pidió Alex.

## 1. Cuántos son y cuántos falla el sistema

En 30 segundos de juego, con 14 personas:

| | |
|---|---|
| cruces detectados (a menos de 2,5 m) | **61** |
| del MISMO equipo | 17 (28 %) |
| de equipos distintos | 44 |

| ¿los resuelve el sistema? | |
|---|---|
| bien | 22 (48 %) |
| **MAL (intercambio de identidad)** | **24 (52 %)** |
| sin datos suficientes | 15 |

**El sistema falla más de la mitad de los cruces.** No son cinco casos:
son 24 fallos en medio minuto. Extrapolado a un partido de 90 minutos,
del orden de 4.000 intercambios.

## 2. ¿Los resolvería la continuidad de movimiento?

En los 24 que falla, se extrapola cada trayectoria desde antes del cruce
y se mira si la asignación correcta gana a la cruzada:

| | |
|---|---|
| **la geometría acierta** | **15 (65 %)** |
| se equivoca igual | 8 (35 %) |

**65 % frente al 50 % del azar: hay señal.** Modesta, pero real. Si se
aprovechara entera, los intercambios en cruces bajarían de 24 a ~9.

## Dos avisos sobre este número, en direcciones opuestas

**A la baja**: es un oráculo **optimista**. Extrapola con las posiciones
del GT, no con las del sistema. Con posiciones ruidosas —y el temblor
crudo es de 0,10 a 0,20 m según la profundidad— acertará menos.

**Al alza**: el GT va a **0,5 s** y el sistema tiene datos a **0,1 s**. A
medio segundo un niño recorre de 1 a 3,5 m, así que la extrapolación
atraviesa el cruce casi a ciegas; a una décima recorre 0,2-0,7 m y la
continuidad es mucho más informativa. **Este test mide la geometría en
las peores condiciones posibles de muestreo.**

Los dos efectos no se cancelan necesariamente, pero el segundo es
estructural: con la cadencia nativa la señal solo puede ser mayor.

## Un bug que cambió el veredicto

La primera pasada daba **48 %** —indistinguible del azar— y la conclusión
habría sido "la geometría tampoco es la vía". Era un fallo en el factor
de extrapolación: la velocidad se estima sobre un tramo de 15 fotogramas
y se proyecta sobre 30, o sea un factor de 2, pero el código lo
multiplicaba otra vez por dos y extrapolaba el doble de lejos.

Con el factor correcto, 65 %. **Sexto bug cazado por desconfiar de un
número**, y el segundo que habría cerrado una vía buena.

## Recomendación

Merece la pena probar la geometría en los cruces, con dos condiciones:

1. **Trabajar a la cadencia nativa (0,1 s), no a la del GT.** Es donde la
   señal es mayor y donde el sistema realmente decide.
2. **Medir contra este 52 % de fallos como línea base**, no contra
   métricas de producto: el efecto sobre el centroide llegará después, y
   diluido.

---

# EL DISEÑO QUE NO SE VA A CONSTRUIR, y por qué (20-ago-2026)

Alex pidió ver el diseño antes de implementarlo. Al prepararlo salió el
dato que lo invalida, así que va aquí en vez de en el código.

## El diseño que iba a proponer

**Pre-proceso descartado de entrada**: separar las cajas antes de
dárselas a ByteTrack falsea la entrada y la posición final sale mal. No
hay forma honesta de separar dos cuerpos que de verdad están juntos.

**Post-proceso**, con la misma forma que la puerta de re-entrada:
detectar el cruce sobre las identidades ya formadas y, si la continuidad
de movimiento dice que se intercambiaron, **intercambiar las colas** desde
el frame del cruce. No crea ni destruye observaciones, solo las reasigna.

## El dato que lo invalida

El swap de colas solo arregla **intercambios**. Desglose real de los 24
fallos en cruces:

| tipo | n | % | del mismo equipo |
|---|---|---|---|
| **ROTURA de uno** (se parte y abre id nueva) | 18 | **75 %** | 7 |
| ROTURA de los dos | 3 | 12 % | 0 |
| **INTERCAMBIO limpio (A↔B)** | **3** | **12 %** | 0 |

**El swap arreglaría 3 de 24.** No paga.

## Y algo más importante: el modelo mental no se sostiene

Llevamos semanas asumiendo que "las quimeras nacen en los cruces". Estos
datos dicen otra cosa: **los cruces producen ROTURAS, no mezclas.** Y una
rotura no contamina — fragmenta, y es recuperable.

Eso encaja con dos medidas anteriores que apuntaban en la misma dirección
y que no supimos leer juntas:

1. El paso 0 midió que el solape de cajas era señal **débil** (1,8×) para
   predecir un cambio de persona.
2. El oráculo del grafo midió que unir perfectamente las piezas —que es
   exactamente lo que arregla una rotura— deja el centroide en 1,68 m.

Es decir: **ya sabíamos que reparar roturas no arregla el producto**, y
ahora sabemos que las roturas son el 87 % de lo que pasa en los cruces.

## Dónde está entonces la contaminación

Sin respuesta con los datos actuales. 15 de las 24 identidades contienen
más de una persona, así que la mezcla existe; pero no aparece en los
eventos de cruce que este test detecta (dos personas a menos de 2,5 m con
mínimo local de distancia).

Hipótesis pendientes de medir, si se retoma:
- Contaminación en aproximaciones que no llegan a 2,5 m.
- Absorciones lentas, sin un instante de cruce identificable.
- Mi clasificación usa el id **dominante** en ventanas de ±1 s, que es
  gruesa: una identidad puede contaminarse sin que cambie su dominante.

## Recomendación: aplicar la regla de los dos intentos

Es la **segunda** medición que dice que los cruces no son la vía —la
primera fue el paso 0 con su 1,8×—. Por la regla que fijó Alex, se
abandona.

Y su plan B ya estaba anunciado en el propio encargo: **admitir identidad
desconocida** en vez de seguir peleando por resolverla. Con estos
números tiene mejor pinta que nunca: si el 87 % de los fallos en cruces
son roturas y unir roturas no mueve el producto, lo honesto puede ser
marcar esos tramos como incertidumbre en vez de inventar una identidad.

---

# DÓNDE NACE LA CONTAMINACIÓN: hay patrón, y no es el que atacábamos

`scripts/donde_nace_la_contaminacion.py` (20-ago-2026). 15 identidades
contaminadas, **75 cambios de persona** localizados y caracterizados.

## Con control, que es lo que da sentido a los números

Decir "el 99 % tenía a alguien a menos de 5 m" no significa nada: en un
F7 casi siempre hay alguien cerca. La comparación es contra las 814
observaciones del GT.

| señal en el instante del cambio | contaminaciones | base | **enriquecimiento** |
|---|---|---|---|
| **vecino a menos de 2,5 m** | 65 % | 27 % | **2,42×** |
| vecino a menos de 5 m | 99 % | 65 % | 1,53× |
| **fondo del campo (30+ m)** | 95 % | 57 % | **1,65×** |
| solape de cajas > 0,1 | 25 % | — | — |
| caja cortada por el borde | 5 % | — | — |
| hueco de detección > 0,3 s | 5 % | — | — |

Distancia mediana al vecino: **1,70 m frente a 3,78 m** de base. Menos de
la mitad.

## El patrón: proximidad en METROS, no solape en PÍXELES

**La contaminación nace cuando dos personas están cerca en METROS, en el
fondo del campo, con seguimiento continuo y SIN solape de cajas.**

- No es solape: solo el 25 % lo tiene.
- No es el borde del encuadre: 5 %.
- No es una re-entrada: 5 % viene de un hueco.
- Es **proximidad física** (2,42×, el factor más fuerte medido en todo el
  proyecto — más que el 1,8× del solape y comparable al 3,0× de la
  re-entrada) **y profundidad** (1,65×).

Y eso explica por qué las dos vías anteriores fallaron: **llevamos
semanas midiendo IoU en píxeles y huecos temporales, y el factor
dominante es la distancia en metros** — justo la magnitud en la que
trabaja nuestro pipeline y que ByteTrack **no** usa, porque asocia por
IoU.

En el fondo del campo dos jugadores a 1,7 m ocupan muy pocos píxeles de
separación; sus cajas pueden quedar próximas sin llegar a solaparse, y el
IoU no ve riesgo donde lo hay.

El 32 % de los cambios son entre compañeros del MISMO equipo, y el 95 %
en la franja donde el color da 0,000 separando equipos y el embedding
solo 0,20. O sea: donde la geometría en píxeles no avisa y la apariencia
tampoco distingue.

## Qué se puede hacer con esto

Una **puerta de ambigüedad en METROS**, no en IoU: cuando dos identidades
están a menos de ~2,5 m, la asociación es de riesgo, y ahí se decide con
más cuidado o se marca incertidumbre. Es la misma forma que ha funcionado
antes (puerta de re-entrada) aplicada a la señal correcta.

Con dos avisos honestos:

1. **2,42× no es un interruptor.** El 27 % de las observaciones normales
   también tiene un vecino a menos de 2,5 m, así que una regla ahí
   tocaría muchos casos sanos. Hay que medir el coste, no solo el
   beneficio.
2. **El techo sigue siendo el del oráculo**: arreglar la asociación por
   completo da 0,42 m de centroide. Esta vía ataca una parte, no todo.

Pero el diagnóstico ya no está abierto: **la contaminación tiene patrón,
y es accionable.** El plan B (admitir incertidumbre) sigue disponible, y
ahora además sabría DÓNDE aplicarse: en los tramos de proximidad en el
fondo del campo.

---

# LA PUERTA DE PROXIMIDAD EN METROS: medida con su coste (20-ago-2026)

`scripts/puerta_proximidad.py`. Tres formas de actuar, cuatro distancias,
con y sin condicionar a la profundidad. **Todos los centroides de esta
tabla suponen UNIÓN PERFECTA** (las piezas se agrupan por su persona del
GT): son techos, no resultados de producción.

| variante | tracklets | pureza | %puros | frag. | centroide | riesgos | cortes |
|---|---|---|---|---|---|---|---|
| **BASE (sin puerta)** | 24 | 80,1 % | 38 % | 1,7 | **1,81 m** | — | — |
| cortar 1,5 m | 162 | 97,9 % | 91 % | 11,6 | 1,24 m | 1.101 | 1.101 |
| cortar 2,0 m | 244 | 98,7 % | 96 % | 17,4 | **1,22 m** | 1.830 | 1.830 |
| cortar 3,0 m | 368 | 99,2 % | 98 % | 26,3 | 1,26 m | 3.128 | 3.128 |
| apariencia 1,5 m | 31 | 83,5 % | 45 % | 2,2 | 1,69 m | 1.101 | 30 |
| apariencia 2,0 m | 35 | 85,0 % | 49 % | 2,5 | 1,64 m | 1.830 | 49 |
| **apariencia 3,0 m** | 39 | 87,4 % | 54 % | **2,8** | **1,57 m** | 3.128 | **79** |
| marcar (cualquier dist.) | 24 | 80,1 % | 38 % | 1,7 | 1,81 m | 1.101-3.128 | 0 |

## El modo "cortar" es la trampa de siempre

Pureza del 99 % y el mejor centroide (1,22 m)… con **fragmentación ×10 a
×17**: 244 trozos para 14 personas. Es exactamente la trampa que ya nos
ha pillado tres veces: **trozos cortos son puros por definición**, y el
centroide sale bien solo porque lo estamos midiendo con unión perfecta.
En producción habría que unir 244 piezas de verdad, y el oráculo del
grafo ya dijo que unir no llega.

## El modo "apariencia" es el compromiso real

Usa la proximidad como **puerta** y la apariencia como **sentencia**: de
3.128 momentos de riesgo examinados, corta 79. Fragmentación ×1,6, no
×17.

Y aporta sobre la partición del 4a (que cortaba en cualquier punto de
cambio, sin condicionar a la proximidad):

| | pureza | frag. | centroide |
|---|---|---|---|
| 4a: partir por apariencia (0,08) | 87,8 % | 2,5 | 1,68 m |
| **proximidad 3 m + apariencia** | 87,4 % | 2,8 | **1,57 m** |

Misma pureza, algo más de fragmentación, **11 cm mejor de centroide**.
Condicionar el corte a los momentos de proximidad coloca mejor los
cortes, aunque no aumente su número.

Del margen total (1,81 → 0,42 m = 1,39 m), recupera **0,24 m: un 17 %**.

## Lo que NO funciona: condicionar a la profundidad

La intuición era buena —el patrón está concentrado en el fondo (1,65×)—
pero medida no paga:

| | todo el campo | solo fondo 30+ m |
|---|---|---|
| cortar 2,0 m | **1,22 m** | 1,34 m |
| apariencia 3,0 m | **1,57 m** | 1,59 m |

Restringir al fondo toca menos casos **y recupera menos**. El 1,65× de
enriquecimiento no basta para que la restricción compense lo que deja
fuera: el 5 % de contaminaciones que ocurren fuera del fondo también
cuentan, y cerca de la cámara la puerta no estorba porque casi nunca se
dispara.

## Lo que dice el modo "marcar", para el plan B

Los momentos de riesgo son **1.101 a 3.128 de 9.511 observaciones**: entre
el **12 % y el 33 %** del tiempo quedaría marcado como dudoso (8-23 % si
se restringe al fondo).

Es mucho. Un producto que dice "no sé" un tercio del tiempo no es un
producto. Si se va al plan B, habría que marcar solo el subconjunto más
sospechoso, no todos los momentos de proximidad.

## Balance

**Hay mejora real y modesta**: 1,81 → 1,57 m de centroide con
fragmentación ×1,6, sin hundir nada. Es el 17 % del margen.

No es el 0,42 m del oráculo, y conviene no venderlo como tal. Pero es la
primera vía de las cuatro investigadas (re-entrada, grafo, cruces,
proximidad) que **mueve el centroide sin pagar con cobertura**.
