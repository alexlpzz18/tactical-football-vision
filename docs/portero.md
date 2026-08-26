# El portero: los dos criterios de Alex, medidos contra el GT

*25-ago-2026. Reproducir: `python scripts/portero.py` (benjamín) y con
`--config configs/processor_villa_v4_cache.yaml --gt
data/annotations/ground_truth_tracking/annotations.xml --offset 7500`
(Villaviciosa).*

El portero lleva **tres intentos rompiendo cosas**: destrozó el doble
pase por colores, casi rompe la regla de staff lento (es el más lento del
partido, 0,60 m/s) y su exclusividad de área se come jugadores de campo.
Por eso se mide ANTES de construir nada del tercer grupo.

Alex corrige dos reglas que parecían obvias y son **falsas**: un portero
bien entrenado juega adelantado —si el balón está en campo rival sube
casi al centro para cortar los pelotazos a la espalda de la defensa— así
que ni "vive en su tercio" ni "se mueve poco longitudinalmente" valen.

⚠️ Esto se mide sobre el GT, o sea con identidad perfecta: la pregunta es
si los criterios son ciertos EN EL FÚTBOL, no si nuestro tracker los
detecta. Si fallaran aquí, no habría nada que construir encima.

## ⚠️ La primera medición era CIRCULAR (lo cazó la verificación)

`lado_de_cada_portero` decidía qué portería defiende cada equipo mirando
**dónde está el portero, buscándolo por su etiqueta del GT**. O sea que
el banco le estaba dando al criterio la mitad de la respuesta: con el
lado invertido, la regla corona a un jugador de campo al 85-91 % sin
enterarse de nada.

Arreglado: el lado sale ahora de donde sale en producción
(`porteros.deducir_lados`) —la posición media de los jugadores de cada
equipo, excluyendo por GEOMETRÍA a quien viva en un área— y el script
imprime los dos cálculos para poder compararlos. **En las dos patas
coinciden**, así que el resultado sobrevive; pero no se sabía hasta
medirlo.

## Criterio 1 — ÚLTIMO HOMBRE: separa en las dos patas

La puntuación **no es el ratio a secas** sino la cota inferior de Wilson
al 95 %. Por qué: un rival con UNA sola observación en la que resulta ser
último hombre puntúa 1/1 = 100 % y le gana al portero real con 55/60. Con
el GT no muerde —todos están en casi todos los frames— pero con nuestras
identidades, repartidas en 6 fragmentos por jugador, es exactamente lo
que va a pasar. Y filtrar por un mínimo de presencia vacía el ranking,
porque los fragmentos son cortos por definición: hay que **ponderar por
presencia, no filtrar por ella**.

| pata | portero | veces último hombre | puntuación | siguiente | margen |
|---|---|---|---|---|---|
| benjamín, equipo A | persona 6 | 59/59 | **0,94** | 0,00 | 94 puntos |
| benjamín, equipo B | persona 7 | 55/60 | **0,82** | 0,04 | 78 puntos |
| Villaviciosa, equipo A | persona 0 | 100/100 | **0,96** | 0,00 | 96 puntos |
| Villaviciosa, equipo B | persona 1 | 100/100 | **0,96** | 0,00 | 96 puntos |

**En los cuatro casos el que más veces es último hombre ES el portero**,
con 78-96 puntos de margen. No hay zona de duda.

⚠️ Un tercer bug, menor pero feo: el script imprimía "el segundo es 0
(0 %)" porque `if segundo` es **falso cuando el segundo es el obj_id 0**,
que existe. El margen real del benjamín A era 98 y no 100. Con un central
de obj_id 0 al 40 % habría dicho 60 en vez de 20 — justo la cifra de la
que depende la decisión.

⚠️ Un error de signo casi lo tira: la primera versión daba **0 %** para
los dos porteros. Con `lado = -1` (defiende x=0) el último hombre es el
de x más PEQUEÑA, y `min(key=lado*x)` minimizaba −x, o sea cogía la
mayor. Lo delató que un criterio que Alex dice que se cumple casi siempre
saliera exactamente al revés: **un número imposible es más fiable que
releer el signo.**

## Criterio 2 — NO CRUZA EL MEDIO CAMPO: cierto, pero no separa solo

| pata | los porteros | jugadores de campo que TAMPOCO cruzan |
|---|---|---|
| benjamín | 0 % los dos; se quedan a 20,2 y 20,4 m del medio | **1 de 12** (llega a 5,4 m del medio) |
| Villaviciosa | 0 % los dos; se quedan a 35,1 y 32,1 m | **5 de 20** (el que más llega, a 16,4 m) |

Los porteros **nunca** lo cruzan: cero falsos negativos en 219 frames.
Pero como veto es **INERTE** — cambia 0 de 1120 decisiones, porque el
ganador del criterio 1 nunca lo incumple. No es un veto, es
documentación. Y como identificador no vale solo, porque en una ventana
de 60 segundos varios centrales tampoco cruzan.

Lo que sí separa es la **distancia mínima al medio campo**: los porteros
se quedan a 20-35 m y el jugador de campo más retrasado llega a 5,4 m
(benjamín) y 16,4 m (Villaviciosa). Margen suficiente en el benjamín,
estrecho en Villaviciosa.

## La regla que sale de aquí

**El portero de cada equipo es la identidad con la mayor cota inferior de
Wilson de "ser el último hombre de su equipo"**, con el lado del campo
deducido de las posiciones del equipo, no de la etiqueta.

La salvaguarda **no** es "no cruza el medio campo", que está medido que
no cambia ninguna decisión. La que hace falta es otra: **exigir que el
candidato pise el área de portería alguna vez**, que es lo que descarta
al falso positivo cuando el portero no se detecta nunca.

Ventajas sobre lo que hay hoy (mediana dentro del área de penalti +
exclusividad):
- No depende de las dimensiones del área ni de que estén bien puestas
  (el área con margen ocupa el 39 % del campo entre las dos y se come el
  21 % de las observaciones).
- No depende del color, que en un portero es basura por diseño.
- Funciona con el portero adelantado, que es donde la regla de área falla.

## ¿Aguanta lo que le va a pasar en producción?

Tres ataques al criterio 1, en las dos patas:

**a) ¿Cuántos frames hace falta?** Con **5 frames** ya acierta al portero
de los dos equipos, al 100 % y con el segundo a 0 %, en las dos patas. No
necesita el tramo entero, así que sirve en cuanto arranca el partido.

**b) ¿Y si el detector no ve al portero?** Ocultándolo a propósito:

| oculto | benjamín A | benjamín B | Villa A | Villa B |
|---|---|---|---|---|
| 20 % | ✔ 100 % | ✔ 90 % | ✔ 100 % | ✔ 100 % |
| 50 % | ✔ 100 % | ✔ 84 % | ✔ 100 % | ✔ 100 % |
| 80 % | ✔ 100 % | ✔ 100 % | ✔ 100 % | ✔ 100 % |
| 100 % | ✘ | ✘ | ✘ | ✘ |

Aguanta hasta el 80 %. Nuestro detector se deja el 8 %, así que hay
muchísimo margen.

⚠️ **Y aquí está el agujero**: al 100 % —un portero que no se detecte
NUNCA en el tramo— el criterio devuelve un jugador de campo, y **el veto
del medio campo no lo caza**, porque los falsos positivos que aparecen
(persona 8 en el benjamín, personas 10 y 19 en Villaviciosa) están
justamente entre los que tampoco cruzan. Hace falta otra salvaguarda: la
más obvia es exigir que el candidato pase también por el área de portería
alguna vez.

**c) ¿Y cuando el portero está más adelantado?** Que es la corrección de
Alex, y donde las reglas obvias fallan. En el 20 % de frames en que más
sube: **último hombre 11/11 y 12/12 en el benjamín, 20/20 y 20/20 en
Villaviciosa. El 100 %.** El criterio no solo sobrevive al portero
adelantado: es que ahí es donde mejor funciona.

## Lo que falta antes de construir

1. **Medirlo con NUESTRAS identidades, no con el GT.** Cada jugador está
   repartido en una mediana de 6 identidades, así que "la identidad que
   más veces es último hombre" no es lo mismo que "la persona que más
   veces lo es". Es la medición que decide si la regla es implementable, y
   es lo siguiente.
2. **La salvaguarda para el portero nunca detectado** (ver el agujero de
   arriba): exigir que el candidato pise el área alguna vez.
3. **Un tramo con córner a favor**, donde el portero sube del todo. En
   60-100 segundos no hay ninguno, así que el punto (c) de arriba mide el
   portero adelantado pero no el portero en el área contraria.

---

# El examen que decide: con NUESTRAS identidades, y el caso negativo

*26-ago-2026. Reproducir: `python scripts/portero_identidades.py` y con
`--config configs/processor_villa_v4_cache.yaml --gt
data/annotations/ground_truth_tracking/annotations.xml --offset 7500`.*

Todo lo de arriba es con el GT, o sea con identidad perfecta. Aquí se
mide con las identidades reales —repartidas en una mediana de 6
fragmentos por jugador— y, sobre todo, con **el caso negativo**: se le
borran al caché las observaciones del portero y se mira si la regla sabe
decir "aquí no hay portero". Una regla que siempre corona a alguien es
peligrosa: en un partido donde el portero no se vea coronaría a un
central, y ese central saldría del cómputo de su equipo.

## El resultado: 8 de 8

| pata | caso | corona a | punt. | pisa área | presencia | decisión |
|---|---|---|---|---|---|---|
| benjamín | x=0, portero presente | **portero 6** | 0,99 | 100 % | 99 % | corona ✓ |
| benjamín | x=largo, portero presente | **portero 7** | 0,93 | 99 % | 100 % | corona ✓ |
| benjamín | x=0, portero BORRADO | impostor | 0,85 | 100 % | **7 %** | **se abstiene** ✓ |
| benjamín | x=largo, portero BORRADO | impostor | 0,75 | **16 %** | 99 % | **se abstiene** ✓ |
| Villaviciosa | x=0, portero presente | **portero 1** | 0,99 | 100 % | 100 % | corona ✓ |
| Villaviciosa | x=largo, portero presente | **portero 0** | 0,99 | 100 % | 100 % | corona ✓ |
| Villaviciosa | x=0, portero BORRADO | impostor | 0,81 | **0 %** | 21 % | **se abstiene** ✓ |
| Villaviciosa | x=largo, portero BORRADO | impostor | 0,93 | **26 %** | 99 % | **se abstiene** ✓ |

Y en los dos casos negativos donde el portero del OTRO lado sigue estando,
se le sigue coronando bien. No hay daño colateral.

## La puntuación sola NO sirve: hacen falta las dos salvaguardas

| | porteros de verdad | impostores |
|---|---|---|
| puntuación | 0,93 - 0,99 | **0,75 - 0,93** |
| pisa área | 99 - 100 % | 0 - **100 %** |
| presencia | 99 - 100 % | 7 - **99 %** |

- **La puntuación se solapa** (0,93 en los dos lados): un umbral ahí
  estaría ajustado a nada.
- **Ninguna salvaguarda separa sola**: un impostor vive dentro del área
  el 100 % del tiempo (un fragmento de 21 frames detrás de la portería) y
  otro tiene el 99 % de presencia (un defensa).
- **Pero cada impostor falla al menos una.** Exigiendo las dos: 8 de 8.
  Los huecos son anchos (27-98 % en área, 22-98 % en presencia), así que
  0,50 no es un filo.

La tercera idea de Alex —que el color esté lejos de los dos prototipos—
**no se adopta**: los porteros dan 0,55-0,99 y los impostores 0,35-0,83,
o sea que se solapan. Es la más débil de las tres.

## Tres correcciones de diseño que salieron de medir

**1. El voto tiene que incluir a las identidades etiquetadas 'otro'.** El
portero cercano del benjamín viste azul eléctrico, el catálogo arbitral
lo manda a 'otro', y un ranking de solo A/B **no puede encontrarlo**.
Pedirle al color que acierte con el portero es circular: su color no es
fiable, que es la razón de buscarlo por comportamiento.

**2. Y no basta con 'otro': tienen que competir TODAS en los dos lados.**
Medido: al borrar un portero, el fit cambia y el clasificador metió al
OTRO portero en el equipo contrario; como su voto solo contaba en el lado
de su etiqueta, sacó **0 de 494** y la regla se abstuvo teniéndolo
delante. El LADO dice el equipo, igual que en la regla de área.

**3. La presencia se cuenta por LADO, no global.** Una identidad que
compite en las dos votaciones tenía la presencia duplicada y el ratio
partido por dos: el portero cercano salía 523/1048 = 0,47 y perdía contra
un fragmento de 50/51.

## Dos trampas del banco que había que quitar antes

- **El caché se recorta al rango del GT.** Va del frame 8991 al 10788 y
  el GT solo del 9750 al 10635: fuera de ahí no se sabe dónde está el
  portero, así que no se le borraba, y el "impostor" del caso negativo
  era el propio portero en los frames sin anotar. Sobrevivían 343 de sus
  524 observaciones.
- **Se reporta por LADO, no por etiqueta de equipo.** Las etiquetas A/B
  salen del fit y son arbitrarias: al borrar un portero se
  intercambiaron, y la tabla parecía decir un disparate.

## Estado

El portero **pasa el caso negativo**. La regla queda definida así:

> Por cada lado del campo, el portero es la identidad no-staff con la
> mayor cota inferior de Wilson de ser el último hombre de ese lado,
> **siempre que** viva dentro de su área más de la mitad del tiempo y
> esté presente más de la mitad del tramo. Si nadie cumple las dos, **no
> hay portero en ese lado**.

Falta llevarla a `src/` como regla de producto y medirla contra las
métricas de producto frente a la regla de área actual. Y eso es una
adopción, así que necesita el OK de Alex.
