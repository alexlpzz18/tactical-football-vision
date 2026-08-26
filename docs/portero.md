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

## Criterio 1 — ÚLTIMO HOMBRE: separa perfecto en las dos patas

| pata | portero | veces último hombre | siguiente candidato | margen |
|---|---|---|---|---|
| benjamín, equipo A | persona 6 | **100 %** (59/59) | 0 % | 100 puntos |
| benjamín, equipo B | persona 7 | **92 %** (55/60) | 8 % | 83 puntos |
| Villaviciosa, equipo A | persona 0 | **100 %** (100/100) | 0 % | 100 puntos |
| Villaviciosa, equipo B | persona 1 | **100 %** (100/100) | 0 % | 100 puntos |

**En los cuatro casos, el que más veces es último hombre ES el portero**,
y el segundo candidato está a 83-100 puntos. No hay nada parecido a una
zona de duda. Es el criterio más limpio que ha dado este proyecto.

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

Los porteros **nunca** lo cruzan, así que como VETO es perfecto: cero
falsos negativos en 219 frames de las dos patas. Pero como identificador
no vale solo, porque en una ventana de 60 segundos varios centrales
tampoco cruzan.

Lo que sí separa es la **distancia mínima al medio campo**: los porteros
se quedan a 20-35 m y el jugador de campo más retrasado llega a 5,4 m
(benjamín) y 16,4 m (Villaviciosa). Margen suficiente en el benjamín,
estrecho en Villaviciosa.

## La regla que sale de aquí

**El portero de cada equipo es la identidad que más veces es el último
hombre de su equipo**, con "no cruza el medio campo" como **veto**: un
candidato que lo cruce queda descartado aunque gane en último hombre.

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
